-- Esquema equivalente para PostgreSQL (migracion desde SQLite en despliegue productivo).
-- La demo usa SQLite para no requerir instalacion; este script deja lista la ruta de migracion.

CREATE TABLE IF NOT EXISTS auditoria (
    id             BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    evento         VARCHAR(30) NOT NULL,
    sub            VARCHAR(128),
    client_id      VARCHAR(64),
    roles          JSONB,
    ip             INET,
    parametros     JSONB,
    entradas_hash  CHAR(64),
    entradas       JSONB,
    resultado      JSONB,
    hash_anterior  CHAR(64) NOT NULL,
    hash           CHAR(64) NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_auditoria_evento_ts ON auditoria (evento, ts DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_sub ON auditoria (sub);

-- Tabla solo-anexar: el rol de la aplicacion no puede modificar ni borrar
CREATE OR REPLACE FUNCTION auditoria_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'auditoria es solo-anexar';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria;
CREATE TRIGGER trg_auditoria_inmutable BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION auditoria_inmutable();

-- Rol de aplicacion con minimo privilegio
-- CREATE ROLE rutas_app LOGIN PASSWORD '<definir en gestor de secretos>';
-- GRANT SELECT, INSERT ON auditoria TO rutas_app;
-- GRANT USAGE ON SEQUENCE auditoria_id_seq TO rutas_app;
-- REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM rutas_app;

-- La tabla "cache" se reemplaza por Redis (SET clave valor EX ttl).
