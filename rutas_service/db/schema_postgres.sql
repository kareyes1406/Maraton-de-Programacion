-- Esquema PostgreSQL (referencia). El servicio lo crea automaticamente al iniciar (rutas_service/db.py)
-- cuando existe la variable DATABASE_URL; en local se usa SQLite con el mismo modelo.

-- Los campos JSON y la fecha se guardan como TEXT a proposito: el hash SHA-256 de la cadena de auditoria
-- se calcula sobre el texto canonico exacto, y JSONB/TIMESTAMPTZ normalizarian el contenido rompiendo
-- la verificacion de integridad.
CREATE TABLE IF NOT EXISTS auditoria (
    id             BIGSERIAL PRIMARY KEY,
    ts             TEXT NOT NULL,              -- ISO-8601 UTC
    evento         VARCHAR(30) NOT NULL,
    sub            VARCHAR(128),
    client_id      VARCHAR(64),
    roles          TEXT,                       -- JSON canonico
    ip             VARCHAR(64),
    parametros     TEXT,                       -- JSON canonico
    entradas_hash  CHAR(64),
    entradas       TEXT,                       -- JSON canonico
    resultado      TEXT,                       -- JSON canonico
    hash_anterior  CHAR(64) NOT NULL,
    hash           CHAR(64) NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_auditoria_evento_ts ON auditoria (evento, ts DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_sub ON auditoria (sub);

-- Tabla solo-anexar: se bloquean UPDATE, DELETE y TRUNCATE
CREATE OR REPLACE FUNCTION auditoria_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'auditoria es solo-anexar';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria;
CREATE TRIGGER trg_auditoria_inmutable BEFORE UPDATE OR DELETE OR TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION auditoria_inmutable();

-- Cache de respuestas de APIs externas (equivalente a Redis con expiracion)
CREATE TABLE IF NOT EXISTS cache (
    k   TEXT PRIMARY KEY,
    v   TEXT NOT NULL,
    exp DOUBLE PRECISION NOT NULL
);

-- Endurecimiento opcional: rol de aplicacion con minimo privilegio
-- CREATE ROLE rutas_app LOGIN PASSWORD '<gestor de secretos>';
-- GRANT SELECT, INSERT ON auditoria TO rutas_app;  GRANT USAGE ON SEQUENCE auditoria_id_seq TO rutas_app;
-- GRANT SELECT, INSERT, UPDATE ON cache TO rutas_app;
