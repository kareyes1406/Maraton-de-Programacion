"""Verifica la configuracion segura de produccion del auth-service (secretos solo por entorno)."""
import importlib
import sys

import pytest


def _cargar_auth(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("auth_service.main", None)
    return importlib.import_module("auth_service.main")


@pytest.fixture(autouse=True)
def restaurar():
    yield
    sys.modules.pop("auth_service.main", None)


def test_produccion_exige_https(monkeypatch):
    with pytest.raises(RuntimeError):
        _cargar_auth(monkeypatch, ENTORNO="produccion", AUTH_ISSUER="http://inseguro", FRONTEND_URL="https://app.test")


def test_produccion_deshabilita_credenciales_demo(monkeypatch):
    m = _cargar_auth(monkeypatch, ENTORNO="produccion", AUTH_ISSUER="https://auth.test", FRONTEND_URL="https://app.test",
                     AUTH_PASSWORD_MEDICO_DEMO="Clave-Segura-2026!")
    assert set(m.USUARIOS) == {"medico.demo"}           # los demas usuarios quedan deshabilitados
    assert "integracion-secretaria" not in m.CLIENTES    # sin secreto en el entorno, el cliente no existe
    assert m.CLIENTES["frontend-rutas"]["redirect_uris"] == ["https://app.test/"]  # sin localhost en produccion
    assert m.ALLOWED_ORIGINS == ["https://app.test"]


def test_produccion_rechaza_contrasena_corta(monkeypatch):
    with pytest.raises(RuntimeError):
        _cargar_auth(monkeypatch, ENTORNO="produccion", AUTH_ISSUER="https://auth.test", FRONTEND_URL="https://app.test",
                     AUTH_PASSWORD_MEDICO_DEMO="corta")
