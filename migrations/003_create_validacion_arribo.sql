CREATE TABLE IF NOT EXISTS operaciones.validacion_arribo (
    id SERIAL PRIMARY KEY,
    id_incidente INTEGER NOT NULL REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_asignacion INTEGER NOT NULL REFERENCES operaciones.asignacion(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    codigo_pin VARCHAR(6) NOT NULL,
    qr_token VARCHAR(100) NOT NULL,
    fecha_generacion TIMESTAMP NOT NULL,
    fecha_expiracion TIMESTAMP NOT NULL,
    usado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_uso TIMESTAMP NULL,
    intentos INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_validacion_arribo_incidente
ON operaciones.validacion_arribo (id_incidente);

CREATE INDEX IF NOT EXISTS ix_validacion_arribo_asignacion
ON operaciones.validacion_arribo (id_asignacion);

CREATE UNIQUE INDEX IF NOT EXISTS ux_validacion_arribo_qr_token
ON operaciones.validacion_arribo (qr_token);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_validacion_arribo_intentos_nonnegative'
    ) THEN
        ALTER TABLE operaciones.validacion_arribo
        ADD CONSTRAINT ck_validacion_arribo_intentos_nonnegative
        CHECK (intentos >= 0);
    END IF;
END $$;
