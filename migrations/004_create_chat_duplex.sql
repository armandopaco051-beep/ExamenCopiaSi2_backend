CREATE TABLE IF NOT EXISTS operaciones.chat_incidente (
    id SERIAL PRIMARY KEY,
    id_incidente INTEGER NOT NULL REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL,
    fecha_cierre TIMESTAMP NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_incidente_incidente
ON operaciones.chat_incidente (id_incidente);

CREATE TABLE IF NOT EXISTS operaciones.mensaje_chat (
    id SERIAL PRIMARY KEY,
    id_chat INTEGER NOT NULL REFERENCES operaciones.chat_incidente(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_incidente INTEGER NOT NULL REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    emisor_id VARCHAR(100) NOT NULL,
    emisor_tipo VARCHAR(20) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo_mensaje VARCHAR(20) NOT NULL DEFAULT 'texto',
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_hora TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_mensaje_chat_chat_fecha
ON operaciones.mensaje_chat (id_chat, fecha_hora);

CREATE INDEX IF NOT EXISTS ix_mensaje_chat_incidente
ON operaciones.mensaje_chat (id_incidente);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_mensaje_chat_emisor_tipo'
    ) THEN
        ALTER TABLE operaciones.mensaje_chat
        ADD CONSTRAINT ck_mensaje_chat_emisor_tipo
        CHECK (emisor_tipo IN ('cliente', 'tecnico'));
    END IF;
END $$;
