UPDATE suscripciones.plan_suscripcion
SET precio = 0
WHERE nombre = 'Plan Estandar';

WITH plan_base AS (
    SELECT id, duracion_dias
    FROM suscripciones.plan_suscripcion
    WHERE nombre = 'Plan Estandar'
    LIMIT 1
),
talleres_sin_tenant AS (
    SELECT
        t.codigo,
        COALESCE(NULLIF(t.nombre, ''), 'Taller ' || t.codigo) AS nombre,
        LOWER(
            REGEXP_REPLACE(
                REGEXP_REPLACE(COALESCE(NULLIF(t.nombre, ''), 'taller-' || t.codigo), '[^A-Za-z0-9]+', '-', 'g'),
                '(^-|-$)',
                '',
                'g'
            )
        ) AS base_slug,
        t.activo
    FROM talleres.taller t
    WHERE NOT EXISTS (
        SELECT 1
        FROM suscripciones.tenant st
        WHERE st.id_taller = t.codigo
    )
),
insertados AS (
    INSERT INTO suscripciones.tenant (nombre, slug, id_taller, estado)
    SELECT
        nombre,
        CASE
            WHEN base_slug = '' THEN 'taller-' || codigo
            ELSE base_slug || '-' || codigo
        END AS slug,
        codigo,
        CASE WHEN activo THEN 'ACTIVO' ELSE 'PENDIENTE' END
    FROM talleres_sin_tenant
    RETURNING id, id_taller, slug
)
INSERT INTO suscripciones.dominio_tenant (id_tenant, dominio, tipo, estado)
SELECT
    id,
    slug || '.emergvial.com',
    'SUBDOMINIO',
    'ACTIVO'
FROM insertados
ON CONFLICT (dominio) DO NOTHING;

INSERT INTO suscripciones.dominio_tenant (id_tenant, dominio, tipo, estado)
SELECT
    tenant.id,
    tenant.slug || '.emergvial.com',
    'SUBDOMINIO',
    'ACTIVO'
FROM suscripciones.tenant tenant
WHERE NOT EXISTS (
    SELECT 1
    FROM suscripciones.dominio_tenant dt
    WHERE dt.id_tenant = tenant.id
)
ON CONFLICT (dominio) DO NOTHING;

INSERT INTO suscripciones.suscripcion_tenant (
    id_tenant,
    id_plan,
    fecha_inicio,
    fecha_vencimiento,
    estado
)
SELECT
    tenant.id,
    plan_base.id,
    CURRENT_DATE,
    CURRENT_DATE + plan_base.duracion_dias,
    'ACTIVA'
FROM suscripciones.tenant tenant
CROSS JOIN plan_base
WHERE NOT EXISTS (
    SELECT 1
    FROM suscripciones.suscripcion_tenant st
    WHERE st.id_tenant = tenant.id
);
