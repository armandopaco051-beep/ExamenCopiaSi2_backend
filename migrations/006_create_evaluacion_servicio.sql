CREATE TABLE IF NOT EXISTS operaciones.evaluacion_servicio (
    id SERIAL PRIMARY KEY,
    id_incidente INTEGER NOT NULL UNIQUE REFERENCES operaciones.incidente(codigo) ON UPDATE CASCADE ON DELETE CASCADE,
    id_asignacion INTEGER NOT NULL REFERENCES operaciones.asignacion(id) ON UPDATE CASCADE ON DELETE CASCADE,
    codigo_cliente VARCHAR(100) NOT NULL REFERENCES seguridad.usuario(codigo) ON UPDATE CASCADE ON DELETE CASCADE,
    codigo_tecnico VARCHAR(100) NOT NULL REFERENCES talleres.tecnico(codigo) ON UPDATE CASCADE ON DELETE CASCADE,
    id_taller INTEGER NOT NULL REFERENCES talleres.taller(codigo) ON UPDATE CASCADE ON DELETE CASCADE,
    calificacion INTEGER NOT NULL,
    puntualidad INTEGER NULL,
    trato INTEGER NULL,
    solucion INTEGER NULL,
    precio INTEGER NULL,
    comentario TEXT NULL,
    fecha_evaluacion TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluacion_servicio_tecnico
    ON operaciones.evaluacion_servicio(codigo_tecnico);

CREATE INDEX IF NOT EXISTS idx_evaluacion_servicio_taller
    ON operaciones.evaluacion_servicio(id_taller);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_evaluacion_servicio_calificacion'
    ) THEN
        ALTER TABLE operaciones.evaluacion_servicio
        ADD CONSTRAINT ck_evaluacion_servicio_calificacion
        CHECK (calificacion BETWEEN 1 AND 5);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_evaluacion_servicio_puntualidad'
    ) THEN
        ALTER TABLE operaciones.evaluacion_servicio
        ADD CONSTRAINT ck_evaluacion_servicio_puntualidad
        CHECK (puntualidad IS NULL OR puntualidad BETWEEN 1 AND 5);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_evaluacion_servicio_trato'
    ) THEN
        ALTER TABLE operaciones.evaluacion_servicio
        ADD CONSTRAINT ck_evaluacion_servicio_trato
        CHECK (trato IS NULL OR trato BETWEEN 1 AND 5);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_evaluacion_servicio_solucion'
    ) THEN
        ALTER TABLE operaciones.evaluacion_servicio
        ADD CONSTRAINT ck_evaluacion_servicio_solucion
        CHECK (solucion IS NULL OR solucion BETWEEN 1 AND 5);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_evaluacion_servicio_precio'
    ) THEN
        ALTER TABLE operaciones.evaluacion_servicio
        ADD CONSTRAINT ck_evaluacion_servicio_precio
        CHECK (precio IS NULL OR precio BETWEEN 1 AND 5);
    END IF;
END $$;
