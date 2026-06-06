from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    nombre: str
    slug: str
    dominio: str
    id_taller: int
    tipo_dominio: str = "SUBDOMINIO"


class CambiarEstadoSuscripcionRequest(BaseModel):
    estado: str = Field(pattern="^(ACTIVA|VENCIDA|SUSPENDIDA|CANCELADA)$")


class RenovarSuscripcionRequest(BaseModel):
    duracion_dias: int = Field(default=30, gt=0)


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
