"""Validacion de access tokens OAuth 2.0 (JWT RS256) emitidos por auth-service."""
from __future__ import annotations

import time
from collections import defaultdict, deque

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auditoria, config

_bearer = HTTPBearer(auto_error=False)
_jwks_cache = {"exp": 0.0, "client": None}


def _jwk_client() -> jwt.PyJWKClient:
    if not _jwks_cache["client"] or _jwks_cache["exp"] < time.time():
        _jwks_cache["client"] = jwt.PyJWKClient(f"{config.AUTH_URL}/.well-known/jwks.json", cache_keys=True)
        _jwks_cache["exp"] = time.time() + 3600
    return _jwks_cache["client"]


def llave_firma(token: str):
    """Separado para poder sustituirlo en pruebas."""
    return _jwk_client().get_signing_key_from_jwt(token).key


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def usuario_actual(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if not cred or cred.scheme.lower() != "bearer":
        raise HTTPException(401, "Token Bearer requerido", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(
            cred.credentials,
            llave_firma(cred.credentials),
            algorithms=["RS256"],          # nunca aceptar 'none' ni HS256
            audience=config.AUDIENCE,
            issuer=config.AUTH_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except (jwt.PyJWTError, httpx.HTTPError) as e:
        auditoria.registrar("TOKEN_INVALIDO", None, _ip(request), {"ruta": request.url.path, "error": type(e).__name__})
        raise HTTPException(401, "Token invalido o expirado", headers={"WWW-Authenticate": "Bearer"})
    claims["scopes"] = set((claims.get("scope") or "").split())
    return claims


def requiere(scope: str):
    def dep(request: Request, usuario: dict = Depends(usuario_actual)) -> dict:
        if scope not in usuario["scopes"]:
            auditoria.registrar(
                "ACCESO_DENEGADO", usuario, _ip(request), {"ruta": request.url.path, "scope_requerido": scope}
            )
            raise HTTPException(403, f"Permiso insuficiente: se requiere '{scope}'")
        return usuario

    return dep


# --------------------------------------------------------- limite de peticiones por usuario
_ventanas: dict[str, deque] = defaultdict(deque)


def limitar(usuario: dict):
    ahora, v = time.time(), _ventanas[usuario["sub"]]
    while v and v[0] < ahora - 60:
        v.popleft()
    if len(v) >= config.RATE_LIMIT_POR_MIN:
        raise HTTPException(429, "Demasiadas solicitudes, intente en un minuto")
    v.append(ahora)
