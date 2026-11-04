"""Genera los diagramas del documento tecnico (PNG 300 dpi, ancho de columna IEEE = 3.5 in).
Uso: python docs/diagramas/generar_diagramas.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).parent
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 6.5})

VERDE, AZUL, GRIS, NARANJA, MORADO = "#1f7a55", "#1d3557", "#6b7b74", "#b5651d", "#5b3f8c"


def caja(ax, x, y, w, h, titulo, lineas=(), color=VERDE, relleno=None, fs=6.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.015",
                                lw=1, ec=color, fc=relleno or "white"))
    ax.text(x + w / 2, y + h - 0.022, titulo, ha="center", va="top", fontsize=fs, weight="bold", color=color)
    for i, l in enumerate(lineas):
        ax.text(x + w / 2, y + h - 0.055 - i * 0.03, l, ha="center", va="top", fontsize=fs - 1, color="#222")


def flecha(ax, p1, p2, txt="", color="#333", estilo="-|>", ls="-", off=(0, 0), fs=5.5, rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=estilo, mutation_scale=7, lw=0.8, color=color,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if txt:
        ax.text((p1[0] + p2[0]) / 2 + off[0], (p1[1] + p2[1]) / 2 + off[1], txt, fontsize=fs,
                ha="center", va="center", color=color,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))


def lienzo(w_in, h_in):
    fig = plt.figure(figsize=(w_in, h_in), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# ------------------------------------------------------------------ 1. arquitectura
def arquitectura():
    fig, ax = lienzo(3.5, 4.3)
    caja(ax, 0.22, 0.86, 0.56, 0.12, "Navegador (SPA)", ["HTML/JS + Leaflet", "Cliente público OAuth 2.0 (PKCE)"], AZUL)
    caja(ax, 0.02, 0.58, 0.40, 0.2, "auth-service :8001", ["FastAPI", "/oauth/authorize, /oauth/token", "JWT RS256 + JWKS", "bcrypt, bloqueo 5 intentos"], MORADO)
    caja(ax, 0.48, 0.42, 0.50, 0.36, "rutas-service :8000", ["FastAPI (API REST)", "seguridad.py  validación JWT/scopes", "optimizador.py  heurístico + 2-opt",
                                                          "fuentes.py  integración APIs", "auditoria.py  cadena de hashes", "cache.py  caché persistente",
                                                          "ml/  Gradient Boosting + K-Means"], VERDE)
    caja(ax, 0.02, 0.36, 0.40, 0.14, "seed_demo.json", ["usuarios, roles y clientes", "(hash bcrypt en memoria)"], GRIS)
    caja(ax, 0.48, 0.22, 0.24, 0.13, "SQLite", ["auditoria", "cache"], NARANJA)
    caja(ax, 0.75, 0.22, 0.23, 0.13, "JSON", ["vulnerabilidad", "simulada (2584)"], NARANJA)
    ax.text(0.5, 0.165, "Fuentes externas (APIs públicas)", ha="center", fontsize=6.5, weight="bold", color=GRIS)
    caja(ax, 0.01, 0.01, 0.235, 0.14, "Esri Colombia", ["Veredas de", "Colombia (DANE)"], GRIS, "#f4f6f5", fs=6)
    caja(ax, 0.255, 0.01, 0.235, 0.14, "Gobernación", ["Centros poblados", "Cundinamarca"], GRIS, "#f4f6f5", fs=6)
    caja(ax, 0.50, 0.01, 0.235, 0.14, "OSRM", ["Distancias y", "ruta por carretera"], GRIS, "#f4f6f5", fs=6)
    caja(ax, 0.745, 0.01, 0.245, 0.14, "OpenStreetMap", ["Teselas del", "mapa base"], GRIS, "#f4f6f5", fs=6)

    flecha(ax, (0.36, 0.86), (0.24, 0.78), "1. login + PKCE", MORADO, off=(-0.07, 0.01))
    flecha(ax, (0.62, 0.86), (0.72, 0.78), "2. HTTPS + Bearer JWT", VERDE, off=(0.1, 0.01))
    flecha(ax, (0.42, 0.66), (0.48, 0.66), "", MORADO, estilo="<|-")
    ax.text(0.45, 0.70, "JWKS", fontsize=5.5, ha="center", color=MORADO)
    flecha(ax, (0.22, 0.58), (0.22, 0.50), "", GRIS, estilo="<|-|>")
    flecha(ax, (0.60, 0.42), (0.60, 0.35), "", NARANJA, estilo="<|-|>")
    flecha(ax, (0.86, 0.42), (0.86, 0.35), "", NARANJA, estilo="<|-")
    for x in (0.13, 0.37, 0.62):
        flecha(ax, (0.55, 0.42), (x, 0.15), "", GRIS, ls="--", rad=0.0)
    flecha(ax, (0.80, 0.86), (0.87, 0.15), "", GRIS, ls="--", rad=-0.25)
    fig.savefig(OUT / "fig1_arquitectura.png")
    plt.close(fig)


# ------------------------------------------------------------------ 2. secuencia
def secuencia():
    fig, ax = lienzo(3.5, 4.6)
    actores = [("Usuario /\nNavegador", 0.11, AZUL), ("auth-service", 0.37, MORADO),
               ("rutas-service", 0.63, VERDE), ("APIs\nexternas", 0.89, GRIS)]
    for n, x, c in actores:
        ax.add_patch(FancyBboxPatch((x - 0.1, 0.93), 0.2, 0.055, boxstyle="round,pad=0.004", ec=c, fc="white", lw=1))
        ax.text(x, 0.957, n, ha="center", va="center", fontsize=6, weight="bold", color=c)
        ax.plot([x, x], [0.02, 0.93], color=c, lw=0.6, ls=(0, (3, 2)))
    pasos = [
        (0.11, 0.37, "GET /authorize (code_challenge S256, state)", MORADO),
        (0.37, 0.11, "formulario de ingreso", MORADO),
        (0.11, 0.37, "POST credenciales (bcrypt)", MORADO),
        (0.37, 0.11, "303 redirect ?code&state", MORADO),
        (0.11, 0.37, "POST /token (code + code_verifier)", MORADO),
        (0.37, 0.11, "access_token JWT RS256 (15 min)", MORADO),
        (0.11, 0.63, "POST /api/rutas  Bearer JWT", VERDE),
        (0.63, 0.37, "JWKS (llave pública, en caché)", MORADO),
        (0.63, 0.63, "valida firma, iss, aud, exp, scope", VERDE),
        (0.63, 0.89, "veredas / cabecera (ArcGIS)", GRIS),
        (0.63, 0.89, "matriz distancias (OSRM table)", GRIS),
        (0.63, 0.63, "prioriza + vecino cercano + 2-opt", VERDE),
        (0.63, 0.63, "registra auditoría (hash encadenado)", NARANJA),
        (0.63, 0.11, "orden de visita, km, motivo, id_auditoría", VERDE),
    ]
    y = 0.885
    for i, (a, b, t, c) in enumerate(pasos, 1):
        if a == b:
            ax.add_patch(FancyArrowPatch((a, y + 0.008), (a, y - 0.03), arrowstyle="-|>", mutation_scale=6, lw=0.7,
                                         color=c, connectionstyle="arc3,rad=-1.6"))
            ax.text(a - 0.02, y - 0.011, f"{i}. {t}", fontsize=5.2, ha="right", va="center", color=c,
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))
            y -= 0.064
            continue
        ax.add_patch(FancyArrowPatch((a, y), (b, y), arrowstyle="-|>", mutation_scale=6, lw=0.8, color=c,
                                     linestyle="-" if a < b or c != MORADO else "--"))
        ax.text(max((a + b) / 2, 0.27), y + 0.016, f"{i}. {t}", fontsize=5.2, ha="center", va="center", color=c,
                bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none"))
        y -= 0.06
    fig.savefig(OUT / "fig2_secuencia.png")
    plt.close(fig)


# ------------------------------------------------------------------ 3. modelo de datos
def tabla(ax, x, y, w, nombre, campos, color, tipo="tabla SQLite"):
    h = 0.045 + 0.028 * len(campos)
    ax.add_patch(FancyBboxPatch((x, y - h), w, h, boxstyle="round,pad=0.004", ec=color, fc="white", lw=1))
    ax.add_patch(FancyBboxPatch((x, y - 0.04), w, 0.04, boxstyle="round,pad=0.004", ec=color, fc=color, lw=1))
    ax.text(x + w / 2, y - 0.02, f"{nombre}", ha="center", va="center", fontsize=6.3, color="white", weight="bold")
    ax.text(x + w, y + 0.012, tipo, ha="right", fontsize=4.8, color=color, style="italic")
    for i, (c, t) in enumerate(campos):
        yy = y - 0.058 - i * 0.028
        ax.text(x + 0.012, yy, c, fontsize=5.2, va="center", weight="bold" if c.startswith(("PK", "FK")) else "normal")
        ax.text(x + w - 0.012, yy, t, fontsize=4.9, va="center", ha="right", color=GRIS)
    return y - h


def modelo_datos():
    fig, ax = lienzo(3.5, 4.4)
    fin_a = tabla(ax, 0.02, 0.96, 0.47, "auditoria", [
        ("PK id", "INTEGER"), ("ts", "TEXT ISO-8601"), ("evento", "TEXT"), ("sub", "TEXT"),
        ("client_id", "TEXT"), ("roles", "JSON"), ("ip", "TEXT"), ("parametros", "JSON"),
        ("entradas_hash", "SHA-256"), ("entradas", "JSON"), ("resultado", "JSON"),
        ("hash_anterior", "SHA-256"), ("hash", "SHA-256")], NARANJA)
    tabla(ax, 0.53, 0.96, 0.45, "cache", [("PK k", "TEXT"), ("v", "JSON"), ("exp", "REAL epoch")], NARANJA)
    tabla(ax, 0.53, 0.78, 0.45, "Vereda", [("PK codigo", "DANE 8 díg."), ("nombre", "texto"), ("cod_municipio", "DANE 5"),
                                          ("lat, lon", "centroide"), ("poligono", "WGS84"), ("area_ha", "num")], GRIS,
          "API Esri/DANE (en caché)")
    tabla(ax, 0.53, 0.46, 0.45, "Vulnerabilidad", [("FK codigo", "→ Vereda"), ("nbi", "0..1"), ("adultos_mayores", "0..1"),
                                                  ("barrera_vial", "0..1"), ("sin_atencion_rec.", "0..1"), ("cronicos", "0..1")],
          VERDE, "JSON precargado (simulado)")
    tabla(ax, 0.02, 0.46, 0.47, "Usuario / Cliente", [("PK username", "texto"), ("hash", "bcrypt"),
                                                     ("roles", "medico|coord.|auditor"), ("client_id", "texto"),
                                                     ("redirect_uris", "lista")], MORADO, "seed_demo.json → memoria")
    ax.annotate("", xy=(0.60, 0.462), xytext=(0.60, 0.567), arrowprops=dict(arrowstyle="-", lw=0.8, color=GRIS))
    ax.text(0.615, 0.52, "1 : 1", fontsize=5, color=GRIS)
    ax.annotate("", xy=(0.12, 0.462), xytext=(0.12, fin_a), arrowprops=dict(arrowstyle="-", lw=0.8, color=MORADO, ls="--"))
    ax.text(0.135, 0.51, "sub → username (N : 1)", fontsize=4.8, color=MORADO, va="center", ha="left")
    # cadena de hashes
    y0 = 0.14
    ax.text(0.5, y0 + 0.07, "Cadena de integridad del registro de auditoría", ha="center", fontsize=6, weight="bold", color=NARANJA)
    for i, x in enumerate((0.03, 0.36, 0.69)):
        ax.add_patch(FancyBboxPatch((x, y0 - 0.1), 0.28, 0.13, boxstyle="round,pad=0.004", ec=NARANJA, fc="#fff7ef", lw=0.9))
        ax.text(x + 0.14, y0 + 0.012, f"registro {i + 1}", ha="center", fontsize=5.5, weight="bold")
        ax.text(x + 0.14, y0 - 0.025, "hash_anterior = h" + ("₀ (0…0)" if i == 0 else str(i)), ha="center", fontsize=4.8)
        ax.text(x + 0.14, y0 - 0.06, f"hash h{i + 1} = SHA-256(campos)", ha="center", fontsize=4.8)
        if i < 2:
            flecha(ax, (x + 0.28, y0 - 0.035), (x + 0.33, y0 - 0.035), "", NARANJA)
    ax.text(0.5, 0.004, "Triggers SQLite bloquean UPDATE/DELETE; /auditoria/verificar recalcula la cadena",
            ha="center", va="bottom", fontsize=4.9, color=GRIS)
    fig.savefig(OUT / "fig3_modelo_datos.png")
    plt.close(fig)


# ------------------------------------------------------------------ 4. algoritmo
def algoritmo():
    fig, ax = lienzo(3.5, 4.0)
    pasos = [
        ("Entrada: municipio, 5–15 candidatas, N visitas, α, equidad", AZUL),
        ("Obtener veredas (API DANE) y cabecera (Gobernación)", GRIS),
        ("ML: Gradient Boosting estima vᵢ; K-Means asigna perfil", MORADO),
        ("Matriz D, T por carretera (OSRM; plan B: haversine×1,4)", GRIS),
        ("pᵢ = α·vᵢ + (1−α)·(1 − dᵢ/d_max) − β·rᵢ", VERDE),
        ("Seleccionar las N veredas de mayor puntaje", VERDE),
        ("Orden inicial: vecino más cercano desde la base", VERDE),
        ("Mejora local 2-opt hasta no haber mejora", VERDE),
        ("¿Duración > jornada de 8 h?  →  advertencia", NARANJA),
        ("Registrar auditoría y devolver ruta explicada", NARANJA),
    ]
    h, gap = 0.072, 0.024
    y = 0.975
    for i, (t, c) in enumerate(pasos):
        ax.add_patch(FancyBboxPatch((0.06, y - h), 0.88, h, boxstyle="round,pad=0.004,rounding_size=0.02",
                                    ec=c, fc="white", lw=0.9))
        ax.text(0.5, y - h / 2, t, ha="center", va="center", fontsize=6)
        if i < len(pasos) - 1:
            flecha(ax, (0.5, y - h), (0.5, y - h - gap), "", "#444")
        y -= h + gap
    fig.savefig(OUT / "fig4_algoritmo.png")
    plt.close(fig)


if __name__ == "__main__":
    arquitectura()
    secuencia()
    modelo_datos()
    algoritmo()
    print("diagramas generados en", OUT)
