"""Componente de aprendizaje automatico (proceso KDD).

1. Seleccion: 2 584 veredas reales de Cundinamarca (codigo DANE) con 5 caracteristicas de necesidad.
2. Preprocesamiento: valores en [0,1]; sin faltantes; semilla fija.
3. Transformacion: estandarizacion (z-score) para K-Means.
4. Mineria de datos:
     - Random Forest (regresion supervisada): estima la necesidad de atencion a partir de las
       caracteristicas, aprendiendo relaciones no lineales e interacciones.
     - K-Means (no supervisado): agrupa las veredas en perfiles de necesidad descriptivos.
5. Interpretacion: metricas (R2, MAE, RMSE, validacion cruzada, silueta) e importancia por permutacion.

IMPORTANTE: no existe una variable objetivo real a nivel veredal. La "necesidad observada" con la que se
entrena es SINTETICA (generada con interacciones no lineales y ruido) para demostrar el pipeline; el modelo
queda listo para reentrenarse con datos oficiales (SISBEN, RIPS, CNPV) sin cambiar la arquitectura.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, silhouette_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

DIR = Path(__file__).parent
MODELO = DIR / "modelo.joblib"
METRICAS = DIR / "metricas.json"
SEMILLA = 42

CARACTERISTICAS = ["nbi", "adultos_mayores", "barrera_vial", "sin_atencion_reciente", "cronicos"]
ETIQUETAS = {
    "nbi": "necesidades básicas insatisfechas",
    "adultos_mayores": "población adulta mayor",
    "barrera_vial": "barreras de acceso vial",
    "sin_atencion_reciente": "tiempo sin atención extramural",
    "cronicos": "carga de enfermedad crónica",
}


# ------------------------------------------------------------------ datos
def objetivo_sintetico(X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """'Necesidad observada' simulada: efectos principales + interacciones + umbral + ruido."""
    nbi, am, bv, sar, cr = X.T
    y = (0.22 * nbi + 0.12 * am + 0.18 * bv + 0.08 * sar + 0.08 * cr
         + 0.40 * am * bv            # adulto mayor + mala via: mucho mas dificil acceder
         + 0.30 * nbi * cr           # pobreza + cronicos: mayor riesgo de complicaciones
         + 0.20 * np.maximum(0, sar - 0.6))  # mucho tiempo sin visita: efecto umbral
    return y + rng.normal(0, 0.025, len(y))


def cargar_dataset(vuln_json: Path) -> tuple[list[str], np.ndarray]:
    datos = json.loads(vuln_json.read_text(encoding="utf-8"))["veredas"]
    codigos = sorted(datos)
    X = np.array([[datos[c]["componentes"][k] for k in CARACTERISTICAS] for c in codigos], dtype=float)
    return codigos, X


# ------------------------------------------------------------------ entrenamiento
def _nombre_perfil(z: np.ndarray) -> str:
    orden = np.argsort(-z)
    if z[orden[0]] < 0.25:
        return "Necesidad moderada en todos los factores"
    principal = ETIQUETAS[CARACTERISTICAS[orden[0]]]
    if z[orden[1]] > 0.5:
        return f"Énfasis en {principal} y {ETIQUETAS[CARACTERISTICAS[orden[1]]]}"
    return f"Énfasis en {principal}"


def entrenar(vuln_json: Path) -> dict:
    rng = np.random.default_rng(SEMILLA)
    codigos, X = cargar_dataset(vuln_json)
    y_raw = objetivo_sintetico(X, rng)
    y_min, y_max = float(y_raw.min()), float(y_raw.max())
    y = (y_raw - y_min) / (y_max - y_min)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEMILLA)

    # --- Seleccion de modelo por validacion cruzada (5 pliegues) sobre el conjunto de entrenamiento
    from ..vulnerabilidad import PESOS  # formula de pesos fijos usada antes del modelo
    w = np.array([PESOS[k] for k in CARACTERISTICAS])
    candidatos = {
        "Regresión lineal": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=150, max_depth=10, min_samples_leaf=3,
                                               random_state=SEMILLA, n_jobs=-1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                                       random_state=SEMILLA),
    }
    kf = KFold(5, shuffle=True, random_state=SEMILLA)
    comparacion = {}
    for nombre, mod in candidatos.items():
        cv = cross_val_score(mod, X_tr, y_tr, cv=kf, scoring="r2")
        mod.fit(X_tr, y_tr)
        p_te = mod.predict(X_te)
        comparacion[nombre] = {
            "r2_cv_media": round(float(cv.mean()), 4), "r2_cv_desv": round(float(cv.std()), 4),
            "r2_prueba": round(float(r2_score(y_te, p_te)), 4),
            "mae_prueba": round(float(mean_absolute_error(y_te, p_te)), 4),
            "rmse_prueba": round(float(np.sqrt(mean_squared_error(y_te, p_te))), 4),
        }
    # la formula de pesos fijos se calibra linealmente para compararla en la misma escala
    cal = LinearRegression().fit((X_tr @ w).reshape(-1, 1), y_tr)
    p_f = cal.predict((X_te @ w).reshape(-1, 1))
    comparacion["Fórmula de pesos fijos (antes)"] = {
        "r2_cv_media": None, "r2_cv_desv": None, "r2_prueba": round(float(r2_score(y_te, p_f)), 4),
        "mae_prueba": round(float(mean_absolute_error(y_te, p_f)), 4),
        "rmse_prueba": round(float(np.sqrt(mean_squared_error(y_te, p_f))), 4),
    }
    elegido = max(candidatos, key=lambda n: comparacion[n]["r2_cv_media"])  # se elige por CV, no por prueba
    rf = candidatos[elegido]

    imp = permutation_importance(rf, X_te, y_te, n_repeats=10, random_state=SEMILLA)
    importancias = {k: round(float(v), 4) for k, v in zip(CARACTERISTICAS, imp.importances_mean)}

    # --- K-Means (perfiles)
    scaler = StandardScaler().fit(X)
    Z = scaler.transform(X)
    siluetas = {}
    for k in range(3, 7):
        km_k = KMeans(n_clusters=k, n_init=10, random_state=SEMILLA).fit(Z)
        siluetas[k] = round(float(silhouette_score(Z, km_k.labels_, sample_size=2000, random_state=SEMILLA)), 4)
    k_opt = max(siluetas, key=siluetas.get)
    km = KMeans(n_clusters=k_opt, n_init=10, random_state=SEMILLA).fit(Z)
    nombres, usados = [], set()
    for c in km.cluster_centers_:
        n = _nombre_perfil(c)
        while n in usados:
            n += " (variante)"
        usados.add(n)
        nombres.append(n)
    tamanos = np.bincount(km.labels_, minlength=k_opt)

    metricas = {
        "version": f"ml-{date.today().isoformat()}",
        "datos": {
            "veredas": len(codigos),
            "entrenamiento": len(X_tr),
            "prueba": len(X_te),
            "caracteristicas": CARACTERISTICAS,
            "objetivo": "necesidad de atención SINTÉTICA (interacciones no lineales + ruido); reemplazable por datos oficiales",
        },
        "modelo_elegido": elegido,
        "criterio_seleccion": "mayor R2 medio en validación cruzada de 5 pliegues",
        "comparacion": comparacion,
        "importancia_permutacion": importancias,
        "kmeans": {
            "k_elegido": k_opt,
            "silueta_por_k": siluetas,
            "perfiles": [
                {"id": i, "nombre": nombres[i], "veredas": int(tamanos[i]),
                 "centroide_z": {k: round(float(v), 2) for k, v in zip(CARACTERISTICAS, km.cluster_centers_[i])}}
                for i in range(k_opt)
            ],
        },
    }
    joblib.dump({"rf": rf, "scaler": scaler, "kmeans": km, "perfiles": nombres, "importancias": importancias,
                 "version": metricas["version"]}, MODELO, compress=3)
    METRICAS.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    return metricas


# ------------------------------------------------------------------ inferencia
@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODELO)  # archivo propio del proyecto (confiable), generado por scripts/entrenar_modelos.py


def disponible() -> bool:
    return MODELO.exists()


def metricas() -> dict:
    return json.loads(METRICAS.read_text(encoding="utf-8"))


def version() -> str:
    return _bundle()["version"]


def predecir(componentes: dict) -> dict:
    b = _bundle()
    x = np.array([[componentes[k] for k in CARACTERISTICAS]], dtype=float)
    indice = float(np.clip(b["rf"].predict(x)[0], 0, 1))
    z = b["scaler"].transform(x)[0]
    perfil = b["perfiles"][int(b["kmeans"].predict(b["scaler"].transform(x))[0])]
    # factor principal local: importancia global del modelo x cuanto se aleja la vereda del promedio
    aporte = {k: b["importancias"][k] * max(z[i], 0) for i, k in enumerate(CARACTERISTICAS)}
    principal = max(aporte, key=aporte.get)
    return {"indice": round(indice, 4), "perfil": perfil, "factor_principal": ETIQUETAS[principal]}
