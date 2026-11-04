"""Integracion con fuentes de datos externas.

* Veredas de Colombia (Esri Colombia - Datos Abiertos, base DANE/POT): limites veredales reales.
* Mapa Veredal de Cundinamarca (Gobernacion): centros poblados -> punto de partida (cabecera).
* OSRM (OpenStreetMap): matriz de distancias/tiempos por carretera y trazado de la ruta.

Cada fuente tiene cache y un plan B (fallback) para no detener la operacion si falla.
"""
from __future__ import annotations

import hashlib
import math
import unicodedata

import httpx

from . import cache, config


class FuenteNoDisponible(Exception):
    pass


def _get_json(url: str, params: dict) -> dict:
    try:
        r = httpx.get(url, params=params, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise FuenteNoDisponible(f"{url}: {e}") from e
    if isinstance(data, dict) and data.get("error"):
        raise FuenteNoDisponible(f"{url}: {data['error']}")
    return data


def _cacheado(key: str, ttl: int, fn):
    val = cache.get(key)
    if val is not None:
        return val
    try:
        val = fn()
    except FuenteNoDisponible:
        viejo = cache.get(key, permitir_expirado=True)
        if viejo is not None:
            return viejo
        raise
    cache.set(key, val, ttl)
    return val


def _titulo(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").strip()
    menores = {"de", "del", "la", "las", "los", "el", "y", "en"}
    return " ".join(
        p.lower() if (i > 0 and p.lower() in menores) else p.capitalize() for i, p in enumerate(s.split())
    )


# ------------------------------------------------------------------ geometria
def _centroide_anillo(ring):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    a *= 0.5
    return cx / (6 * a), cy / (6 * a), abs(a)


def centroide(rings) -> tuple[float, float]:
    """Centroide del anillo de mayor area (lon, lat)."""
    mejor = max((_centroide_anillo(r) for r in rings if len(r) >= 3), key=lambda t: t[2])
    return mejor[0], mejor[1]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ municipios / veredas
def listar_municipios() -> list[dict]:
    def fn():
        data = _get_json(
            config.ARCGIS_VEREDAS,
            {
                "where": f"COD_DPTO='{config.COD_DPTO}'",
                "outFields": "DPTOMPIO,NOMB_MPIO",
                "returnDistinctValues": "true",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        vistos = {}
        for f in data.get("features", []):
            a = f["attributes"]
            vistos.setdefault(a["DPTOMPIO"], _titulo(a["NOMB_MPIO"]))
        return sorted(({"codigo": k, "nombre": v} for k, v in vistos.items()), key=lambda m: m["nombre"])

    return _cacheado(f"municipios:{config.COD_DPTO}", config.CACHE_TTL_GEO, fn)


def veredas_municipio(cod_mpio: str) -> list[dict]:
    def fn():
        data = _get_json(
            config.ARCGIS_VEREDAS,
            {
                "where": f"DPTOMPIO='{cod_mpio}'",  # cod_mpio ya validado con regex ^25\d{3}$
                "outFields": "CODIGO_VER,NOMBRE_VER,NOMB_MPIO,DPTOMPIO,AREA_HA,FUENTE,VIGENCIA",
                "returnGeometry": "true",
                "outSR": "4326",
                "maxAllowableOffset": "0.0015",
                "geometryPrecision": "5",
                "f": "json",
            },
        )
        res = []
        for f in data.get("features", []):
            a, g = f["attributes"], f.get("geometry") or {}
            rings = g.get("rings") or []
            if not rings:
                continue
            lon, lat = centroide(rings)
            res.append(
                {
                    "codigo": a["CODIGO_VER"],
                    "nombre": _titulo(a["NOMBRE_VER"]),
                    "municipio": _titulo(a["NOMB_MPIO"]),
                    "cod_municipio": a["DPTOMPIO"],
                    "area_ha": round(a.get("AREA_HA") or 0, 1),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "fuente": f"{a.get('FUENTE') or 'N/D'} {a.get('VIGENCIA') or ''}".strip(),
                    "poligono": [[[p[1], p[0]] for p in r] for r in rings],  # [lat, lon] para Leaflet
                }
            )
        return sorted(res, key=lambda v: v["codigo"])

    return _cacheado(f"veredas:{cod_mpio}", config.CACHE_TTL_GEO, fn)


def punto_partida(cod_mpio: str, veredas: list[dict]) -> dict:
    """Cabecera municipal (sede del puesto/centro de salud) segun la Gobernacion."""

    def fn():
        data = _get_json(
            config.ARCGIS_CENTROS_POBLADOS,
            {
                "where": f"CODIGO_MUN='{cod_mpio}'",
                "outFields": "COD_CENTRO,NOMBRE,MUNICIPIO",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "f": "json",
            },
        )
        feats = [f for f in data.get("features", []) if f.get("centroid")]
        if not feats:
            raise FuenteNoDisponible("sin centros poblados")
        cab = next(
            (f for f in feats if _titulo(f["attributes"]["NOMBRE"]) == _titulo(f["attributes"]["MUNICIPIO"])),
            min(feats, key=lambda f: f["attributes"]["COD_CENTRO"]),
        )
        return {
            "nombre": f"Cabecera {_titulo(cab['attributes']['NOMBRE'])}",
            "lat": round(cab["centroid"]["y"], 6),
            "lon": round(cab["centroid"]["x"], 6),
            "fuente": "Gobernacion de Cundinamarca - centros poblados",
        }

    try:
        return _cacheado(f"cabecera:{cod_mpio}", config.CACHE_TTL_GEO, fn)
    except FuenteNoDisponible:
        lat = sum(v["lat"] for v in veredas) / len(veredas)
        lon = sum(v["lon"] for v in veredas) / len(veredas)
        return {"nombre": "Punto central del municipio (aprox.)", "lat": round(lat, 6), "lon": round(lon, 6),
                "fuente": "fallback: promedio de centroides"}


# ------------------------------------------------------------------ distancias
def _coords(puntos):
    return ";".join(f"{p['lon']:.5f},{p['lat']:.5f}" for p in puntos)


def matriz_distancias(puntos: list[dict]) -> dict:
    """Matriz NxN de distancia (km) y tiempo (min). Fuente OSRM; fallback haversine."""
    coords = _coords(puntos)
    key = "osrm:table:" + hashlib.sha256(coords.encode()).hexdigest()

    def fn():
        data = _get_json(
            f"{config.OSRM_URL}/table/v1/driving/{coords}",
            {"annotations": "distance,duration"},
        )
        if data.get("code") != "Ok":
            raise FuenteNoDisponible(f"OSRM: {data.get('code')}")
        dist = [[round((d or 0) / 1000, 3) for d in fila] for fila in data["distances"]]
        dur = [[round((t or 0) / 60, 2) for t in fila] for fila in data["durations"]]
        return {"distancia_km": dist, "tiempo_min": dur, "fuente": "OSRM (OpenStreetMap) - distancia por carretera"}

    try:
        return _cacheado(key, config.CACHE_TTL_OSRM, fn)
    except FuenteNoDisponible:
        n = len(puntos)
        dist = [[0.0] * n for _ in range(n)]
        dur = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    d = haversine_km(puntos[i]["lat"], puntos[i]["lon"], puntos[j]["lat"], puntos[j]["lon"])
                    dist[i][j] = round(d * config.FACTOR_SINUOSIDAD, 3)
                    dur[i][j] = round(dist[i][j] / config.VELOCIDAD_RURAL_KMH * 60, 2)
        return {
            "distancia_km": dist,
            "tiempo_min": dur,
            "fuente": f"fallback: haversine x {config.FACTOR_SINUOSIDAD} (OSRM no disponible)",
        }


def geometria_ruta(puntos: list[dict]) -> list[list[float]]:
    """Trazado [lat, lon] por carretera para dibujar en el mapa (fallback: lineas rectas)."""
    coords = _coords(puntos)
    key = "osrm:route:" + hashlib.sha256(coords.encode()).hexdigest()

    def fn():
        data = _get_json(
            f"{config.OSRM_URL}/route/v1/driving/{coords}",
            {"overview": "simplified", "geometries": "geojson"},
        )
        if data.get("code") != "Ok":
            raise FuenteNoDisponible("OSRM route")
        return [[round(lat, 5), round(lon, 5)] for lon, lat in data["routes"][0]["geometry"]["coordinates"]]

    try:
        return _cacheado(key, config.CACHE_TTL_OSRM, fn)
    except FuenteNoDisponible:
        return [[p["lat"], p["lon"]] for p in puntos]
