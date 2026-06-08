CREATE SCHEMA IF NOT EXISTS suscripciones;

CREATE TABLE IF NOT EXISTS suscripciones.plan_suscripcion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    duracion_dias INTEGER NOT NULL,
    precio NUMERIC(10, 2) NOT NULL DEFAULT 0,
    dominio_incluido BOOLEAN NOT NULL DEFAULT TRUE,
    dominio_personalizado BOOLEAN NOT NULL DEFAULT TRUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    limite_talleres INTEGER NOT NULL DEFAULT 1,
    limite_tecnicos INTEGER NOT NULL DEFAULT 5,
    limite_usuarios INTEGER NOT NULL DEFAULT 50,
    limite_incidentes_mensuales INTEGER NOT NULL DEFAULT 300,
    limite_notificaciones_push INTEGER NOT NULL DEFAULT 1000,
    limite_almacenamiento_gb NUMERIC(10, 2) NOT NULL DEFAULT 5,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suscripciones.tenant (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    slug VARCHAR(120) NOT NULL UNIQUE,
    id_taller INTEGER NOT NULL UNIQUE REFERENCES talleres.taller(codigo) ON UPDATE CASCADE ON DELETE CASCADE,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suscripciones.dominio_tenant (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES suscripciones.tenant(id) ON UPDATE CASCADE ON DELETE CASCADE,
    dominio VARCHAR(255) NOT NULL UNIQUE,
    tipo VARCHAR(30) NOT NULL DEFAULT 'SUBDOMINIO',
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suscripciones.suscripcion_tenant (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES suscripciones.tenant(id) ON UPDATE CASCADE ON DELETE CASCADE,
    id_plan INTEGER NOT NULL REFERENCES suscripciones.plan_suscripcion(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_inicio DATE NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVA',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suscripciones.consumo_cuota (
    id SERIAL PRIMARY KEY,
    id_tenant INTEGER NOT NULL REFERENCES suscripciones.tenant(id) ON UPDATE CASCADE ON DELETE CASCADE,
    periodo VARCHAR(7) NOT NULL,
    tecnicos_usados INTEGER NOT NULL DEFAULT 0,
    usuarios_usados INTEGER NOT NULL DEFAULT 0,
    incidentes_usados INTEGER NOT NULL DEFAULT 0,
    notificaciones_usadas INTEGER NOT NULL DEFAULT 0,
    almacenamiento_usado_gb NUMERIC(10, 2) NOT NULL DEFAULT 0,
    observacion TEXT NULL,
    UNIQUE(id_tenant, periodo)
);

CREATE INDEX IF NOT EXISTS idx_dominio_tenant_dominio
    ON suscripciones.dominio_tenant(dominio);

CREATE INDEX IF NOT EXISTS idx_suscripcion_tenant_tenant
    ON suscripciones.suscripcion_tenant(id_tenant);

INSERT INTO suscripciones.plan_suscripcion (
    nombre,
    duracion_dias,
    precio,
    dominio_incluido,
    dominio_personalizado,
    estado,
    limite_talleres,
    limite_tecnicos,
    limite_usuarios,
    limite_incidentes_mensuales,
    limite_notificaciones_push,
    limite_almacenamiento_gb
)
VALUES (
    'Plan Estandar',
    30,
    0,
    TRUE,
    TRUE,
    'ACTIVO',
    1,
    5,
    50,
    300,
    1000,
    5
)
ON CONFLICT (nombre) DO UPDATE SET
    duracion_dias = EXCLUDED.duracion_dias,
    dominio_incluido = EXCLUDED.dominio_incluido,
    dominio_personalizado = EXCLUDED.dominio_personalizado,
    estado = EXCLUDED.estado,
    limite_talleres = EXCLUDED.limite_talleres,
    limite_tecnicos = EXCLUDED.limite_tecnicos,
    limite_usuarios = EXCLUDED.limite_usuarios,
    limite_incidentes_mensuales = EXCLUDED.limite_incidentes_mensuales,
    limite_notificaciones_push = EXCLUDED.limite_notificaciones_push,
    limite_almacenamiento_gb = EXCLUDED.limite_almacenamiento_gb;

WITH talleres_sin_tenant AS (
    SELECT
        t.codigo,
        t.nombre,
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

INSERT INTO suscripciones.suscripcion_tenant (
    id_tenant,
    id_plan,
    fecha_inicio,
    fecha_vencimiento,
    estado
)
SELECT
    tenant.id,
    plan.id,
    CURRENT_DATE,
    CURRENT_DATE + plan.duracion_dias,
    'ACTIVA'
FROM suscripciones.tenant tenant
CROSS JOIN suscripciones.plan_suscripcion plan
WHERE plan.nombre = 'Plan Estandar'
  AND NOT EXISTS (
      SELECT 1
      FROM suscripciones.suscripcion_tenant st
      WHERE st.id_tenant = tenant.id
  );
