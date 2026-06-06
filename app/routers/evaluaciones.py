from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import Asignacion, EvaluacionServicio, Incidente
from app.models.talleres import Taller, Tecnico
from app.services.auth_service import decode_token


router = APIRouter(prefix="/evaluaciones", tags=["Evaluaciones"])

ESTADO_ASIGNACION_FINALIZADA = 6


class EvaluacionCreate(BaseModel):
    calificacion: int = Field(ge=1, le=5)
    comentario: str | None = None
    puntualidad: int | None = Field(default=None, ge=1, le=5)
    trato: int | None = Field(default=None, ge=1, le=5)
    solucion: int | None = Field(default=None, ge=1, le=5)
    precio: int | None = Field(default=None, ge=1, le=5)


def obtener_payload(token: str):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido")
    return payload


def validar_cliente_incidente(token: str, incidente: Incidente):
    payload = obtener_payload(token)
    if payload.get("tipo") != "usuario" or payload.get("rol") != 4 or payload.get("sub") != incidente.codigo_usuario:
        raise HTTPException(
            status_code=403,
            detail="Solo el cliente del incidente puede evaluar este servicio"
        )
    return payload


def validar_admin_taller(db: Session, token: str, id_taller: int):
    payload = obtener_payload(token)
    if payload.get("tipo") != "usuario" or payload.get("rol") != 2:
        raise HTTPException(status_code=403, detail="No autorizado como admin_taller")

    taller = db.query(Taller).filter(Taller.usuario_id == payload.get("sub")).first()
    if not taller or taller.codigo != id_taller:
        raise HTTPException(status_code=403, detail="No autorizado para este taller")
    return taller


def validar_tecnico(token: str, codigo_tecnico: str):
    payload = obtener_payload(token)
    if payload.get("tipo") != "tecnico" or payload.get("sub") != codigo_tecnico:
        raise HTTPException(status_code=403, detail="No autorizado para este tecnico")
    return payload


def obtener_incidente_y_asignacion_finalizada(db: Session, id_incidente: int):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    asignacion = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente
    ).order_by(Asignacion.fecha_asignacion.desc()).first()

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    if asignacion.id_estado_asignacion != ESTADO_ASIGNACION_FINALIZADA:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede evaluar un servicio finalizado"
        )

    return incidente, asignacion


def serializar_evaluacion(evaluacion: EvaluacionServicio):
    return {
        "id": evaluacion.id,
        "id_incidente": evaluacion.id_incidente,
        "id_asignacion": evaluacion.id_asignacion,
        "codigo_cliente": evaluacion.codigo_cliente,
        "codigo_tecnico": evaluacion.codigo_tecnico,
        "id_taller": evaluacion.id_taller,
        "calificacion": evaluacion.calificacion,
        "puntualidad": evaluacion.puntualidad,
        "trato": evaluacion.trato,
        "solucion": evaluacion.solucion,
        "precio": evaluacion.precio,
        "comentario": evaluacion.comentario,
        "fecha_evaluacion": evaluacion.fecha_evaluacion
    }


@router.post("/incidentes/{id_incidente}")
def registrar_evaluacion_servicio(
    id_incidente: int,
    datos: EvaluacionCreate,
    token: str,
    db: Session = Depends(get_db)
):
    incidente, asignacion = obtener_incidente_y_asignacion_finalizada(db, id_incidente)
    validar_cliente_incidente(token, incidente)

    existe = db.query(EvaluacionServicio).filter(
        EvaluacionServicio.id_incidente == id_incidente
    ).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail="Este servicio ya fue evaluado"
        )

    if not asignacion.id_tecnico:
        raise HTTPException(status_code=400, detail="La asignacion no tiene tecnico")

    evaluacion = EvaluacionServicio(
        id_incidente=incidente.codigo,
        id_asignacion=asignacion.id,
        codigo_cliente=incidente.codigo_usuario,
        codigo_tecnico=asignacion.id_tecnico,
        id_taller=asignacion.id_taller,
        calificacion=datos.calificacion,
        puntualidad=datos.puntualidad,
        trato=datos.trato,
        solucion=datos.solucion,
        precio=datos.precio,
        comentario=datos.comentario,
        fecha_evaluacion=datetime.now()
    )

    db.add(evaluacion)
    db.commit()
    db.refresh(evaluacion)

    return {
        "mensaje": "Evaluacion registrada correctamente",
        "evaluacion": serializar_evaluacion(evaluacion)
    }


@router.get("/incidentes/{id_incidente}")
def obtener_evaluacion_incidente(
    id_incidente: int,
    token: str,
    db: Session = Depends(get_db)
):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    asignacion = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente
    ).order_by(Asignacion.fecha_asignacion.desc()).first()
    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    payload = obtener_payload(token)
    codigo = payload.get("sub")
    tipo = payload.get("tipo")
    rol = payload.get("rol")

    autorizado = (
        tipo == "usuario" and rol == 4 and codigo == incidente.codigo_usuario
    ) or (
        tipo == "tecnico" and codigo == asignacion.id_tecnico
    )

    if not autorizado and tipo == "usuario" and rol == 2:
        taller = db.query(Taller).filter(Taller.usuario_id == codigo).first()
        autorizado = bool(taller and taller.codigo == asignacion.id_taller)

    if not autorizado:
        raise HTTPException(status_code=403, detail="No autorizado")

    evaluacion = db.query(EvaluacionServicio).filter(
        EvaluacionServicio.id_incidente == id_incidente
    ).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Evaluacion no encontrada")

    return serializar_evaluacion(evaluacion)


@router.get("/taller/{id_taller}")
def listar_evaluaciones_taller(
    id_taller: int,
    token: str,
    db: Session = Depends(get_db)
):
    validar_admin_taller(db, token, id_taller)

    evaluaciones = db.query(EvaluacionServicio).filter(
        EvaluacionServicio.id_taller == id_taller
    ).order_by(EvaluacionServicio.fecha_evaluacion.desc()).all()

    promedio = db.query(func.avg(EvaluacionServicio.calificacion)).filter(
        EvaluacionServicio.id_taller == id_taller
    ).scalar()

    return {
        "id_taller": id_taller,
        "total_evaluaciones": len(evaluaciones),
        "promedio_calificacion": round(float(promedio), 2) if promedio is not None else None,
        "evaluaciones": [serializar_evaluacion(evaluacion) for evaluacion in evaluaciones]
    }


@router.get("/tecnico/{codigo_tecnico}/resumen")
def resumen_evaluaciones_tecnico(
    codigo_tecnico: str,
    token: str,
    db: Session = Depends(get_db)
):
    validar_tecnico(token, codigo_tecnico)

    total = db.query(EvaluacionServicio).filter(
        EvaluacionServicio.codigo_tecnico == codigo_tecnico
    ).count()

    promedio = db.query(func.avg(EvaluacionServicio.calificacion)).filter(
        EvaluacionServicio.codigo_tecnico == codigo_tecnico
    ).scalar()

    ultimas = db.query(EvaluacionServicio).filter(
        EvaluacionServicio.codigo_tecnico == codigo_tecnico
    ).order_by(EvaluacionServicio.fecha_evaluacion.desc()).limit(10).all()

    return {
        "codigo_tecnico": codigo_tecnico,
        "total_evaluaciones": total,
        "promedio_calificacion": round(float(promedio), 2) if promedio is not None else None,
        "ultimas_evaluaciones": [serializar_evaluacion(evaluacion) for evaluacion in ultimas]
    }
