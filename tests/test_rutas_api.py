import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from rutas_service import auditoria, config, fuentes, seguridad
from rutas_service import main as rutas

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA = rsa.generate_private_key(public_exponent=65537, key_size=2048)

VEREDAS = [
    {"codigo": f"25535{i:03d}", "nombre": f"Vereda {i}", "municipio": "Pasca", "cod_municipio": "25535",
     "area_ha": 100.0, "lat": 4.30 + 0.01 * (i % 4), "lon": -74.30 + 0.012 * (i // 4), "fuente": "test",
     "poligono": []}
    for i in range(1, 13)
]
BASE = {"nombre": "Cabecera", "lat": 4.30, "lon": -74.30, "fuente": "test"}


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    monkeypatch.setattr(seguridad, "llave_firma", lambda token: LLAVE.public_key())
    monkeypatch.setattr(fuentes, "veredas_municipio", lambda cod: VEREDAS if cod == "25535" else [])
    monkeypatch.setattr(fuentes, "punto_partida", lambda cod, vs: BASE)
    monkeypatch.setattr(fuentes, "geometria_ruta", lambda pts: [[p["lat"], p["lon"]] for p in pts])

    def matriz(pts):
        n = len(pts)
        d = [[fuentes.haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * 1.4 for b in pts] for a in pts]
        return {"distancia_km": d, "tiempo_min": [[x * 2 for x in f] for f in d], "fuente": "test"}

    monkeypatch.setattr(fuentes, "matriz_distancias", matriz)
    seguridad._ventanas.clear()


def token(scopes, sub="medico.demo", llave=LLAVE, exp=900, **extra):
    ahora = int(time.time())
    claims = {"iss": config.AUTH_ISSUER, "aud": "rutas-api", "sub": sub, "scope": " ".join(scopes),
              "iat": ahora, "nbf": ahora, "exp": ahora + exp, "roles": ["medico"], **extra}
    return {"Authorization": "Bearer " + jwt.encode(claims, llave, algorithm="RS256")}


c = TestClient(rutas.app)
MEDICO = ["veredas:leer", "rutas:generar"]
AUDITOR = ["veredas:leer", "auditoria:leer"]


def test_sin_token_401():
    assert c.post("/api/rutas", json={"municipio": "25535"}).status_code == 401


def test_token_firmado_por_otra_llave_401():
    assert c.post("/api/rutas", json={"municipio": "25535"}, headers=token(MEDICO, llave=OTRA)).status_code == 401


def test_token_expirado_401():
    assert c.post("/api/rutas", json={"municipio": "25535"}, headers=token(MEDICO, exp=-10)).status_code == 401


def test_alg_none_rechazado():
    t = jwt.encode({"sub": "x", "aud": "rutas-api", "iss": config.AUTH_ISSUER, "scope": "rutas:generar",
                    "exp": int(time.time()) + 60, "iat": int(time.time())}, None, algorithm="none")
    assert c.post("/api/rutas", json={"municipio": "25535"},
                  headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_rol_sin_permiso_403():
    assert c.post("/api/rutas", json={"municipio": "25535"}, headers=token(AUDITOR, sub="auditor.demo")).status_code == 403
    assert c.get("/api/auditoria", headers=token(MEDICO)).status_code == 403


def test_validacion_entradas_422():
    h = token(MEDICO)
    assert c.post("/api/rutas", json={"municipio": "11001"}, headers=h).status_code == 422          # fuera de Cundinamarca
    assert c.post("/api/rutas", json={"municipio": "25535' OR 1=1--"}, headers=h).status_code == 422  # inyeccion
    assert c.post("/api/rutas", json={"municipio": "25535", "visitas": 50}, headers=h).status_code == 422
    assert c.post("/api/rutas", json={"municipio": "25535", "candidatas": ["25999001"] * 6}, headers=h).status_code == 422


def test_generar_ruta_y_auditar_y_reproducir():
    cand = [v["codigo"] for v in VEREDAS[:10]]
    r = c.post("/api/rutas", json={"municipio": "25535", "candidatas": cand, "visitas": 5, "alpha": 0.7},
               headers=token(MEDICO))
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["orden_visita"]) == 5 and d["distancia_total_km"] > 0
    assert all(p["codigo"] in cand for p in d["orden_visita"])
    assert "SIMULADO" in d["aviso"]

    ha = token(AUDITOR, sub="auditor.demo")
    reg = c.get(f"/api/auditoria/{d['id_auditoria']}", headers=ha).json()
    assert reg["sub"] == "medico.demo" and reg["parametros"]["alpha"] == 0.7
    assert reg["resultado"]["distancia_total_km"] == d["distancia_total_km"]

    rep = c.post(f"/api/auditoria/{d['id_auditoria']}/reproducir", headers=ha).json()
    assert rep["coincide"] is True
    assert c.get("/api/auditoria/verificar", headers=ha).json()["integra"] is True


def test_auditoria_detecta_alteracion():
    c.post("/api/rutas", json={"municipio": "25535"}, headers=token(MEDICO))
    con = sqlite3.connect(config.DB_PATH)
    # la BD bloquea modificaciones...
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE auditoria SET sub='otro' WHERE id=1")
    # ...y aun si un atacante con acceso al archivo quita el trigger, la cadena de hashes lo delata
    con.execute("DROP TRIGGER aud_no_update")
    con.execute("UPDATE auditoria SET parametros='{\"alpha\":1}' WHERE evento='RUTA_GENERADA'")
    con.commit()
    v = auditoria.verificar_cadena()
    assert v["integra"] is False
