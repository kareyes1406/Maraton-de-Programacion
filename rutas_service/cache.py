"""Cache persistente de respuestas de APIs externas (tabla `cache` en SQLite o PostgreSQL).

Permite que la demo siga funcionando sin internet una vez consultado un municipio
(misma funcion que cumpliria Redis en un despliegue de mayor escala).
"""
import json
import threading
import time
from contextlib import closing

from . import db

_lock = threading.Lock()


def get(key: str, permitir_expirado: bool = False):
    with _lock, closing(db.conectar()) as c, c:
        row = c.execute(db.sql("SELECT v, exp FROM cache WHERE k=?"), (key,)).fetchone()
    if not row:
        return None
    if row[1] < time.time() and not permitir_expirado:
        return None
    return json.loads(row[0])


def set(key: str, value, ttl: int):
    with _lock, closing(db.conectar()) as c, c:
        c.execute(
            db.sql("INSERT INTO cache (k, v, exp) VALUES (?,?,?) "
                   "ON CONFLICT (k) DO UPDATE SET v = excluded.v, exp = excluded.exp"),
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl),
        )
