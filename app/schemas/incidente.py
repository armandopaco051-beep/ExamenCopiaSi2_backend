from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class IncidenteCreate(BaseModel):
    descripcion: str
    latitud: Decimal
    longitud: Decimal
    fecha_reporte: datetime
    id_prioridad: int = 2
    id_categoria_problema: int
    id_estado_incidente: int = 1
    id_vehiculo: int
    codigo_usuario: str
    cotizacion_express: bool = False


class IncidenteUpdate(BaseModel):
    descripcion: Optional[str] = None
    id_prioridad: Optional[int] = None
    id_categoria_problema: Optional[int] = None
    id_estado_incidente: Optional[int] = None
    fecha_cierre: Optional[datetime] = None


class IncidenteResponse(BaseModel):
    codigo: int
    descripcion: str
    latitud: Decimal
    longitud: Decimal
    fecha_reporte: datetime
    fecha_cierre: Optional[datetime] = None
    id_prioridad: int
    id_categoria_problema: int
    id_estado_incidente: int
    id_vehiculo: int
    codigo_usuario: str

    class Config:
        from_attributes = True
