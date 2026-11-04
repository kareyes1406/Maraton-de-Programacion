from rutas_service import vulnerabilidad
from rutas_service.ml import modelos


def test_modelo_disponible_y_metricas():
    assert modelos.disponible()
    m = modelos.metricas()
    elegido = m["modelo_elegido"]
    assert elegido in m["comparacion"]
    # el modelo elegido debe superar a la formula de pesos fijos que se usaba antes
    assert m["comparacion"][elegido]["r2_prueba"] > m["comparacion"]["Fórmula de pesos fijos (antes)"]["r2_prueba"]
    assert m["comparacion"][elegido]["r2_prueba"] > 0.85
    assert 3 <= m["kmeans"]["k_elegido"] <= 6
    nombres = [p["nombre"] for p in m["kmeans"]["perfiles"]]
    assert len(set(nombres)) == len(nombres)


def test_prediccion_en_rango_y_determinista():
    comp = {"nbi": 0.6, "adultos_mayores": 0.5, "barrera_vial": 0.8, "sin_atencion_reciente": 0.3, "cronicos": 0.4}
    a, b = modelos.predecir(comp), modelos.predecir(comp)
    assert a == b
    assert 0 <= a["indice"] <= 1 and a["perfil"] and a["factor_principal"]


def test_monotonia_razonable():
    bajo = {k: 0.1 for k in modelos.CARACTERISTICAS}
    alto = {k: 0.9 for k in modelos.CARACTERISTICAS}
    assert modelos.predecir(alto)["indice"] > modelos.predecir(bajo)["indice"]


def test_vulnerabilidad_usa_modelo():
    v = vulnerabilidad.obtener("25535019")
    assert v["modelo"].startswith("ml-") and "indice_formula" in v and v["perfil"]
