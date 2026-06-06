CREATE TABLE IF NOT EXISTS operaciones.concepto_cobro (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    descripcion TEXT NULL,
    precio_unitario NUMERIC(10, 2) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    id_taller INTEGER NULL REFERENCES talleres.taller(codigo)
        ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS operaciones.cobro_servicio (
    id SERIAL PRIMARY KEY,
    id_incidente INTEGER NOT NULL UNIQUE REFERENCES operaciones.incidente(codigo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_asignacion INTEGER NOT NULL REFERENCES operaciones.asignacion(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    estado_pago VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0,
    descuento NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total NUMERIC(10, 2) NOT NULL DEFAULT 0,
    fecha_generacion TIMESTAMP NOT NULL,
    fecha_aceptacion TIMESTAMP NULL,
    fecha_pago TIMESTAMP NULL,
    fecha_comprobante TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS operaciones.detalle_cobro (
    id SERIAL PRIMARY KEY,
    id_cobro INTEGER NOT NULL REFERENCES operaciones.cobro_servicio(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_concepto INTEGER NOT NULL REFERENCES operaciones.concepto_cobro(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    descripcion TEXT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    cantidad NUMERIC(10, 2) NOT NULL,
    precio_unitario NUMERIC(10, 2) NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    observacion TEXT NULL
);

CREATE TABLE IF NOT EXISTS operaciones.pago_servicio (
    id SERIAL PRIMARY KEY,
    id_cobro INTEGER NOT NULL UNIQUE REFERENCES operaciones.cobro_servicio(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    metodo_pago VARCHAR(50) NOT NULL,
    referencia_pago VARCHAR(100) NULL,
    monto_pagado NUMERIC(10, 2) NOT NULL,
    estado_pago VARCHAR(30) NOT NULL,
    fecha_pago TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS operaciones.comprobante_pago (
    id SERIAL PRIMARY KEY,
    id_cobro INTEGER NOT NULL UNIQUE REFERENCES operaciones.cobro_servicio(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    numero_comprobante VARCHAR(50) NOT NULL UNIQUE,
    fecha_emision TIMESTAMP NOT NULL,
    total NUMERIC(10, 2) NOT NULL,
    contenido_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_detalle_cobro_cobro
ON operaciones.detalle_cobro (id_cobro);

INSERT INTO operaciones.concepto_cobro
    (codigo, nombre, tipo, descripcion, precio_unitario, activo)
VALUES
    ('AUXILIO_BASE', 'Auxilio vehicular base', 'SERVICIO', 'Tarifa base por atencion de auxilio vehicular', 50.00, TRUE),
    ('RECARGO_DISTANCIA', 'Recargo por desplazamiento', 'DISTANCIA', 'Recargo fijo por desplazamiento del tecnico', 10.00, TRUE),
    ('MANO_OBRA_EXTRA', 'Mano de obra adicional', 'MANO_OBRA', 'Trabajo adicional realizado por el tecnico', 30.00, TRUE),
    ('BATERIA_NUEVA', 'Bateria nueva', 'REPUESTO', 'Cambio o instalacion de bateria nueva', 400.00, TRUE),
    ('COMBUSTIBLE', 'Combustible', 'INSUMO', 'Abastecimiento de combustible de emergencia', 20.00, TRUE),
    ('GRUA', 'Servicio de grua', 'SERVICIO', 'Traslado con grua', 150.00, TRUE),
    ('CAMBIO_LLANTA', 'Cambio de llanta', 'SERVICIO', 'Servicio de cambio de llanta', 40.00, TRUE),
    ('REPARACION_ELECTRICA', 'Reparacion electrica menor', 'SERVICIO', 'Revision o reparacion electrica menor', 60.00, TRUE)
ON CONFLICT (codigo) DO UPDATE
SET
    nombre = EXCLUDED.nombre,
    tipo = EXCLUDED.tipo,
    descripcion = EXCLUDED.descripcion,
    precio_unitario = EXCLUDED.precio_unitario,
    activo = EXCLUDED.activo;
