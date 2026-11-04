"""rutas-service: priorizacion de visitas domiciliarias en veredas de Cundinamarca."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Path as P, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auditoria, config, fuentes, optimizador, vulnerabilidad
from .ml import modelos
from .seguridad import limitar, requiere

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
AVISO = ("Índice de vulnerabilidad SIMULADO con fines demostrativos. La ruta es una sugerencia "
         "que debe validar el equipo de salud; no reemplaza el criterio profesional ni el conocimiento local.")

app = FastAPI(
    title="rutas-service - Rutas de atención en salud rural",
    version="1.0.0",
    description="Microservicio de priorización de visitas domiciliarias (veredas reales de Cundinamarca, "
                "vulnerabilidad simulada). Protegido con OAuth 2.0 (JWT RS256).",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    # OpenStreetMap exige el encabezado Referer para servir tiles (politica de uso); solo se envia el origen
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.scheme == "https":  # detras del proxy TLS de la nube (uvicorn --proxy-headers)
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif not request.url.path.startswith(("/docs", "/openapi", "/redoc")):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://unpkg.com; "
            "style-src 'self' https://unpkg.com https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com; "
            f"connect-src 'self' {config.AUTH_URL}; frame-ancestors 'none'; form-action {config.AUTH_URL}"
        )
    return resp


def _ip(request: Request):
    return request.client.host if request.client else None


def _fuente(fn, *args):
    try:
        return fn(*args)
    except fuentes.FuenteNoDisponible as e:
        raise HTTPException(503, f"Fuente de datos externa no disponible: {e}")


# ------------------------------------------------------------------ publicos
@app.get("/health")
def health():
    return {"status": "ok", "servicio": "rutas-service", "datos_vulnerabilidad": vulnerabilidad.version_datos()}


@app.get("/api/config")
def config_publica():
    return {"auth_url": config.AUTH_URL, "client_id": "frontend-rutas", "aviso": AVISO}


def _version_modelo():
    return modelos.version() if modelos.disponible() else "formula-pesos-fijos"


@app.get("/api/modelo")
def modelo_ml(_u=Depends(requiere("veredas:leer"))):
    """Métricas del modelo de aprendizaje automático (selección por CV, importancias y perfiles K-Means)."""
    if not modelos.disponible():
        raise HTTPException(404, "Modelo no entrenado; ejecute scripts/entrenar_modelos.py")
    return modelos.metricas()


# ------------------------------------------------------------------ veredas
@app.get("/api/municipios")
def municipios(_u=Depends(requiere("veredas:leer"))):
    return _fuente(fuentes.listar_municipios)


@app.get("/api/municipios/{cod}/veredas")
def veredas(cod: str = P(..., pattern=r"^25\d{3}$"), _u=Depends(requiere("veredas:leer"))):
    vs = _fuente(fuentes.veredas_municipio, cod)
    if not vs:
        raise HTTPException(404, "Municipio sin veredas en la fuente")
    base = fuentes.punto_partida(cod, vs)
    # Sugerencia neutral de candidatas: las 15 mas cercanas a la base (no por vulnerabilidad)
    cercanas = sorted(vs, key=lambda v: fuentes.haversine_km(base["lat"], base["lon"], v["lat"], v["lon"]))
    return {
        "municipio": cod,
        "base": base,
        # minimizacion de datos: el indice NO se expone en el listado general (evita rankings publicos)
        "veredas": vs,
        "sugeridas": [v["codigo"] for v in cercanas[:15]],
        "fuente": "Veredas de Colombia - Esri Colombia Datos Abiertos (DANE/POT)",
    }


# ------------------------------------------------------------------ rutas
class SolicitudRuta(BaseModel):
    municipio: str = Field(..., pattern=r"^25\d{3}$", description="Código DANE del municipio (Cundinamarca)")
    candidatas: list[str] | None = Field(
        None, min_length=5, max_length=15, description="10-15 códigos de vereda candidatas (opcional)"
    )
    visitas: int = Field(5, ge=1, le=8, description="Número de veredas a visitar en la jornada")
    alpha: float = Field(0.6, ge=0, le=1, description="Peso de la vulnerabilidad vs. cercanía")
    tiempo_atencion_min: int = Field(60, ge=15, le=180)
    considerar_equidad: bool = Field(True, description="Ajuste para rotar veredas visitadas recientemente")

    @field_validator("candidatas")
    @classmethod
    def _codigos(cls, v):
        if v is None:
            return v
        if len(set(v)) != len(v):
            raise ValueError("códigos de vereda repetidos")
        for c in v:
            if not (c.isdigit() and len(c) == 8 and c.startswith("25")):
                raise ValueError(f"código de vereda inválido: {c!r}")
        return v


def _ejecutar(parametros: dict, entradas: dict) -> dict:
    cand = entradas["candidatas"]
    if len(cand) < parametros["visitas"]:
        raise HTTPException(422, "Hay menos candidatas que visitas solicitadas")
    return optimizador.priorizar(
        base=entradas["base"],
        candidatas=cand,
        matriz=entradas["matriz"],
        n_visitas=parametros["visitas"],
        alpha=parametros["alpha"],
        beta_equidad=0.1 if parametros["considerar_equidad"] else 0.0,
        visitas_recientes=entradas["visitas_recientes"],
        tiempo_atencion_min=parametros["tiempo_atencion_min"],
        jornada_min=config.JORNADA_MIN,
    )


@app.post("/api/rutas")
def generar_ruta(sol: SolicitudRuta, request: Request, usuario=Depends(requiere("rutas:generar"))):
    limitar(usuario)
    vs = {v["codigo"]: v for v in _fuente(fuentes.veredas_municipio, sol.municipio)}
    if not vs:
        raise HTTPException(404, "Municipio sin veredas en la fuente")
    base = fuentes.punto_partida(sol.municipio, list(vs.values()))

    if sol.candidatas:
        faltan = [c for c in sol.candidatas if c not in vs]
        if faltan:
            raise HTTPException(422, f"Veredas que no pertenecen al municipio: {faltan}")
        codigos, criterio = sol.candidatas, "seleccionadas por el usuario"
    else:
        codigos = [v["codigo"] for v in sorted(
            vs.values(), key=lambda v: fuentes.haversine_km(base["lat"], base["lon"], v["lat"], v["lon"]))[:15]]
        criterio = "15 veredas más cercanas a la base (criterio neutral)"

    candidatas = []
    for c in sorted(codigos):
        v, vul = vs[c], vulnerabilidad.obtener(c)
        candidatas.append({"codigo": c, "nombre": v["nombre"], "lat": v["lat"], "lon": v["lon"],
                           "vulnerabilidad": vul["indice"], "componentes": vul["componentes"],
                           "perfil": vul.get("perfil"), "factor_principal": vul.get("factor_principal")})

    matriz = fuentes.matriz_distancias([base] + candidatas)
    entradas = {
        "base": base,
        "candidatas": candidatas,
        "matriz": matriz,
        "visitas_recientes": auditoria.visitas_recientes() if sol.considerar_equidad else {},
        "version_vulnerabilidad": vulnerabilidad.version_datos(),
        "modelo_ml": _version_modelo(),
        "criterio_candidatas": criterio,
    }
    parametros = sol.model_dump()
    resultado = _ejecutar(parametros, entradas)

    ordenados = [base] + [{"lat": p["lat"], "lon": p["lon"]} for p in resultado["orden_visita"]] + [base]
    id_aud = auditoria.registrar("RUTA_GENERADA", usuario, _ip(request), parametros, entradas, resultado)
    return {
        "id_auditoria": id_aud,
        "municipio": sol.municipio,
        "base": base,
        **resultado,
        "parametros": parametros,
        "criterio_candidatas": criterio,
        "candidatas_evaluadas": len(candidatas),
        "fuente_distancias": matriz["fuente"],
        "modelo_ml": entradas["modelo_ml"],
        "geometria": fuentes.geometria_ruta(ordenados),
        "aviso": AVISO,
    }


# ------------------------------------------------------------------ auditoria
@app.get("/api/auditoria")
def auditoria_listar(
    request: Request,
    limite: int = Query(50, ge=1, le=500),
    evento: str | None = Query(None, pattern=r"^[A-Z_]{3,30}$"),
    usuario=Depends(requiere("auditoria:leer")),
):
    return auditoria.listar(limite, evento)


@app.get("/api/auditoria/verificar")
def auditoria_verificar(usuario=Depends(requiere("auditoria:leer"))):
    return auditoria.verificar_cadena()


@app.get("/api/auditoria/{id_}")
def auditoria_detalle(id_: int, usuario=Depends(requiere("auditoria:leer"))):
    r = auditoria.obtener(id_)
    if not r:
        raise HTTPException(404, "Registro no encontrado")
    return r


@app.post("/api/auditoria/{id_}/reproducir")
def auditoria_reproducir(id_: int, request: Request, usuario=Depends(requiere("auditoria:leer"))):
    """Re-ejecuta el algoritmo con los parametros y datos exactos del registro y compara."""
    r = auditoria.obtener(id_)
    if not r or r["evento"] != "RUTA_GENERADA":
        raise HTTPException(404, "Registro de ruta no encontrado")
    nuevo = _ejecutar(r["parametros"], r["entradas"])
    coincide = (
        [p["codigo"] for p in nuevo["orden_visita"]] == [p["codigo"] for p in r["resultado"]["orden_visita"]]
        and nuevo["distancia_total_km"] == r["resultado"]["distancia_total_km"]
    )
    auditoria.registrar("RUTA_REPRODUCIDA", usuario, _ip(request), {"id_original": id_, "coincide": coincide})
    return {"id_original": id_, "coincide": coincide, "original": r["resultado"], "reproducido": nuevo}


# ------------------------------------------------------------------ frontend
if FRONTEND.exists():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
