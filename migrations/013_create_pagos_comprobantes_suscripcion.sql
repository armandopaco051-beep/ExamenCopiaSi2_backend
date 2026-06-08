CREATE TABLE IF NOT EXISTS suscripciones.pago_suscripcion (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES suscripciones.tenant(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_suscripcion INTEGER NOT NULL REFERENCES suscripciones.suscripcion_tenant(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    id_plan INTEGER NOT NULL REFERENCES suscripciones.plan_suscripcion(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    proveedor VARCHAR(30) NOT NULL DEFAULT 'STRIPE',
    stripe_invoice_id VARCHAR(100) NULL UNIQUE,
    stripe_payment_intent_id VARCHAR(100) NULL,
    stripe_checkout_session_id VARCHAR(100) NULL,
    stripe_subscription_id VARCHAR(100) NULL,
    monto NUMERIC(10, 2) NOT NULL,
    moneda VARCHAR(10) NOT NULL,
    estado VARCHAR(30) NOT NULL,
    periodo_inicio DATE NULL,
    periodo_fin DATE NULL,
    hosted_invoice_url VARCHAR(500) NULL,
    invoice_pdf VARCHAR(500) NULL,
    fecha_pago TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS suscripciones.comprobante_suscripcion (
    id SERIAL PRIMARY KEY,
    id_pago INTEGER NOT NULL UNIQUE REFERENCES suscripciones.pago_suscripcion(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    numero_comprobante VARCHAR(50) NOT NULL UNIQUE,
    fecha_emision TIMESTAMP NOT NULL,
    total NUMERIC(10, 2) NOT NULL,
    moneda VARCHAR(10) NOT NULL,
    contenido_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_pago_suscripcion_tenant
ON suscripciones.pago_suscripcion (id_tenant, fecha_pago);

CREATE INDEX IF NOT EXISTS ix_pago_suscripcion_stripe_subscription
ON suscripciones.pago_suscripcion (stripe_subscription_id);
