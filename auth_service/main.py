"""
auth-service: servidor de autorizacion OAuth 2.0 minimo para la demo.

Flujos soportados:
  * authorization_code + PKCE (S256)  -> frontend web (cliente publico)
  * client_credentials                 -> integraciones maquina a maquina (cliente confidencial)

Los access tokens son JWT firmados con RS256. Los servicios de recursos validan la
firma con la llave publica expuesta en /.well-known/jwks.json (nunca comparten secretos).
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

BASE = Path(__file__).parent
KEYS_DIR = Path(os.getenv("AUTH_KEYS_DIR", BASE / "keys"))
SEED_FILE = Path(os.getenv("AUTH_SEED_FILE", BASE / "seed_demo.json"))
ENTORNO = os.getenv("ENTORNO", "desarrollo")  # "produccion" en la nube
ISSUER = os.getenv("AUTH_ISSUER", os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8001")).rstrip("/")
AUDIENCE = "rutas-api"
TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", "900"))  # 15 minutos
CODE_TTL = 60
MAX_INTENTOS = 5
BLOQUEO_SEG = 300
# URL publica del frontend (rutas-service): se agrega como redirect_uri y origen permitido
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
_origenes = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
ALLOWED_ORIGINS = sorted({o.strip().rstrip("/") for o in _origenes + ([FRONTEND_URL] if FRONTEND_URL else []) if o.strip()})

if ENTORNO == "produccion" and not (ISSUER.startswith("https://") and FRONTEND_URL.startswith("https://")):
    raise RuntimeError("En produccion AUTH_ISSUER y FRONTEND_URL deben usar HTTPS")

# Rol -> permisos (scopes). Principio de minimo privilegio.
ROL_SCOPES = {
    "medico": ["veredas:leer", "rutas:generar"],
    "coordinador": ["veredas:leer", "rutas:generar", "auditoria:leer"],
    "auditor": ["veredas:leer", "auditoria:leer"],
}


# ---------------------------------------------------------------- llaves RSA
def _cargar_o_crear_llave():
    pem = os.getenv("AUTH_PRIVATE_KEY_PEM")  # en la nube: secreto inyectado por variable de entorno
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv_path = KEYS_DIR / "private.pem"
    if pem:
        key = serialization.load_pem_private_key(pem.replace("\\n", "\n").encode(), password=None)
    elif priv_path.exists():
        key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    pub = key.public_key()
    kid = hashlib.sha256(
        pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    ).hexdigest()[:16]
    return key, pub, kid


def _b64u(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


PRIVATE_KEY, PUBLIC_KEY, KID = _cargar_o_crear_llave()


# ---------------------------------------------------------------- usuarios / clientes
def _hash(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10))


def _env_secreto(prefijo: str, ident: str) -> str | None:
    """AUTH_PASSWORD_MEDICO_DEMO, AUTH_SECRET_INTEGRACION_SECRETARIA, ..."""
    return os.getenv(f"{prefijo}_{ident.upper().replace('.', '_').replace('-', '_')}")


def _cargar_seed():
    """Usuarios y clientes. En produccion las contrasenas y secretos SOLO vienen de variables de entorno:
    las credenciales de demostracion publicadas en el repositorio quedan deshabilitadas."""
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    prod = ENTORNO == "produccion"
    usuarios = {}
    for u in data["usuarios"]:
        pw = _env_secreto("AUTH_PASSWORD", u["username"]) or (None if prod else u["password"])
        if not pw:
            continue  # usuario deshabilitado: sin secreto configurado en produccion
        if prod and len(pw) < 12:
            raise RuntimeError(f"La contrasena de {u['username']} debe tener al menos 12 caracteres")
        usuarios[u["username"]] = {
            "hash": _hash(pw),  # la contrasena en claro no se conserva en memoria
            "nombre": u["nombre"],
            "roles": u["roles"],
        }
    clientes = {}
    for c in data["clientes"]:
        c = dict(c)
        if c.get("tipo") == "publico" and FRONTEND_URL:
            c["redirect_uris"] = c.get("redirect_uris", []) + [f"{FRONTEND_URL}/"]
        if "client_secret" in c:
            sec = _env_secreto("AUTH_SECRET", c["client_id"]) or (None if prod else c["client_secret"])
            c.pop("client_secret")
            if not sec:
                continue
            c["secret_hash"] = _hash(sec)
        clientes[c["client_id"]] = c
    return usuarios, clientes


USUARIOS, CLIENTES = _cargar_seed()
CODIGOS: dict[str, dict] = {}       # codigo de autorizacion -> datos (un solo uso)
INTENTOS: dict[str, list] = {}      # username -> [fallos, bloqueado_hasta]
# hash bcrypt valido para comparar cuando el usuario no existe (evita enumeracion por tiempo)
_HASH_FALSO = _hash("usuario-inexistente")


# ---------------------------------------------------------------- app
app = FastAPI(title="auth-service (OAuth 2.0)", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":  # detras del proxy TLS de la nube (uvicorn --proxy-headers)
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # form-action tambien aplica a la redireccion 303 hacia el cliente: se permiten solo sus origenes
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        f"form-action 'self' {' '.join(ALLOWED_ORIGINS)}; frame-ancestors 'none'"
    )
    return resp


def _emitir_token(sub: str, scopes: list[str], client_id: str, extra: dict | None = None) -> dict:
    ahora = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": sub,
        "client_id": client_id,
        "scope": " ".join(sorted(set(scopes))),
        "iat": ahora,
        "nbf": ahora,
        "exp": ahora + TOKEN_TTL,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        claims.update(extra)
    token = jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})
    return {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_TTL, "scope": claims["scope"]}


def _error_oauth(error: str, desc: str, status: int = 400):
    return JSONResponse({"error": error, "error_description": desc}, status_code=status)


@app.get("/.well-known/jwks.json")
def jwks():
    nums = PUBLIC_KEY.public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": _b64u(nums.n), "e": _b64u(nums.e)}]}


@app.get("/.well-known/oauth-authorization-server")
def metadata():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/oauth/authorize",
        "token_endpoint": f"{ISSUER}/oauth/token",
        "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": sorted({s for v in ROL_SCOPES.values() for s in v}),
    }


@app.get("/health")
def health():
    return {"status": "ok", "servicio": "auth-service"}


# ---------------------------------------------------------------- authorization code + PKCE
def _validar_solicitud_autorizacion(client_id, redirect_uri, response_type, code_challenge, method):
    cliente = CLIENTES.get(client_id)
    if not cliente or cliente.get("tipo") != "publico":
        raise HTTPException(400, "client_id invalido")
    # Nunca redirigir a una URI no registrada (evita robo del codigo)
    if redirect_uri not in cliente.get("redirect_uris", []):
        raise HTTPException(400, "redirect_uri no registrada")
    if response_type != "code":
        raise HTTPException(400, "response_type debe ser 'code'")
    if method != "S256" or not code_challenge or not (43 <= len(code_challenge) <= 128):
        raise HTTPException(400, "PKCE obligatorio con code_challenge_method=S256")


LOGIN_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Ingreso - Rutas de Salud Rural</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap">
<style>
:root{{--fondo:#f4f7f6;--sup:#fff;--txt:#0f1f18;--suave:#4a5d55;--borde:#b6c8bf;--prim:#1a7350;--prim-h:#135c3f;--sobre:#fff;
--suave-bg:#e2f1ea;--prim-txt:#145a3e;--err-bg:#fdecea;--err:#b42318;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--fondo:#0b1411;--sup:#13201b;--txt:#e6efe9;--suave:#a7b9b0;--borde:#3b5348;--prim:#3fb383;
--prim-h:#5cc79a;--sobre:#04150d;--suave-bg:#173a2b;--prim-txt:#86dcb4;--err-bg:#3b1515;--err:#fca5a5;color-scheme:dark}}}}
*{{box-sizing:border-box}}
body{{font-family:"Atkinson Hyperlegible",system-ui,Segoe UI,Roboto,sans-serif;background:var(--fondo);margin:0;display:grid;place-items:center;
min-height:100vh;padding:1rem;color:var(--txt);line-height:1.5}}
main{{background:var(--sup);padding:clamp(1.5rem,5vw,2.25rem);border-radius:16px;border:1px solid var(--borde);
box-shadow:0 8px 30px rgba(0,0,0,.08);width:min(400px,100%)}}
.ic{{width:52px;height:52px;border-radius:14px;display:grid;place-items:center;background:var(--suave-bg);color:var(--prim-txt);margin-bottom:1rem}}
.ic svg{{width:28px;height:28px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}
h1{{font-size:1.3rem;margin:0 0 .25rem;line-height:1.25}} p{{color:var(--suave);margin:.25rem 0 1.25rem;font-size:.95rem}}
label{{display:block;font-weight:700;margin:1rem 0 .35rem}}
input{{width:100%;min-height:44px;padding:.65rem .75rem;border:1px solid var(--borde);border-radius:8px;font:inherit;
background:var(--sup);color:var(--txt)}}
input:hover{{border-color:var(--prim)}}
:focus-visible{{outline:3px solid #f2b705;outline-offset:2px}}
button{{margin-top:1.5rem;width:100%;min-height:44px;padding:.75rem;border:0;border-radius:8px;background:var(--prim);color:var(--sobre);
font:inherit;font-weight:700;cursor:pointer;transition:background-color .15s}}
button:hover{{background:var(--prim-h)}}
.err{{display:flex;gap:.5rem;align-items:flex-start;background:var(--err-bg);color:var(--err);padding:.7rem .9rem;border-radius:8px;margin-bottom:.5rem;font-weight:700}}
small{{display:block;margin-top:1.25rem;color:var(--suave);font-size:.85rem;text-align:center}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style></head><body><main>
<div class="ic" aria-hidden="true"><svg viewBox="0 0 24 24"><rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
<h1>Rutas de atención en salud rural</h1>
<p>Ingrese con su usuario institucional (servidor OAuth 2.0).</p>
{error}
<form method="post" action="/oauth/authorize">
{hidden}
<label for="u">Usuario</label><input id="u" name="username" required maxlength="64" autofocus autocomplete="username"
 autocapitalize="none" spellcheck="false">
<label for="p">Contraseña</label><input id="p" name="password" type="password" required maxlength="128" autocomplete="current-password">
<button type="submit">Ingresar</button>
</form>
<small>Acceso con autorización de código + PKCE. Solo datos simulados.</small>
</main></body></html>"""


