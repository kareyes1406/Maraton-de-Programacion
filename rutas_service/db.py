"""Capa de acceso a datos: PostgreSQL en la nube (DATABASE_URL) o SQLite en local.

Las consultas se escriben con marcadores '?' y se adaptan a '%s' para PostgreSQL.
Siempre se usan consultas parametrizadas (nunca concatenacion de valores).
"""
from __future__ import annotations

import os
import sqlite3
import threading

from . import config

DATABASE_URL = os.getenv("DATABASE_URL", "")
ES_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
MOTOR = "postgresql" if ES_POSTGRES else "sqlite"

_init_lock = threading.Lock()
_inicializado = False

_DDL_SQLITE = [
    """CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, evento TEXT NOT NULL, sub TEXT, client_id TEXT, roles TEXT, ip TEXT,
        parametros TEXT, entradas_hash TEXT, entradas TEXT, resultado TEXT,
        hash_anterior TEXT NOT NULL, hash TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS aud_no_update BEFORE UPDATE ON auditoria
       BEGIN SELECT RAISE(ABORT, 'auditoria es solo-anexar'); END""",
    """CREATE TRIGGER IF NOT EXISTS aud_no_delete BEFORE DELETE ON auditoria
       BEGIN SELECT RAISE(ABORT, 'auditoria es solo-anexar'); END""",
    "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL, exp REAL NOT NULL)",
]

# Los campos JSON se guardan como TEXT: el hash de la cadena se calcula sobre el texto canonico exacto,
# y JSONB reordenaria/normalizaria el contenido, rompiendo la verificacion de integridad.
_DDL_POSTGRES = [
    """CREATE TABLE IF NOT EXISTS auditoria (
        id BIGSERIAL PRIMARY KEY,
        ts TEXT NOT NULL, evento VARCHAR(30) NOT NULL, sub VARCHAR(128), client_id VARCHAR(64), roles TEXT,
        ip VARCHAR(64), parametros TEXT, entradas_hash CHAR(64), entradas TEXT, resultado TEXT,
        hash_anterior CHAR(64) NOT NULL, hash CHAR(64) NOT NULL UNIQUE)""",
    "CREATE INDEX IF NOT EXISTS idx_auditoria_evento_ts ON auditoria (evento, ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auditoria_sub ON auditoria (sub)",
    """CREATE OR REPLACE FUNCTION auditoria_inmutable() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'auditoria es solo-anexar'; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria",
    """CREATE TRIGGER trg_auditoria_inmutable BEFORE UPDATE OR DELETE OR TRUNCATE ON auditoria
       FOR EACH STATEMENT EXECUTE FUNCTION auditoria_inmutable()""",
    "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL, exp DOUBLE PRECISION NOT NULL)",
]


def _abrir():
    if ES_POSTGRES:
        import psycopg  # solo se requiere en la nube

        return psycopg.connect(DATABASE_URL, connect_timeout=10)
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(config.DB_PATH)


def _inicializar():
    global _inicializado
    with _init_lock:
        if _inicializado:
            return
        c = _abrir()
        try:
            with c:
                if ES_POSTGRES:
                    # evita carreras si varias instancias arrancan a la vez
                    c.execute("SELECT pg_advisory_xact_lock(4242)")
                for ddl in (_DDL_POSTGRES if ES_POSTGRES else _DDL_SQLITE):
                    c.execute(ddl)
        finally:
            c.close()
        _inicializado = True


def conectar():
    """Conexion nueva. Usar como `with db.conectar() as c:` (confirma la transaccion al salir)."""
    _inicializar()
    return _abrir()


def sql(consulta: str) -> str:
    return consulta.replace("?", "%s") if ES_POSTGRES else consulta
