import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi.testclient import TestClient

from auth_service import main as auth

c = TestClient(auth.app)
REDIRECT = "http://localhost:8000/"


def _pkce():
    v = secrets.token_urlsafe(48)
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    return v, ch


def _login(user="medico.demo", pw="Medico#2026", challenge=None):
    return c.post("/oauth/authorize", data={
        "username": user, "password": pw, "client_id": "frontend-rutas", "redirect_uri": REDIRECT,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    }, follow_redirects=False)


def _codigo(resp):
    return parse_qs(urlparse(resp.headers["location"]).query)["code"][0]


def _pub():
    return auth.PUBLIC_KEY


def test_flujo_pkce_completo():
    v, ch = _pkce()
    r = _login(challenge=ch)
    assert r.status_code == 303 and "state=xyz" in r.headers["location"]
    t = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": _codigo(r),
                                     "redirect_uri": REDIRECT, "client_id": "frontend-rutas", "code_verifier": v})
    assert t.status_code == 200
    claims = jwt.decode(t.json()["access_token"], _pub(), algorithms=["RS256"], audience="rutas-api")
    assert claims["sub"] == "medico.demo"
    assert "rutas:generar" in claims["scope"] and "auditoria:leer" not in claims["scope"]


def test_pkce_verifier_incorrecto_y_codigo_de_un_solo_uso():
    v, ch = _pkce()
    code = _codigo(_login(challenge=ch))
    malo = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                        "client_id": "frontend-rutas", "code_verifier": _pkce()[0]})
    assert malo.status_code == 400
    # el codigo ya fue consumido, aun con el verifier correcto
    otra = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                        "client_id": "frontend-rutas", "code_verifier": v})
    assert otra.status_code == 400


def test_redirect_uri_no_registrada():
    _, ch = _pkce()
    r = c.get("/oauth/authorize", params={"client_id": "frontend-rutas", "redirect_uri": "https://evil.example/",
                                          "code_challenge": ch, "response_type": "code"})
    assert r.status_code == 400


def test_password_incorrecta_y_bloqueo():
    _, ch = _pkce()
    for _ in range(auth.MAX_INTENTOS):
        assert _login(user="auditor.demo", pw="mala", challenge=ch).status_code == 401
    r = _login(user="auditor.demo", pw="Audita#2026", challenge=ch)
    assert r.status_code == 401 and "bloqueada" in r.text
    auth.INTENTOS.clear()


def test_client_credentials():
    ok = c.post("/oauth/token", data={"grant_type": "client_credentials"},
                auth=("integracion-secretaria", "secreto-demo-integracion-2026"))
    assert ok.status_code == 200 and ok.json()["scope"] == "rutas:generar"
    mal = c.post("/oauth/token", data={"grant_type": "client_credentials"}, auth=("integracion-secretaria", "x"))
    assert mal.status_code == 401


def test_jwks_publica():
    k = c.get("/.well-known/jwks.json").json()["keys"][0]
    assert k["alg"] == "RS256" and "d" not in k  # nunca exponer la parte privada
