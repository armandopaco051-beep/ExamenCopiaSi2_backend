from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VehiculoCreate(BaseModel):
    modelo: str
    placa: str
    marca: str
    anio: str = Field(alias="año")
    id_usuario: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class VehiculoUpdate(BaseModel):
    modelo: Optional[str] = None
    placa: Optional[str] = None
    marca: Optional[str] = None
    anio: Optional[str] = Field(default=None, alias="año")
    activo: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)


class VehiculoResponse(BaseModel):
    codigo: int
    modelo: str
    placa: str
    marca: str
    anio: str = Field(alias="año")
    activo: bool
    id_usuario: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
