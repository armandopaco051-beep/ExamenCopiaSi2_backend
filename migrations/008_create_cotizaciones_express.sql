INSERT INTO catalogo.estado_incidente (id, nombre)
VALUES (8, 'En cotizacion')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;

DO $$
DECLARE
    secuencia TEXT;
BEGIN
    secuencia := pg_get_serial_sequence('catalogo.estado_incidente', 'id');
    IF secuencia IS NOT NULL THEN
        PERFORM setval(
            secuencia,
            GREATEST((SELECT COALESCE(MAX(id), 1) FROM catalogo.estado_incidente), 1),
            TRUE
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS operaciones.solicitud_cotizacion (
    id SERIAL PRIMARY KEY,
    id_incidente INTEGER NOT NULL
        REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    ronda INTEGER NOT NULL DEFAULT 1 CHECK (ronda > 0),
    estado VARCHAR(30) NOT NULL DEFAULT 'ABIERTA'
        CHECK (estado IN (
            'ABIERTA',
            'CON_RESPUESTAS',
            'FINALIZADA',
            'VENCIDA',
            'CANCELADA'
        )),
    radio_busqueda_km NUMERIC(10, 2) NOT NULL
        CHECK (radio_busqueda_km >= 0),
    max_talleres INTEGER NOT NULL DEFAULT 3
        CONSTRAINT ck_solicitud_cotizacion_max_talleres
        CHECK (max_talleres BETWEEN 1 AND 3),
    tiempo_limite_minutos INTEGER NOT NULL DEFAULT 10
        CHECK (tiempo_limite_minutos BETWEEN 1 AND 60),
    fecha_solicitud TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_vencimiento TIMESTAMP NOT NULL,
    fecha_finalizacion TIMESTAMP NULL,
    id_cotizacion_aceptada INTEGER NULL,
    observacion TEXT NULL,
    CONSTRAINT uq_solicitud_cotizacion_incidente_ronda
        UNIQUE (id_incidente, ronda)
);

CREATE TABLE IF NOT EXISTS operaciones.cotizacion_taller (
    id SERIAL PRIMARY KEY,
    id_solicitud INTEGER NOT NULL
        REFERENCES operaciones.solicitud_cotizacion(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    id_taller INTEGER NOT NULL
        REFERENCES talleres.taller(codigo)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    id_tecnico VARCHAR(100) NULL
        REFERENCES talleres.tecnico(codigo)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'INVITADA'
        CHECK (estado IN (
            'INVITADA',
            'ENVIADA',
            'ACEPTADA',
            'RECHAZADA',
            'VENCIDA',
            'AJUSTE_SOLICITADO',
            'RETIRADA'
        )),
    distancia_km NUMERIC(10, 2) NOT NULL CHECK (distancia_km >= 0),
    monto_estimado NUMERIC(10, 2) NULL CHECK (monto_estimado > 0),
    tiempo_llegada_minutos INTEGER NULL CHECK (tiempo_llegada_minutos > 0),
    tiempo_reparacion_minutos INTEGER NULL CHECK (tiempo_reparacion_minutos > 0),
    descripcion_servicio TEXT NULL,
    observacion TEXT NULL,
    fecha_invitacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_respuesta TIMESTAMP NULL,
    fecha_vencimiento TIMESTAMP NOT NULL,
    CONSTRAINT uq_cotizacion_solicitud_taller
        UNIQUE (id_solicitud, id_taller)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_solicitud_cotizacion_aceptada'
          AND conrelid = 'operaciones.solicitud_cotizacion'::regclass
    ) THEN
        ALTER TABLE operaciones.solicitud_cotizacion
            ADD CONSTRAINT fk_solicitud_cotizacion_aceptada
            FOREIGN KEY (id_cotizacion_aceptada)
            REFERENCES operaciones.cotizacion_taller(id)
            ON UPDATE CASCADE
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_solicitud_cotizacion_incidente
    ON operaciones.solicitud_cotizacion(id_incidente);

CREATE INDEX IF NOT EXISTS idx_solicitud_cotizacion_estado
    ON operaciones.solicitud_cotizacion(estado);

CREATE INDEX IF NOT EXISTS idx_cotizacion_taller_solicitud
    ON operaciones.cotizacion_taller(id_solicitud);

CREATE INDEX IF NOT EXISTS idx_cotizacion_taller_taller_estado
    ON operaciones.cotizacion_taller(id_taller, estado);

DO $$
BEGIN
    ALTER TABLE operaciones.solicitud_cotizacion
        DROP CONSTRAINT IF EXISTS solicitud_cotizacion_max_talleres_check;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_solicitud_cotizacion_max_talleres'
          AND conrelid = 'operaciones.solicitud_cotizacion'::regclass
    ) THEN
        ALTER TABLE operaciones.solicitud_cotizacion
            ADD CONSTRAINT ck_solicitud_cotizacion_max_talleres
            CHECK (max_talleres BETWEEN 1 AND 3);
    END IF;
END $$;