def _render_login(params: dict, error: str = "") -> HTMLResponse:
    hidden = "\n".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v or "")}">' for k, v in params.items()
    )
    err = f'<div class="err" role="alert">{html.escape(error)}</div>' if error else ""
    return HTMLResponse(LOGIN_HTML.format(hidden=hidden, error=err), status_code=401 if error else 200)


@app.get("/oauth/authorize", response_class=HTMLResponse)
def authorize_form(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    response_type: str = "code",
    code_challenge_method: str = "S256",
    state: str = "",
    scope: str = "",
):
    _validar_solicitud_autorizacion(client_id, redirect_uri, response_type, code_challenge, code_challenge_method)
    return _render_login(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "response_type": response_type,
            "state": state[:256],
            "scope": scope[:256],
        }
    )


@app.post("/oauth/authorize")
def authorize_submit(
    username: str = Form(..., max_length=64),
    password: str = Form(..., max_length=128),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    response_type: str = Form("code"),
    state: str = Form(""),
    scope: str = Form(""),
):
    _validar_solicitud_autorizacion(client_id, redirect_uri, response_type, code_challenge, code_challenge_method)
    params = {
        "client_id": client_id, "redirect_uri": redirect_uri, "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method, "response_type": response_type,
        "state": state, "scope": scope,
    }
    ahora = time.time()
    fallos, bloqueado_hasta = INTENTOS.get(username, [0, 0])
    if bloqueado_hasta > ahora:
        return _render_login(params, "Cuenta bloqueada temporalmente por intentos fallidos. Intente en unos minutos.")

    usuario = USUARIOS.get(username)
    ok = bcrypt.checkpw(password.encode(), usuario["hash"] if usuario else _HASH_FALSO) and usuario is not None
    if not ok:
        fallos += 1
        INTENTOS[username] = [fallos, ahora + BLOQUEO_SEG if fallos >= MAX_INTENTOS else 0]
        return _render_login(params, "Usuario o contraseña incorrectos.")  # mensaje generico
    INTENTOS.pop(username, None)

    permitidos = {s for r in usuario["roles"] for s in ROL_SCOPES.get(r, [])}
    pedidos = set(scope.split()) if scope else permitidos
    codigo = secrets.token_urlsafe(32)
    CODIGOS[codigo] = {
        "username": username,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "scopes": sorted(pedidos & permitidos),
        "exp": ahora + CODE_TTL,
    }
    q = {"code": codigo}
    if state:
        q["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(q)}", status_code=303)


