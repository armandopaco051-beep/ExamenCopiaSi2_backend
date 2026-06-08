ALTER TABLE suscripciones.plan_suscripcion
ADD COLUMN IF NOT EXISTS stripe_product_id VARCHAR(100) NULL;

ALTER TABLE suscripciones.plan_suscripcion
ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(100) NULL;

ALTER TABLE suscripciones.suscripcion_tenant
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100) NULL;

ALTER TABLE suscripciones.suscripcion_tenant
ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(100) NULL;

ALTER TABLE suscripciones.suscripcion_tenant
ADD COLUMN IF NOT EXISTS stripe_checkout_session_id VARCHAR(100) NULL;

ALTER TABLE suscripciones.suscripcion_tenant
ADD COLUMN IF NOT EXISTS fecha_ultimo_pago TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS ix_suscripcion_tenant_stripe_subscription
ON suscripciones.suscripcion_tenant (stripe_subscription_id);

CREATE INDEX IF NOT EXISTS ix_suscripcion_tenant_stripe_session
ON suscripciones.suscripcion_tenant (stripe_checkout_session_id);
