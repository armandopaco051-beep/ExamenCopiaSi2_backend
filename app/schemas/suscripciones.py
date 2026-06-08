from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    nombre: str
    slug: str
    dominio: str
    id_taller: int
    tipo_dominio: str = "SUBDOMINIO"
    id_plan: int | None = None


class PlanSuscripcionCreate(BaseModel):
    nombre: str
    duracion_dias: int = Field(default=30, gt=0)
    precio: Decimal = Field(default=Decimal("0"), ge=0)
    dominio_incluido: bool = True
    dominio_personalizado: bool = True
    estado: str = Field(default="ACTIVO", pattern="^(ACTIVO|INACTIVO)$")
    limite_talleres: int = Field(default=1, gt=0)
    limite_tecnicos: int = Field(default=5, ge=0)
    limite_usuarios: int = Field(default=50, ge=0)
    limite_incidentes_mensuales: int = Field(default=300, ge=0)
    limite_notificaciones_push: int = Field(default=1000, ge=0)
    limite_almacenamiento_gb: Decimal = Field(default=Decimal("5"), ge=0)
    stripe_product_id: str | None = None
    stripe_price_id: str | None = None


class PlanSuscripcionUpdate(BaseModel):
    nombre: str | None = None
    duracion_dias: int | None = Field(default=None, gt=0)
    precio: Decimal | None = Field(default=None, ge=0)
    dominio_incluido: bool | None = None
    dominio_personalizado: bool | None = None
    estado: str | None = Field(default=None, pattern="^(ACTIVO|INACTIVO)$")
    limite_talleres: int | None = Field(default=None, gt=0)
    limite_tecnicos: int | None = Field(default=None, ge=0)
    limite_usuarios: int | None = Field(default=None, ge=0)
    limite_incidentes_mensuales: int | None = Field(default=None, ge=0)
    limite_notificaciones_push: int | None = Field(default=None, ge=0)
    limite_almacenamiento_gb: Decimal | None = Field(default=None, ge=0)
    stripe_product_id: str | None = None
    stripe_price_id: str | None = None


class CambiarPlanTenantRequest(BaseModel):
    id_plan: int


class CambiarEstadoSuscripcionRequest(BaseModel):
    estado: str = Field(pattern="^(ACTIVA|VENCIDA|SUSPENDIDA|CANCELADA)$")


class RenovarSuscripcionRequest(BaseModel):
    duracion_dias: int = Field(default=30, gt=0)


class CrearCheckoutSuscripcionRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSuscripcionResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str
    id_tenant: int
    id_suscripcion: int
    estado_suscripcion: str


class PlanSuscripcionResponse(BaseModel):
    id: int
    nombre: str
    duracion_dias: int
    precio: Decimal
    dominio_incluido: bool
    dominio_personalizado: bool
    estado: str
    limite_talleres: int
    limite_tecnicos: int
    limite_usuarios: int
    limite_incidentes_mensuales: int
    limite_notificaciones_push: int
    limite_almacenamiento_gb: Decimal
    stripe_product_id: str | None = None
    stripe_price_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantResponse(BaseModel):
    id: int
    nombre: str
    slug: str
    id_taller: int
    estado: str
    fecha_creacion: datetime | None = None
    dominio: str | None = None
    estado_dominio: str | None = None
    id_suscripcion: int | None = None
    estado_suscripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_vencimiento: date | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    plan: PlanSuscripcionResponse | None = None


class CuotasResponse(BaseModel):
    id_tenant: int
    id_taller: int
    periodo: str
    estado_suscripcion: str
    fecha_vencimiento: date
    limites: dict
    consumo: dict
    excedidos: dict


class PagoSuscripcionResponse(BaseModel):
    id: int
    id_tenant: int
    id_suscripcion: int
    id_plan: int
    proveedor: str
    stripe_invoice_id: str | None = None
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_subscription_id: str | None = None
    monto: Decimal
    moneda: str
    estado: str
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    hosted_invoice_url: str | None = None
    invoice_pdf: str | None = None
    fecha_pago: datetime

    model_config = ConfigDict(from_attributes=True)


class ComprobanteSuscripcionResponse(BaseModel):
    id: int
    id_pago: int
    numero_comprobante: str
    fecha_emision: datetime
    total: Decimal
    moneda: str
    detalle: dict
