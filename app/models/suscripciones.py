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
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


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
