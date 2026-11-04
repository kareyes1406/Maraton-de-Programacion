"""Registro de auditoria encadenado (append-only, tipo blockchain simple).

Cada registro guarda quien, cuando, con que parametros, con que datos de entrada y que resultado
se genero, mas el hash del registro anterior. Si alguien modifica o borra un registro, la cadena
deja de verificar.
"""
from __future__ import annotations

import hashlib
import json
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone

from . import db

_lock = threading.Lock()
GENESIS = "0" * 64
CAMPOS = ("id", "ts", "evento", "sub", "client_id", "roles", "ip", "parametros", "entradas_hash",
          "entradas", "resultado", "hash_anterior", "hash")


@contextmanager
def _conn():
    """Transaccion sobre SQLite o PostgreSQL (la tabla y sus triggers solo-anexar los crea db.py)."""
    with closing(db.conectar()) as c, c:
        yield c


def _canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_registro(r: dict) -> str:
    cuerpo = {k: r[k] for k in CAMPOS if k not in ("id", "hash")}
    return hashlib.sha256(_canon(cuerpo).encode()).hexdigest()


def registrar(evento: str, usuario: dict | None, ip: str | None, parametros=None, entradas=None, resultado=None) -> int:
    usuario = usuario or {}
    with _lock, _conn() as c:
        if db.ES_POSTGRES:
            # serializa la escritura entre instancias: dos registros no pueden encadenarse al mismo anterior
            c.execute("LOCK TABLE auditoria IN SHARE ROW EXCLUSIVE MODE")
        fila = c.execute("SELECT hash FROM auditoria ORDER BY id DESC LIMIT 1").fetchone()
        r = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "evento": evento,
            "sub": usuario.get("sub"),
            "client_id": usuario.get("client_id"),
            "roles": _canon(usuario.get("roles", [])),
            "ip": ip,
            "parametros": _canon(parametros) if parametros is not None else None,
            "entradas_hash": hashlib.sha256(_canon(entradas).encode()).hexdigest() if entradas is not None else None,
            "entradas": _canon(entradas) if entradas is not None else None,
            "resultado": _canon(resultado) if resultado is not None else None,
            "hash_anterior": fila[0] if fila else GENESIS,
        }
        r["hash"] = _hash_registro(r)
        cur = c.execute(
            db.sql(f"INSERT INTO auditoria ({','.join(CAMPOS[1:])}) VALUES ({','.join('?' * (len(CAMPOS) - 1))})"
                   + (" RETURNING id" if db.ES_POSTGRES else "")),
            tuple(r[k] for k in CAMPOS[1:]),
        )
        return cur.fetchone()[0] if db.ES_POSTGRES else cur.lastrowid


def _fila_a_dict(fila, completo: bool) -> dict:
    r = dict(zip(CAMPOS, fila))
    for k in ("roles", "parametros", "entradas", "resultado"):
        if r[k] is not None:
            r[k] = json.loads(r[k])
    if not completo:
        r.pop("entradas", None)
        res = r.pop("resultado", None) or {}
        r["resumen"] = {
            "veredas": [p["nombre"] for p in res.get("orden_visita", [])],
            "distancia_total_km": res.get("distancia_total_km"),
        } if res else None
    return r


def listar(limite: int = 50, evento: str | None = None) -> list[dict]:
    q, args = f"SELECT {','.join(CAMPOS)} FROM auditoria", []
    if evento:
        q += " WHERE evento=?"
        args.append(evento)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    with _conn() as c:
        return [_fila_a_dict(f, completo=False) for f in c.execute(db.sql(q), args).fetchall()]


def obtener(id_: int) -> dict | None:
    with _conn() as c:
        f = c.execute(db.sql(f"SELECT {','.join(CAMPOS)} FROM auditoria WHERE id=?"), (id_,)).fetchone()
    return _fila_a_dict(f, completo=True) if f else None


def verificar_cadena() -> dict:
    with _conn() as c:
        filas = c.execute(f"SELECT {','.join(CAMPOS)} FROM auditoria ORDER BY id").fetchall()
    previo = GENESIS
    for f in filas:
        r = dict(zip(CAMPOS, f))
        if r["hash_anterior"] != previo or _hash_registro(r) != r["hash"]:
            return {"integra": False, "registros": len(filas), "primer_registro_alterado": r["id"]}
        previo = r["hash"]
    return {"integra": True, "registros": len(filas), "ultimo_hash": previo}


def visitas_recientes(dias: int = 30) -> dict:
    """Cuantas veces se programo cada vereda en rutas recientes (para el factor de equidad)."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    conteo: dict[str, int] = {}
    with _conn() as c:
        for (res,) in c.execute(
            db.sql("SELECT resultado FROM auditoria WHERE evento='RUTA_GENERADA' AND ts>=?"), (desde,)
        ):
            for p in json.loads(res or "{}").get("orden_visita", []):
                conteo[p["codigo"]] = conteo.get(p["codigo"], 0) + 1
    return conteo
