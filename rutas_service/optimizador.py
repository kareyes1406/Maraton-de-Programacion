"""Algoritmo de priorizacion y ordenamiento de visitas.

Paso 1 - Seleccion (heuristico multicriterio, transparente):
    puntaje_i = a * vulnerabilidad_i + (1 - a) * cercania_i - b * rotacion_i
      cercania_i = 1 - d(base, i) / d_max            (distancia real por carretera)
      rotacion_i = min(visitas_recientes_i, 3) / 3   (equidad: evita visitar siempre las mismas)
    Se eligen las N veredas de mayor puntaje (empates -> codigo, determinista).

Paso 2 - Orden de visita (TSP con regreso a la base):
    vecino mas cercano desde la cabecera + mejora local 2-opt.

Funcion pura y determinista: con las mismas entradas produce exactamente la misma salida,
lo que permite reproducir cualquier ruta desde el registro de auditoria.
"""
from __future__ import annotations

from .vulnerabilidad import ETIQUETAS, PESOS


def _costo_tour(tour, dist):
    return sum(dist[a][b] for a, b in zip(tour, tour[1:]))


def vecino_mas_cercano(nodos: list[int], dist) -> list[int]:
    tour, pendientes = [0], set(nodos)
    while pendientes:
        actual = tour[-1]
        sig = min(pendientes, key=lambda j: (dist[actual][j], j))
        tour.append(sig)
        pendientes.remove(sig)
    return tour + [0]


def dos_opt(tour: list[int], dist) -> list[int]:
    mejor, mejoro = tour[:], True
    while mejoro:
        mejoro = False
        for i in range(1, len(mejor) - 2):
            for k in range(i + 1, len(mejor) - 1):
                nuevo = mejor[:i] + mejor[i:k + 1][::-1] + mejor[k + 1:]
                if _costo_tour(nuevo, dist) + 1e-9 < _costo_tour(mejor, dist):
                    mejor, mejoro = nuevo, True
    return mejor


def _motivo(c: dict, alpha: float, cerc: float, rot: float, beta: float) -> str:
    aporte_v = alpha * c["vulnerabilidad"]
    aporte_d = (1 - alpha) * cerc
    comp = c["componentes"]
    # el factor principal lo calcula el modelo de ML; si no esta disponible se usa la formula de pesos fijos
    factor = c.get("factor_principal") or ETIQUETAS[max(PESOS, key=lambda k: PESOS[k] * comp[k])]
    partes = [
        f"necesidad de atención aporta {aporte_v:.2f}",
        f"cercanía a la base aporta {aporte_d:.2f}",
    ]
    if rot:
        partes.append(f"ajuste por visitas recientes -{beta * rot:.2f}")
    return "; ".join(partes) + f". Factor de necesidad más relevante: {factor}."


def priorizar(
    base: dict,
    candidatas: list[dict],
    matriz: dict,
    n_visitas: int = 5,
    alpha: float = 0.6,
    beta_equidad: float = 0.1,
    visitas_recientes: dict | None = None,
    tiempo_atencion_min: int = 60,
    jornada_min: int = 480,
) -> dict:
    """`matriz` incluye la base en el indice 0 y las candidatas en 1..n en el mismo orden."""
    dist, dur = matriz["distancia_km"], matriz["tiempo_min"]
    visitas_recientes = visitas_recientes or {}
    n_visitas = min(n_visitas, len(candidatas))

    # ida y vuelta: no castigar veredas donde la via de regreso es mucho mas larga
    d_base = [(dist[0][i + 1] + dist[i + 1][0]) / 2 for i in range(len(candidatas))]
    d_max = max(d_base) or 1.0

    evaluadas = []
    for i, c in enumerate(candidatas):
        cerc = 1 - d_base[i] / d_max
        rot = min(visitas_recientes.get(c["codigo"], 0), 3) / 3
        puntaje = alpha * c["vulnerabilidad"] + (1 - alpha) * cerc - beta_equidad * rot
        evaluadas.append(
            {
                "idx": i + 1,
                "codigo": c["codigo"],
                "nombre": c["nombre"],
                "lat": c["lat"],
                "lon": c["lon"],
                "vulnerabilidad": round(c["vulnerabilidad"], 4),
                "distancia_base_km": round(d_base[i], 2),
                "cercania": round(cerc, 4),
                "ajuste_rotacion": round(-beta_equidad * rot, 4),
                "puntaje": round(puntaje, 4),
                "motivo": _motivo(c, alpha, cerc, rot, beta_equidad),
                "perfil": c.get("perfil"),
            }
        )

    ranking = sorted(evaluadas, key=lambda e: (-e["puntaje"], e["codigo"]))
    elegidas = ranking[:n_visitas]
    tour = dos_opt(vecino_mas_cercano([e["idx"] for e in elegidas], dist), dist)
    por_idx = {e["idx"]: e for e in elegidas}

    paradas, km, minutos = [], 0.0, 0.0
    for orden, (a, b) in enumerate(zip(tour, tour[1:]), start=1):
        km += dist[a][b]
        minutos += dur[a][b]
        if b == 0:
            break
        minutos += tiempo_atencion_min
        e = por_idx[b]
        paradas.append(
            {
                "orden": orden,
                **{k: e[k] for k in ("codigo", "nombre", "lat", "lon", "vulnerabilidad", "puntaje", "motivo", "perfil")},
                "tramo_km": round(dist[a][b], 2),
                "llegada_estimada_min": round(minutos - tiempo_atencion_min, 1),
            }
        )

    advertencias = []
    if minutos > jornada_min:
        advertencias.append(
            f"La jornada estimada ({minutos / 60:.1f} h) supera {jornada_min / 60:.0f} h: "
            "considere reducir visitas o dividir en dos jornadas."
        )

    return {
        "orden_visita": paradas,
        "distancia_total_km": round(km, 2),
        "tiempo_desplazamiento_min": round(sum(dur[a][b] for a, b in zip(tour, tour[1:])), 1),
        "tiempo_total_estimado_min": round(minutos, 1),
        "regresa_a_base": True,
        "no_seleccionadas": [
            {k: e[k] for k in ("codigo", "nombre", "puntaje", "motivo")} for e in ranking[n_visitas:]
        ],
        "advertencias": advertencias,
    }
