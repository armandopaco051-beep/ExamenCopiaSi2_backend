from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import math

from app.database import get_db
from app.models.seguridad import Usuario
from app.models.talleres import Taller
from app.routers.tecnicos import get_current_usuario, get_taller_admin
from app.schemas.taller import (
    CoberturaResponse,
    CoberturaUpdate,
    TallerCreate,
    TallerResponse,
    TallerUpdate,
    VerificarCoberturaResponse,
)

router = APIRouter(prefix="/talleres", tags=["Talleres"])


# Valida que el usuario sea administrador de la plataforma
# Caso de uso: Control de acceso para operaciones administrativas
def validar_admin_global(usuario: Usuario):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede realizar esta accion")


# Obtiene un taller validando que el usuario tenga acceso al mismo
# Caso de uso: Control de acceso para operaciones de taller
def obtener_taller_autorizado(
    db: Session,
    codigo: int,
    usuario: Usuario,
    permitir_admin_global: bool = True
):
    t = db.query(Taller).filter(Taller.codigo == codigo).first()
    if not t:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    if permitir_admin_global and usuario.id_rol == 1:
        return t

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if taller.codigo == t.codigo:
            return t

    raise HTTPException(status_code=403, detail="No autorizado para este taller")


def calcular_distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia en km usando Haversine."""
    radio_tierra_km = 6371
    d_lat = math.radians(float(lat2) - float(lat1))
    d_lon = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(float(lat1)))
        * math.cos(math.radians(float(lat2)))
        * math.sin(d_lon / 2) ** 2
    )
    return radio_tierra_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Crea un nuevo taller en el sistema
# Caso de uso: Creación de taller por administrador
@router.post("", response_model=TallerResponse, status_code=201)
def crear_taller(
    datos: TallerCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin_global(usuario)
    nuevo = Taller(**datos.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


# Lista los talleres según el rol del usuario (todos para admin, solo el propio para admin_taller)
# Caso de uso: Consulta de talleres
@router.get("", response_model=List[TallerResponse])
def listar_talleres(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol == 1:
        return db.query(Taller).filter(Taller.activo == True).all()

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        return db.query(Taller).filter(Taller.codigo == taller.codigo, Taller.activo == True).all()

    raise HTTPException(status_code=403, detail="No autorizado")


# Obtiene un taller específico por su código
# Caso de uso: Consulta de taller por ID
@router.get("/{codigo}", response_model=TallerResponse)
def obtener_taller(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    return obtener_taller_autorizado(db, codigo, usuario)


# Obtiene la información de cobertura de un taller
# Caso de uso: Consulta de cobertura de taller
@router.get("/{codigo}/cobertura", response_model=CoberturaResponse)
def obtener_cobertura_taller(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    t = obtener_taller_autorizado(db, codigo, usuario)

    return {
        "codigo_taller": t.codigo,
        "nombre_taller": t.nombre,
        "latitud": t.latitud,
        "longitud": t.longitud,
        "radio_cobertura_km": t.radio_cobertura_km,
    }


# Actualiza el radio de cobertura de un taller
# Caso de uso: Actualización de cobertura de taller
@router.put("/{codigo}/cobertura", response_model=CoberturaResponse)
def actualizar_cobertura_taller(
    codigo: int,
    datos: CoberturaUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    t = obtener_taller_autorizado(db, codigo, usuario)

    t.radio_cobertura_km = datos.radio_cobertura_km
    db.commit()
    db.refresh(t)

    return {
        "codigo_taller": t.codigo,
        "nombre_taller": t.nombre,
        "latitud": t.latitud,
        "longitud": t.longitud,
        "radio_cobertura_km": t.radio_cobertura_km,
    }


# Verifica si una coordenada está dentro del radio de cobertura de un taller
# Caso de uso: Verificación de cobertura para asignación
@router.get("/{codigo}/cobertura/verificar", response_model=VerificarCoberturaResponse)
def verificar_cobertura_taller(
    codigo: int,
    latitud: float,
    longitud: float,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    t = obtener_taller_autorizado(db, codigo, usuario)

    distancia = calcular_distancia_km(latitud, longitud, t.latitud, t.longitud)

    return {
        "codigo_taller": t.codigo,
        "nombre_taller": t.nombre,
        "latitud_consulta": latitud,
        "longitud_consulta": longitud,
        "radio_cobertura_km": t.radio_cobertura_km,
        "distancia_km": round(distancia, 2),
        "dentro_cobertura": distancia <= t.radio_cobertura_km,
    }


# Actualiza los datos de un taller
# Caso de uso: Actualización de información de taller
@router.put("/{codigo}", response_model=TallerResponse)
def actualizar_taller(
    codigo: int,
    datos: TallerUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    t = obtener_taller_autorizado(db, codigo, usuario)

    datos_dict = datos.model_dump(exclude_unset=True)
    if usuario.id_rol == 2:
        datos_dict.pop("usuario_id", None)
        datos_dict.pop("activo", None)

    for campo, valor in datos_dict.items():
        setattr(t, campo, valor)

    db.commit()
    db.refresh(t)
    return t


# Desactiva un taller (no lo elimina, solo marca como inactivo)
# Caso de uso: Desactivación de taller por administrador
@router.delete("/{codigo}")
def desactivar_taller(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin_global(usuario)
    t = obtener_taller_autorizado(db, codigo, usuario)

    t.activo = False
    db.commit()
    db.refresh(t)

    return {"mensaje": "Taller desactivado"}
