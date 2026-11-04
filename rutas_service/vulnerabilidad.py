"""Indice de vulnerabilidad SIMULADO (precargado en JSON).

No existe una fuente publica con este indice a nivel veredal, por lo que se simula de forma
deterministica (semilla = codigo DANE de la vereda). Los componentes y pesos son explicitos para
que el calculo sea auditable y para que se lea como "necesidad de atencion", nunca como
calificacion de la comunidad.
"""
from __future__ import annotations

import hashlib
import json
import random
from functools import lru_cache

from . import config

PESOS = {
    "nbi": 0.30,                    # necesidades basicas insatisfechas
    "adultos_mayores": 0.20,        # proporcion de poblacion >= 60 anos
    "barrera_vial": 0.25,           # estado de la via / medio de transporte disponible
    "sin_atencion_reciente": 0.15,  # tiempo desde la ultima visita extramural
    "cronicos": 0.10,               # prevalencia de enfermedades cronicas
}

ETIQUETAS = {
    "nbi": "necesidades básicas insatisfechas",
    "adultos_mayores": "población adulta mayor",
    "barrera_vial": "barreras de acceso vial",
    "sin_atencion_reciente": "tiempo sin atención extramural",
    "cronicos": "carga de enfermedad crónica",
}


def simular(codigo: str) -> dict:
    rnd = random.Random(int(hashlib.sha256(codigo.encode()).hexdigest()[:12], 16))
    comp = {
        "nbi": round(rnd.betavariate(2.2, 3.0), 3),
        "adultos_mayores": round(rnd.betavariate(2.0, 4.0), 3),
        "barrera_vial": round(rnd.betavariate(2.0, 2.5), 3),
        "sin_atencion_reciente": round(rnd.betavariate(1.8, 2.2), 3),
        "cronicos": round(rnd.betavariate(2.0, 3.5), 3),
    }
    return {"indice": calcular_indice(comp), "componentes": comp, "simulado": True}


def calcular_indice(comp: dict) -> float:
    return round(sum(PESOS[k] * comp[k] for k in PESOS), 4)


@lru_cache(maxsize=1)
def _tabla() -> dict:
    try:
        return json.loads(config.VULN_FILE.read_text(encoding="utf-8"))["veredas"]
    except (FileNotFoundError, KeyError, ValueError):
        return {}


def obtener(codigo: str) -> dict:
    """Componentes precargados (o simulados) + indice estimado por el modelo de aprendizaje automatico.

    Si el modelo no esta disponible se usa la formula de pesos fijos como respaldo.
    """
    d = _tabla().get(codigo)
    base = {"indice": calcular_indice(d["componentes"]), "componentes": d["componentes"], "simulado": True} \
        if d else simular(codigo)
    base["indice_formula"] = base["indice"]
    from .ml import modelos  # import diferido: el servicio arranca aunque falte el modelo
    if modelos.disponible():
        pred = modelos.predecir(base["componentes"])
        base.update(indice=pred["indice"], perfil=pred["perfil"], factor_principal=pred["factor_principal"],
                    modelo=modelos.version())
    return base


def version_datos() -> str:
    try:
        return hashlib.sha256(config.VULN_FILE.read_bytes()).hexdigest()[:16]
    except FileNotFoundError:
        return "generado-en-linea"
