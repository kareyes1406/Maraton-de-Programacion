"""Genera rutas_service/data/vulnerabilidad_simulada.json para todas las veredas de Cundinamarca.

Descarga los codigos de vereda desde la API publica (Esri Colombia / DANE) y asigna componentes
simulados de forma deterministica. Uso:  python -m scripts.generar_vulnerabilidad
"""
import json
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rutas_service import config, vulnerabilidad  # noqa: E402


def main():
    codigos, offset = {}, 0
    while True:
        r = httpx.get(
            config.ARCGIS_VEREDAS,
            params={
                "where": f"COD_DPTO='{config.COD_DPTO}'",
                "outFields": "CODIGO_VER,NOMBRE_VER,NOMB_MPIO",
                "returnGeometry": "false",
                "orderByFields": "CODIGO_VER",
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "f": "json",
            },
            timeout=60,
        )
        feats = r.json().get("features", [])
        for f in feats:
            a = f["attributes"]
            codigos[a["CODIGO_VER"]] = f"{a['NOMBRE_VER']} ({a['NOMB_MPIO']})"
        if len(feats) < 1000:
            break
        offset += 1000

    salida = {
        "_metadata": {
            "descripcion": "Indice de vulnerabilidad SIMULADO para demostracion. No representa la realidad de ninguna comunidad.",
            "generado": date.today().isoformat(),
            "fuente_codigos": "Veredas de Colombia - Esri Colombia Datos Abiertos (base DANE/POT)",
            "pesos": vulnerabilidad.PESOS,
            "escala": "0 (menor necesidad de atencion) a 1 (mayor necesidad de atencion)",
            "total_veredas": len(codigos),
        },
        "veredas": {
            c: {"referencia": n, "componentes": vulnerabilidad.simular(c)["componentes"]}
            for c, n in sorted(codigos.items())
        },
    }
    config.VULN_FILE.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(codigos)} veredas -> {config.VULN_FILE}")


if __name__ == "__main__":
    main()
