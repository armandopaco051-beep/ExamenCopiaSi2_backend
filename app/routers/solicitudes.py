from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app.models.seguridad import Usuario
from app.models.talleres import Taller
from app.schemas.solicitud import (
    RegistroAdminTallerCreate,
    ResponderSolicitudRequest,
    SolicitudAdminTallerResponse
)
from app.services.auth_service import (
    hash_password,
    registrar_bitacora,
    decode_token
)

router = APIRouter(
    prefix="/solicitudes-registro",
    tags=["Solicitudes Registro Admin Taller"]
)


# Extrae el código de usuario del token JWT del encabezado Authorization
# Caso de uso: Autenticación para endpoints de solicitudes
def obtener_codigo_actor(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Falta token de autenticación")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token inválido")

    token = auth_header.replace("Bearer ", "").strip()
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    codigo = payload.get("sub")
    if not codigo:
        raise HTTPException(status_code=401, detail="Token sin código de usuario")

    return str(codigo)


# Crea una solicitud de registro para un nuevo admin_taller y su taller
# Caso de uso: Solicitud de registro de taller
@router.post("", status_code=201)
def solicitar_registro(
    datos: RegistroAdminTallerCreate,
    db: Session = Depends(get_db)
):
    if db.query(Usuario).filter(Usuario.codigo == datos.codigo_usuario).first():
        raise HTTPException(status_code=400, detail="El CI ya está registrado")

    if db.query(Usuario).filter(Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    nuevo_usuario = Usuario(
        codigo=datos.codigo_usuario,
        nombre=datos.nombre,
        apellido=datos.apellido,
        email=datos.email,
        password=hash_password(datos.password),
        telefono=datos.telefono,
        id_rol=2,
        estado=False,
        estado_registro="pendiente",
        observacion_admin=None,
        fecha_registro=datetime.now(),
        fecha_solicitud=datetime.now()
    )
    db.add(nuevo_usuario)
    db.flush()

    nuevo_taller = Taller(
        nombre=datos.nombre_taller,
        telefono=datos.telefono_taller,
        direccion=datos.direccion_taller,
        latitud=float(datos.latitud_taller),
        longitud=float(datos.longitud_taller),
        horario_inicio=datos.horario_inicio,
        horario_fin=datos.horario_fin,
        activo=False,
        estado_registro="pendiente",
        observacion_admin=None,
        fecha_solicitud=datetime.now(),
        usuario_id=datos.codigo_usuario
    )
    db.add(nuevo_taller)
    db.flush()

    registrar_bitacora(
        db=db,
        codigo_usuario=datos.codigo_usuario,
        accion="SOLICITUD_REGISTRO_TALLER",
        modulo="SOLICITUDES",
        descripcion=f"El usuario {datos.codigo_usuario} solicitó registrar el taller {datos.nombre_taller}",
        ip_address="127.0.0.1",
        id_taller=nuevo_taller.codigo
    )

    db.commit()
    db.refresh(nuevo_usuario)
    db.refresh(nuevo_taller)

    return {
        "mensaje": "Solicitud enviada. Espera aprobación del administrador.",
        "codigo_usuario": datos.codigo_usuario,
        "codigo_taller": nuevo_taller.codigo
    }

# Lista todas las solicitudes de registro de talleres con filtro opcional por estado
# Caso de uso: Consulta de solicitudes por administrador
@router.get("", response_model=List[SolicitudAdminTallerResponse])
def listar_solicitudes(
    estado: "str | None" = None,
    db: Session = Depends(get_db)
):
    query = (
        db.query(Usuario, Taller)
        .join(Taller, Taller.usuario_id == Usuario.codigo)
        .filter(Usuario.id_rol == 2)
    )

    if estado:
        query = query.filter(Usuario.estado_registro == estado)

    data = query.order_by(Usuario.fecha_solicitud.desc()).all()

    resultado = []
    for usuario, taller in data:
        resultado.append({
            "codigo_usuario": usuario.codigo,
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "telefono": usuario.telefono,

            "codigo_taller": taller.codigo,
            "nombre_taller": taller.nombre,
            "telefono_taller": taller.telefono,
            "direccion_taller": taller.direccion,
            "latitud_taller": taller.latitud,
            "longitud_taller": taller.longitud,
            "horario_inicio": taller.horario_inicio,
            "horario_fin": taller.horario_fin,

            "estado_registro": usuario.estado_registro,
            "observacion_admin": usuario.observacion_admin,
            "fecha_solicitud": usuario.fecha_solicitud,
            "fecha_respuesta": usuario.fecha_respuesta
        })

    return resultado


# Cuenta las solicitudes de registro pendientes de aprobación
# Caso de uso: Consulta de contador de solicitudes pendientes
@router.get("/pendientes/count")
def contar_pendientes(db: Session = Depends(get_db)):
    count = db.query(Usuario).filter(
        Usuario.id_rol == 2,
        Usuario.estado_registro == "pendiente"
    ).count()

    return {"pendientes": count}


# Acepta o rechaza una solicitud de registro de taller
# Caso de uso: Aprobación/rechazo de solicitud de taller por administrador
@router.put("/{codigo_usuario}/responder")
def responder_solicitud(
    codigo_usuario: str,
    datos: ResponderSolicitudRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    admin_codigo = obtener_codigo_actor(request)

    admin = db.query(Usuario).filter(Usuario.codigo == admin_codigo).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Administrador no encontrado")

    if admin.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    usuario = db.query(Usuario).filter(
        Usuario.codigo == codigo_usuario,
        Usuario.id_rol == 2
    ).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if usuario.estado_registro != "pendiente":
        raise HTTPException(status_code=400, detail="La solicitud ya fue procesada")

    taller = db.query(Taller).filter(Taller.usuario_id == codigo_usuario).first()

    if not taller:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    try:
        if datos.aceptada:
            usuario.estado = True
            usuario.estado_registro = "aceptado"
            usuario.observacion_admin = None
            usuario.fecha_respuesta = datetime.now()

            taller.activo = True
            taller.estado_registro = "aceptado"
            taller.observacion_admin = None
            taller.fecha_respuesta = datetime.now()

            registrar_bitacora(
                db=db,
                codigo_usuario=admin.codigo,
                accion="ACEPTAR_SOLICITUD",
                modulo="SOLICITUDES",
                descripcion=f"El admin aceptó la solicitud del usuario {codigo_usuario} para el taller {taller.nombre}",
                ip_address="127.0.0.1",
                id_taller=taller.codigo
            )

        else:
            observacion = (datos.observacion or "").strip() or "Solicitud rechazada por el administrador"

            registrar_bitacora(
                db=db,
                codigo_usuario=admin.codigo,
                accion="RECHAZAR_SOLICITUD",
                modulo="SOLICITUDES",
                descripcion=f"El admin rechazó la solicitud del usuario {codigo_usuario} para el taller {taller.nombre}. Motivo: {observacion}",
                ip_address="127.0.0.1",
                id_taller=taller.codigo
            )

            db.flush()

            db.delete(taller)
            db.delete(usuario)

        db.commit()

        return {"mensaje": "Solicitud procesada correctamente"}

    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al responder solicitud: {str(e)}")