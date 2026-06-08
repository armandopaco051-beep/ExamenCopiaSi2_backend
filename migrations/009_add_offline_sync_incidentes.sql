ALTER TABLE operaciones.incidente
ADD COLUMN IF NOT EXISTS id_local_origen VARCHAR(100) NULL;

ALTER TABLE operaciones.incidente
ADD COLUMN IF NOT EXISTS origen_registro VARCHAR(20) NOT NULL DEFAULT 'ONLINE';

ALTER TABLE operaciones.incidente
ADD COLUMN IF NOT EXISTS fecha_creacion_local TIMESTAMP NULL;

ALTER TABLE operaciones.incidente
ADD COLUMN IF NOT EXISTS version_local INTEGER NULL;

ALTER TABLE operaciones.incidente
ADD COLUMN IF NOT EXISTS estado_local_origen VARCHAR(30) NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_incidente_origen_registro'
          AND conrelid = 'operaciones.incidente'::regclass
    ) THEN
        ALTER TABLE operaciones.incidente
        ADD CONSTRAINT ck_incidente_origen_registro
        CHECK (origen_registro IN ('ONLINE', 'OFFLINE'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_incidente_usuario_id_local_origen
ON operaciones.incidente (codigo_usuario, id_local_origen)
WHERE id_local_origen IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_incidente_origen_registro
ON operaciones.incidente (origen_registro);
