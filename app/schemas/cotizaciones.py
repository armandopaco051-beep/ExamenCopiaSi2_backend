from decimal import Decimal

from pydantic import BaseModel, Field


class SolicitudCotizacionCreate(BaseModel):
    max_talleres: int = Field(default=3, ge=1, le=3)
    tiempo_limite_minutos: int = Field(default=10, ge=1, le=60)
    radio_busqueda_km: Decimal | None = Field(default=None, gt=0)
    observacion: str | None = None


class CotizacionTallerCreate(BaseModel):
    monto_estimado: Decimal = Field(gt=0)
    tiempo_llegada_minutos: int = Field(gt=0, le=1440)
    tiempo_reparacion_minutos: int = Field(gt=0, le=10080)
    descripcion_servicio: str
    id_tecnico: str | None = None
    observacion: str | None = None


class RechazarCotizacionRequest(BaseModel):
    observacion: str | None = None


class SolicitarAjusteRequest(BaseModel):
    observacion: str
