CREATE TABLE IF NOT EXISTS operaciones.conflicto_sincronizacion (
    id SERIAL PRIMARY KEY,
    id_local_origen VARCHAR(100) NOT NULL,
    codigo_usuario VARCHAR(100) NOT NULL REFERENCES seguridad.usuario(codigo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_incidente_backend INTEGER NULL REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE ON DELETE SET NULL,
    tipo_conflicto VARCHAR(50) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    regla_arbitraje VARCHAR(100) NULL,
    datos_locales_json TEXT NOT NULL,
    datos_servidor_json TEXT NULL,
    resolucion VARCHAR(50) NULL,
    observacion TEXT NULL,
    resuelto_por VARCHAR(100) NULL,
    fecha_deteccion TIMESTAMP NOT NULL,
    fecha_resolucion TIMESTAMP NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_conflicto_sincronizacion_estado'
          AND conrelid = 'operaciones.conflicto_sincronizacion'::regclass
    ) THEN
        ALTER TABLE operaciones.conflicto_sincronizacion
        ADD CONSTRAINT ck_conflicto_sincronizacion_estado
        CHECK (estado IN ('PENDIENTE', 'RESUELTO', 'DESCARTADO'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_conflicto_sync_usuario_estado
ON operaciones.conflicto_sincronizacion (codigo_usuario, estado);

CREATE INDEX IF NOT EXISTS ix_conflicto_sync_incidente_backend
ON operaciones.conflicto_sincronizacion (id_incidente_backend);
