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
    id_local_origen: Optional[str] = None
    origen_registro: str = "ONLINE"
    fecha_creacion_local: Optional[datetime] = None
    version_local: Optional[int] = None
    estado_local_origen: Optional[str] = None


class IncidenteOfflineSync(IncidenteCreate):
    id_local_origen: str
    origen_registro: str = "OFFLINE"


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
    id_local_origen: Optional[str] = None
    origen_registro: str = "ONLINE"
    fecha_creacion_local: Optional[datetime] = None
    version_local: Optional[int] = None
    estado_local_origen: Optional[str] = None

    class Config:
        from_attributes = True
