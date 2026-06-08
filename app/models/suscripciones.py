from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, TIMESTAMP, Text, func

from app.database import Base


class PlanSuscripcion(Base):
    __tablename__ = "plan_suscripcion"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    duracion_dias = Column(Integer, nullable=False)
    precio = Column(Numeric(10, 2), nullable=False, default=0)
    dominio_incluido = Column(Boolean, nullable=False, default=True)
    dominio_personalizado = Column(Boolean, nullable=False, default=True)
    estado = Column(String(20), nullable=False, default="ACTIVO")
    limite_talleres = Column(Integer, nullable=False, default=1)
    limite_tecnicos = Column(Integer, nullable=False, default=5)
    limite_usuarios = Column(Integer, nullable=False, default=50)
    limite_incidentes_mensuales = Column(Integer, nullable=False, default=300)
    limite_notificaciones_push = Column(Integer, nullable=False, default=1000)
    limite_almacenamiento_gb = Column(Numeric(10, 2), nullable=False, default=5)
    stripe_product_id = Column(String(100), nullable=True)
    stripe_price_id = Column(String(100), nullable=True)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenant"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    slug = Column(String(120), nullable=False, unique=True)
    id_taller = Column(Integer, ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, unique=True)
    estado = Column(String(20), nullable=False, default="ACTIVO")
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class DominioTenant(Base):
    __tablename__ = "dominio_tenant"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_tenant = Column(Integer, ForeignKey("suscripciones.tenant.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    dominio = Column(String(255), nullable=False, unique=True)
    tipo = Column(String(30), nullable=False, default="SUBDOMINIO")
    estado = Column(String(20), nullable=False, default="ACTIVO")
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class SuscripcionTenant(Base):
    __tablename__ = "suscripcion_tenant"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_tenant = Column(Integer, ForeignKey("suscripciones.tenant.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_plan = Column(Integer, ForeignKey("suscripciones.plan_suscripcion.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    fecha_inicio = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    estado = Column(String(20), nullable=False, default="ACTIVA")
    stripe_customer_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)
    stripe_checkout_session_id = Column(String(100), nullable=True)
    fecha_ultimo_pago = Column(TIMESTAMP, nullable=True)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class PagoSuscripcion(Base):
    __tablename__ = "pago_suscripcion"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_tenant = Column(Integer, ForeignKey("suscripciones.tenant.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_suscripcion = Column(Integer, ForeignKey("suscripciones.suscripcion_tenant.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_plan = Column(Integer, ForeignKey("suscripciones.plan_suscripcion.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    proveedor = Column(String(30), nullable=False, default="STRIPE")
    stripe_invoice_id = Column(String(100), nullable=True, unique=True)
    stripe_payment_intent_id = Column(String(100), nullable=True)
    stripe_checkout_session_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)
    monto = Column(Numeric(10, 2), nullable=False)
    moneda = Column(String(10), nullable=False)
    estado = Column(String(30), nullable=False)
    periodo_inicio = Column(Date, nullable=True)
    periodo_fin = Column(Date, nullable=True)
    hosted_invoice_url = Column(String(500), nullable=True)
    invoice_pdf = Column(String(500), nullable=True)
    fecha_pago = Column(TIMESTAMP, nullable=False)


class ComprobanteSuscripcion(Base):
    __tablename__ = "comprobante_suscripcion"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_pago = Column(Integer, ForeignKey("suscripciones.pago_suscripcion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, unique=True)
    numero_comprobante = Column(String(50), nullable=False, unique=True)
    fecha_emision = Column(TIMESTAMP, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    moneda = Column(String(10), nullable=False)
    contenido_json = Column(Text, nullable=False)


class ConsumoCuota(Base):
    __tablename__ = "consumo_cuota"
    __table_args__ = {"schema": "suscripciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_tenant = Column(Integer, ForeignKey("suscripciones.tenant.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    periodo = Column(String(7), nullable=False)
    tecnicos_usados = Column(Integer, nullable=False, default=0)
    usuarios_usados = Column(Integer, nullable=False, default=0)
    incidentes_usados = Column(Integer, nullable=False, default=0)
    notificaciones_usadas = Column(Integer, nullable=False, default=0)
    almacenamiento_usado_gb = Column(Numeric(10, 2), nullable=False, default=0)
    observacion = Column(Text, nullable=True)
