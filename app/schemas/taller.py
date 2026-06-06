from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime, time


class TallerCreate(BaseModel):
    nombre: str
    telefono: str
    direccion: str
    latitud: float
    longitud: float
    radio_cobertura_km: float = Field(default=10.0, gt=0)
    horario_inicio: Optional[str] = "08:00"
    horario_fin: Optional[str] = "18:00"


class TallerUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    radio_cobertura_km: Optional[float] = Field(default=None, gt=0)
    activo: Optional[bool] = None
    horario_inicio: Optional[str] = None
    horario_fin: Optional[str] = None
    usuario_id: Optional[str] = None


class TallerResponse(BaseModel):
    codigo: int
    nombre: str
    telefono: str
    direccion: str
    latitud: float
    longitud: float
    radio_cobertura_km: float
    activo: bool
    estado_registro: str
    observacion_admin: Optional[str] = None
    fecha_solicitud: Optional[datetime] = None
    fecha_respuesta: Optional[datetime] = None
    horario_inicio: Optional[time] = None
    horario_fin: Optional[time] = None
    usuario_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CoberturaUpdate(BaseModel):
    radio_cobertura_km: float = Field(gt=0)


class CoberturaResponse(BaseModel):
    codigo_taller: int
    nombre_taller: str
    latitud: float
    longitud: float
    radio_cobertura_km: float


class VerificarCoberturaResponse(BaseModel):
    codigo_taller: int
    nombre_taller: str
    latitud_consulta: float
    longitud_consulta: float
    radio_cobertura_km: float
    distancia_km: float
    dentro_cobertura: bool
