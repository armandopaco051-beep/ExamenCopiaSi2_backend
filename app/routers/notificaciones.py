from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notificaciones import Notificacion
from app.models.seguridad import Usuario
from app.routers.tecnicos import get_current_usuario
from app.services.auth_service import decode_token
from app.services.notificaciones_service import crear_notificacion
from app.services.notificaciones_realtime import notificaciones_manager


router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


class BroadcastNotificacionRequest(BaseModel):
    mensaje: str
    id_incidente: int | None = None
    id_rol: int | None = 4


# Serializa una notificación a formato JSON para respuesta
# Caso de uso: Normalización de datos de notificaciones
def serializar_notificacion(notificacion: Notificacion):
    return {
        "codigo": notificacion.codigo,
        "fecha_envio": notificacion.fecha_envio,
        "mensaje": notificacion.mensaje,
        "leido": notificacion.leido,
        "id_usuario": notificacion.id_usuario,
        "id_incidente": notificacion.id_incidente
    }


def obtener_usuario_desde_token_ws(token: str, db: Session):
    payload = decode_token(token)
    if not payload or payload.get("tipo") != "usuario":
        return None

    codigo_usuario = payload.get("sub")
    if not codigo_usuario:
        return None

    return db.query(Usuario).filter(
        Usuario.codigo == codigo_usuario,
        Usuario.estado == True
    ).first()


@router.websocket("/ws")
async def websocket_notificaciones(
    websocket: WebSocket,
    token: str,
    db: Session = Depends(get_db)
):
    usuario = obtener_usuario_desde_token_ws(token, db)
    if not usuario:
        await websocket.close(code=1008)
        return

    await notificaciones_manager.conectar(usuario.codigo, websocket)
    try:
        total_no_leidas = db.query(Notificacion).filter(
            Notificacion.id_usuario == usuario.codigo,
            Notificacion.leido == False
        ).count()
        await websocket.send_json({
            "evento": "conexion_notificaciones",
            "id_usuario": usuario.codigo,
            "total_no_leidas": total_no_leidas
        })

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notificaciones_manager.desconectar(usuario.codigo, websocket)
    except Exception:
        notificaciones_manager.desconectar(usuario.codigo, websocket)
        await websocket.close()


# Lista las notificaciones del usuario actual con opción de filtrar por no leídas
# Caso de uso: Consulta de notificaciones por usuario
@router.get("/mis-notificaciones")
def listar_mis_notificaciones(
    solo_no_leidas: bool = False,
    limit: int = 50,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    query = db.query(Notificacion).filter(
        Notificacion.id_usuario == usuario.codigo
    )

    if solo_no_leidas:
        query = query.filter(Notificacion.leido == False)

    notificaciones = query.order_by(
        Notificacion.fecha_envio.desc()
    ).limit(min(limit, 100)).all()

    return [serializar_notificacion(n) for n in notificaciones]


@router.post("/broadcast")
def enviar_notificacion_broadcast(
    datos: BroadcastNotificacionRequest,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede enviar notificaciones generales")

    query = db.query(Usuario).filter(Usuario.estado == True)
    if datos.id_rol is not None:
        query = query.filter(Usuario.id_rol == datos.id_rol)

    usuarios = query.all()
    total = 0
    for destino in usuarios:
        notificacion = crear_notificacion(
            db,
            destino.codigo,
            datos.id_incidente,
            datos.mensaje
        )
        if notificacion:
            total += 1

    db.commit()
    return {
        "mensaje": "Notificacion general enviada",
        "total_destinatarios": total
    }


# Cuenta las notificaciones no leídas del usuario actual
# Caso de uso: Consulta de contador de notificaciones pendientes
@router.get("/no-leidas/contador")
def contar_notificaciones_no_leidas(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    total = db.query(Notificacion).filter(
        Notificacion.id_usuario == usuario.codigo,
        Notificacion.leido == False
    ).count()

    return {"total_no_leidas": total}


# Marca una notificación específica como leída
# Caso de uso: Marcar notificación individual como leída
@router.put("/{codigo}/leer")
def marcar_notificacion_leida(
    codigo: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    notificacion = db.query(Notificacion).filter(
        Notificacion.codigo == codigo,
        Notificacion.id_usuario == usuario.codigo
    ).first()

    if not notificacion:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")

    notificacion.leido = True
    db.commit()
    db.refresh(notificacion)

    return {
        "mensaje": "Notificacion marcada como leida",
        "notificacion": serializar_notificacion(notificacion)
    }


# Marca todas las notificaciones del usuario como leídas
# Caso de uso: Marcar todas las notificaciones como leídas
@router.put("/marcar-todas/leidas")
def marcar_todas_leidas(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    total = db.query(Notificacion).filter(
        Notificacion.id_usuario == usuario.codigo,
        Notificacion.leido == False
    ).update({"leido": True})

    db.commit()
    return {"mensaje": "Notificaciones marcadas como leidas", "total_actualizadas": total}
