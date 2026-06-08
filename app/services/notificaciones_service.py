from datetime import datetime

from sqlalchemy.orm import Session

from app.models.notificaciones import Notificacion
from app.models.operaciones import Asignacion, Incidente
from app.models.talleres import Taller
from app.services.notificaciones_realtime import emitir_notificacion_realtime


def serializar_notificacion_realtime(notificacion: Notificacion):
    return {
        "evento": "notificacion_nueva",
        "notificacion": {
            "codigo": notificacion.codigo,
            "fecha_envio": notificacion.fecha_envio.isoformat() if notificacion.fecha_envio else None,
            "mensaje": notificacion.mensaje,
            "leido": notificacion.leido,
            "id_usuario": notificacion.id_usuario,
            "id_incidente": notificacion.id_incidente,
        }
    }


def crear_notificacion(
    db: Session,
    id_usuario: str | None,
    id_incidente: int | None,
    mensaje: str
):
    if not id_usuario:
        return None

    notificacion = Notificacion(
        fecha_envio=datetime.now(),
        mensaje=mensaje,
        leido=False,
        id_usuario=id_usuario,
        id_incidente=id_incidente
    )
    db.add(notificacion)
    db.flush()
    emitir_notificacion_realtime(
        id_usuario,
        serializar_notificacion_realtime(notificacion)
    )
    return notificacion


def notificar_incidente_cliente(
    db: Session,
    incidente: Incidente,
    mensaje: str
):
    return crear_notificacion(
        db,
        incidente.codigo_usuario,
        incidente.codigo,
        mensaje
    )


def notificar_cambio_asignacion(
    db: Session,
    asignacion: Asignacion,
    mensaje_cliente: str,
    mensaje_admin_taller: str | None = None
):
    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()
    taller = db.query(Taller).filter(
        Taller.codigo == asignacion.id_taller
    ).first()

    if incidente:
        crear_notificacion(
            db,
            incidente.codigo_usuario,
            incidente.codigo,
            mensaje_cliente
        )

    if taller and taller.usuario_id:
        crear_notificacion(
            db,
            taller.usuario_id,
            asignacion.id_incidente,
            mensaje_admin_taller or mensaje_cliente
        )
