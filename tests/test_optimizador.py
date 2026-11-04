import itertools
import random

from rutas_service import fuentes, optimizador


def _escenario(n=12, semilla=7):
    rnd = random.Random(semilla)
    base = {"lat": 4.30, "lon": -74.30}
    cands = []
    for i in range(n):
        cands.append({
            "codigo": f"25535{i:03d}", "nombre": f"V{i}",
            "lat": 4.30 + rnd.uniform(-0.08, 0.08), "lon": -74.30 + rnd.uniform(-0.08, 0.08),
            "vulnerabilidad": round(rnd.random(), 3),
            "componentes": {k: rnd.random() for k in
                            ("nbi", "adultos_mayores", "barrera_vial", "sin_atencion_reciente", "cronicos")},
        })
    puntos = [base] + cands
    dist = [[fuentes.haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for b in puntos] for a in puntos]
    dur = [[d * 2 for d in fila] for fila in dist]
    return base, cands, {"distancia_km": dist, "tiempo_min": dur}


def test_selecciona_n_y_regresa_a_base():
    base, cands, m = _escenario()
    r = optimizador.priorizar(base, cands, m, n_visitas=5)
    assert len(r["orden_visita"]) == 5
    assert len(r["no_seleccionadas"]) == len(cands) - 5
    assert [p["orden"] for p in r["orden_visita"]] == [1, 2, 3, 4, 5]
    assert r["regresa_a_base"] and r["distancia_total_km"] > 0


def test_determinista():
    base, cands, m = _escenario()
    assert optimizador.priorizar(base, cands, m) == optimizador.priorizar(base, cands, m)


def test_alpha_extremos():
    base, cands, m = _escenario()
    solo_necesidad = optimizador.priorizar(base, cands, m, n_visitas=3, alpha=1.0)
    top3 = sorted(cands, key=lambda c: -c["vulnerabilidad"])[:3]
    assert {p["codigo"] for p in solo_necesidad["orden_visita"]} == {c["codigo"] for c in top3}

    solo_cercania = optimizador.priorizar(base, cands, m, n_visitas=3, alpha=0.0)
    cercanas = sorted(range(len(cands)), key=lambda i: m["distancia_km"][0][i + 1])[:3]
    assert {p["codigo"] for p in solo_cercania["orden_visita"]} == {cands[i]["codigo"] for i in cercanas}


def test_dos_opt_cerca_del_optimo():
    base, cands, m = _escenario(n=8)
    r = optimizador.priorizar(base, cands, m, n_visitas=6, alpha=0.5)
    idx = {c["codigo"]: i + 1 for i, c in enumerate(cands)}
    nodos = [idx[p["codigo"]] for p in r["orden_visita"]]
    d = m["distancia_km"]
    optimo = min(
        sum(d[a][b] for a, b in zip((0,) + p, p + (0,))) for p in itertools.permutations(nodos)
    )
    assert r["distancia_total_km"] <= optimo * 1.10 + 0.01  # heuristico a <=10% del optimo


def test_equidad_rota_veredas():
    base, cands, m = _escenario()
    r1 = optimizador.priorizar(base, cands, m, n_visitas=5, alpha=1.0)
    elegidas = {p["codigo"]: 3 for p in r1["orden_visita"]}
    r2 = optimizador.priorizar(base, cands, m, n_visitas=5, alpha=1.0, beta_equidad=1.0, visitas_recientes=elegidas)
    assert {p["codigo"] for p in r2["orden_visita"]} != set(elegidas)


def test_advierte_jornada_larga():
    base, cands, m = _escenario()
    r = optimizador.priorizar(base, cands, m, n_visitas=8, tiempo_atencion_min=120)
    assert r["advertencias"]
