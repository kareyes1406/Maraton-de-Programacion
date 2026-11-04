"""Cache persistente simple (SQLite) para respuestas de APIs externas.

Permite que la demo siga funcionando sin internet una vez consultado un municipio
(misma funcion que cumpliria Redis en un despliegue productivo).
"""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()


def _conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL, exp REAL NOT NULL)")
    return c


def get(key: str, permitir_expirado: bool = False):
    with _lock, _conn() as c:
        row = c.execute("SELECT v, exp FROM cache WHERE k=?", (key,)).fetchone()
    if not row:
        return None
    if row[1] < time.time() and not permitir_expirado:
        return None
    return json.loads(row[0])


def set(key: str, value, ttl: int):
    with _lock, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache (k, v, exp) VALUES (?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl),
        )
