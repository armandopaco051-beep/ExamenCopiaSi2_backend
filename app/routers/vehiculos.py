from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.clientes import Vehiculo
from app.models.seguridad import Usuario
from app.routers.tecnicos import get_current_usuario
from app.schemas.vehiculos import VehiculoCreate, VehiculoResponse, VehiculoUpdate


router = APIRouter(prefix="/vehiculos", tags=["Vehiculos"])


# Normaliza una placa de vehículo a mayúsculas sin espacios
# Caso de uso: Normalización de placas para consistencia
def normalizar_placa(placa: str) -> str:
    return placa.strip().upper()


# Valida que el usuario sea cliente o administrador
# Caso de uso: Control de acceso para gestión de vehículos
def validar_cliente_o_admin(usuario: Usuario):
    if usuario.id_rol not in [1, 4]:
        raise HTTPException(status_code=403, detail="No autorizado para gestionar vehiculos")


# Obtiene un vehículo validando que el usuario tenga acceso al mismo
# Caso de uso: Control de acceso para operaciones de vehículo
def obtener_vehiculo_autorizado(codigo: int, usuario: Usuario, db: Session):
    vehiculo = db.query(Vehiculo).filter(Vehiculo.codigo == codigo).first()
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehiculo no encontrado")

    if usuario.id_rol == 1 or vehiculo.id_usuario == usuario.codigo:
        return vehiculo

    raise HTTPException(status_code=403, detail="No autorizado para este vehiculo")


# Crea un nuevo vehículo para un cliente
# Caso de uso: Registro de vehículo
@router.post("/", response_model=VehiculoResponse, status_code=201)
def crear_vehiculo(
    datos: VehiculoCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_cliente_o_admin(usuario)

    placa = normalizar_placa(datos.placa)
    if db.query(Vehiculo).filter(Vehiculo.placa == placa).first():
        raise HTTPException(status_code=400, detail="Placa ya registrada")

    id_usuario = usuario.codigo if usuario.id_rol == 4 else datos.id_usuario
    if not id_usuario:
        raise HTTPException(status_code=400, detail="Debe indicar id_usuario para registrar vehiculo como administrador")

    nuevo = Vehiculo(
        modelo=datos.modelo.strip(),
        marca=datos.marca.strip(),
        placa=placa,
        anio=datos.anio.strip(),
        id_usuario=id_usuario
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


# Lista los vehículos del cliente actual
# Caso de uso: Consulta de vehículos propios por cliente
@router.get("/mis-vehiculos", response_model=List[VehiculoResponse])
def listar_mis_vehiculos(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 4:
        raise HTTPException(status_code=403, detail="Solo el cliente puede consultar sus vehiculos")

    return db.query(Vehiculo).filter(
        Vehiculo.id_usuario == usuario.codigo,
        Vehiculo.activo == True
    ).all()


# Lista los vehículos de un usuario específico
# Caso de uso: Consulta de vehículos por usuario
@router.get("/usuario/{id_usuario}", response_model=List[VehiculoResponse])
def listar_por_usuario(
    id_usuario: str,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 1 and usuario.codigo != id_usuario:
        raise HTTPException(status_code=403, detail="No autorizado para consultar vehiculos de otro usuario")

    return db.query(Vehiculo).filter(Vehiculo.id_usuario == id_usuario).all()


# Obtiene un vehículo específico por su código
# Caso de uso: Consulta de vehículo por ID
@router.get("/{codigo}", response_model=VehiculoResponse)
def obtener_vehiculo(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    return obtener_vehiculo_autorizado(codigo, usuario, db)


# Actualiza los datos de un vehículo
# Caso de uso: Actualización de información de vehículo
@router.put("/{codigo}", response_model=VehiculoResponse)
def actualizar_vehiculo(
    codigo: int,
    datos: VehiculoUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    vehiculo = obtener_vehiculo_autorizado(codigo, usuario, db)

    datos_dict = datos.model_dump(exclude_unset=True)
    if "placa" in datos_dict and datos_dict["placa"] is not None:
        placa = normalizar_placa(datos_dict["placa"])
        existe = db.query(Vehiculo).filter(
            Vehiculo.placa == placa,
            Vehiculo.codigo != vehiculo.codigo
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail="Placa ya registrada")
        datos_dict["placa"] = placa

    if "modelo" in datos_dict and datos_dict["modelo"] is not None:
        datos_dict["modelo"] = datos_dict["modelo"].strip()
    if "marca" in datos_dict and datos_dict["marca"] is not None:
        datos_dict["marca"] = datos_dict["marca"].strip()
    if "anio" in datos_dict and datos_dict["anio"] is not None:
        datos_dict["anio"] = datos_dict["anio"].strip()

    for campo, valor in datos_dict.items():
        setattr(vehiculo, campo, valor)

    db.commit()
    db.refresh(vehiculo)
    return vehiculo


# Desactiva un vehículo (no lo elimina, solo marca como inactivo)
# Caso de uso: Desactivación de vehículo
@router.delete("/{codigo}")
def desactivar_vehiculo(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    vehiculo = obtener_vehiculo_autorizado(codigo, usuario, db)
    vehiculo.activo = False
    db.commit()
    return {"mensaje": "Vehiculo desactivado"}