# ---------------------------------------------------------------- token endpoint
def _credenciales_basic(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            cid, _, sec = base64.b64decode(auth[6:]).decode().partition(":")
            return cid, sec
        except Exception:
            return None, None
    return None, None


@app.post("/oauth/token")
def token(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    scope: str | None = Form(None),
):
    if grant_type == "authorization_code":
        datos = CODIGOS.pop(code or "", None)  # un solo uso
        if not datos or datos["exp"] < time.time():
            return _error_oauth("invalid_grant", "codigo invalido o expirado")
        if datos["client_id"] != client_id or datos["redirect_uri"] != redirect_uri:
            return _error_oauth("invalid_grant", "client_id o redirect_uri no coinciden")
        if not code_verifier or not (43 <= len(code_verifier) <= 128):
            return _error_oauth("invalid_grant", "code_verifier invalido")
        calculado = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
        if not secrets.compare_digest(calculado, datos["code_challenge"]):
            return _error_oauth("invalid_grant", "PKCE: code_verifier no corresponde")
        usuario = USUARIOS[datos["username"]]
        return _emitir_token(
            datos["username"], datos["scopes"], client_id,
            {"roles": usuario["roles"], "name": usuario["nombre"]},
        )

    if grant_type == "client_credentials":
        b_id, b_sec = _credenciales_basic(request)
        cid, sec = b_id or client_id, b_sec or client_secret
        cliente = CLIENTES.get(cid or "")
        if not cliente or cliente.get("tipo") != "confidencial" or not sec or \
                not bcrypt.checkpw(sec.encode(), cliente["secret_hash"]):
            return _error_oauth("invalid_client", "autenticacion de cliente fallida", 401)
        permitidos = set(cliente.get("scopes", []))
        pedidos = set(scope.split()) if scope else permitidos
        return _emitir_token(f"client:{cid}", sorted(pedidos & permitidos), cid, {"roles": ["sistema"]})

    return _error_oauth("unsupported_grant_type", "use authorization_code o client_credentials")
