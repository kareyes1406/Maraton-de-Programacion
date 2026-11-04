"""Pruebas de la auditoria y la cache sobre PostgreSQL real.

Se ejecutan solo si existe PG_TEST_URL (p. ej. un PostgreSQL local o embebido con `pgserver`):
    PG_TEST_URL=postgresql://... python -m pytest tests/test_postgres.py
"""
import os

import pytest

from rutas_service import auditoria, cache, db

PG = os.getenv("PG_TEST_URL")
pytestmark = pytest.mark.skipif(not PG, reason="sin PG_TEST_URL")


@pytest.fixture(autouse=True)
def usar_postgres(monkeypatch):
    import psycopg

    with psycopg.connect(PG, autocommit=True) as c:  # base limpia
        c.execute("DROP TABLE IF EXISTS auditoria CASCADE")
        c.execute("DROP TABLE IF EXISTS cache")
    monkeypatch.setattr(db, "DATABASE_URL", PG)
    monkeypatch.setattr(db, "ES_POSTGRES", True)
    monkeypatch.setattr(db, "_inicializado", False)
    yield
    monkeypatch.setattr(db, "_inicializado", False)


def test_cadena_en_postgres():
    usuario = {"sub": "medico.demo", "client_id": "frontend-rutas", "roles": ["medico"]}
    res = {"orden_visita": [{"codigo": "25535019", "nombre": "La Mesa"}], "distancia_total_km": 12.3}
    ids = [auditoria.registrar("RUTA_GENERADA", usuario, "10.0.0.1", {"alpha": 0.6}, {"x": [1, 2]}, res)
           for _ in range(3)]
    assert ids == sorted(ids) and len(set(ids)) == 3
    assert auditoria.verificar_cadena() == {"integra": True, "registros": 3, "ultimo_hash": auditoria.obtener(ids[-1])["hash"]}
    assert auditoria.obtener(ids[0])["parametros"] == {"alpha": 0.6}
    assert len(auditoria.listar(10, "RUTA_GENERADA")) == 3
    assert auditoria.visitas_recientes() == {"25535019": 3}


def test_postgres_bloquea_modificaciones():
    import psycopg

    auditoria.registrar("RUTA_GENERADA", {"sub": "x"}, None, {"a": 1}, {}, {})
    for q in ("UPDATE auditoria SET sub='otro'", "DELETE FROM auditoria", "TRUNCATE auditoria"):
        with psycopg.connect(PG) as c, pytest.raises(psycopg.errors.RaiseException):
            c.execute(q)


def test_cache_en_postgres():
    cache.set("k1", {"a": 1}, 60)
    cache.set("k1", {"a": 2}, 60)  # upsert
    assert cache.get("k1") == {"a": 2}
    cache.set("k2", [1], -1)
    assert cache.get("k2") is None and cache.get("k2", permitir_expirado=True) == [1]
