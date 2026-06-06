from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notificaciones import Notificacion
from app.models.seguridad import Usuario
from app.routers.tecnicos import get_current_usuario


router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


def serializar_notificacion(notificacion: Notificacion):
    return {
        "codigo": notificacion.codigo,
        "fecha_envio": notificacion.fecha_envio,
        "mensaje": notificacion.mensaje,
        "leido": notificacion.leido,
        "id_usuario": notificacion.id_usuario,
        "id_incidente": notificacion.id_incidente
    }


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
