"""Entrena el Random Forest y el K-Means y guarda modelo + metricas.
Uso: .venv\\Scripts\\python -m scripts.entrenar_modelos
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rutas_service import config  # noqa: E402
from rutas_service.ml import modelos  # noqa: E402

if __name__ == "__main__":
    m = modelos.entrenar(config.VULN_FILE)
    print(json.dumps({k: m[k] for k in ("modelo_elegido", "comparacion", "importancia_permutacion")}, ensure_ascii=False, indent=1))
    print("K-Means k =", m["kmeans"]["k_elegido"], m["kmeans"]["silueta_por_k"])
    for p in m["kmeans"]["perfiles"]:
        print(f"  [{p['id']}] {p['nombre']}: {p['veredas']} veredas")
