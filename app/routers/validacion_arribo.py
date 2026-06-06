from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import Asignacion, HistorialEstado, Incidente, ValidacionArribo
from app.models.talleres import Tecnico
from app.routers.tecnicos import get_current_tecnico
from app.routers.tracking import calcular_distancia_km, ubicaciones_en_vivo, validar_ubicacion_vigente
from app.services.auth_service import registrar_bitacora
from app.services.notificaciones_service import notificar_cambio_asignacion


router = APIRouter(prefix="/validacion-arribo", tags=["Validacion Arribo"])

ESTADO_EN_CAMINO = 5
ESTADO_TECNICO_LLEGO = 10
PIN_VIGENCIA_MINUTOS = 15
MAX_INTENTOS = 5
MAX_DISTANCIA_ARRIBO_METROS = 200


class ValidarArriboRequest(BaseModel):
    pin: str | None = None
    qr_token: str | None = None
    latitud: float | None = None
    longitud: float | None = None


def generar_pin() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def generar_qr_token() -> str:
    return secrets.token_urlsafe(32)


def obtener_asignacion_en_camino_por_incidente(db: Session, id_incidente: int):
    return db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente,
        Asignacion.id_estado_asignacion == ESTADO_EN_CAMINO
    ).order_by(Asignacion.fecha_asignacion.desc()).first()


def obtener_validacion_activa(db: Session, id_asignacion: int):
    ahora = datetime.now()
    return db.query(ValidacionArribo).filter(
        ValidacionArribo.id_asignacion == id_asignacion,
        ValidacionArribo.usado == False,
        ValidacionArribo.fecha_expiracion > ahora
    ).order_by(ValidacionArribo.fecha_generacion.desc()).first()


def crear_validacion(db: Session, asignacion: Asignacion):
    ahora = datetime.now()
    validacion = ValidacionArribo(
        id_incidente=asignacion.id_incidente,
        id_asignacion=asignacion.id,
        codigo_pin=generar_pin(),
        qr_token=generar_qr_token(),
        fecha_generacion=ahora,
        fecha_expiracion=ahora + timedelta(minutes=PIN_VIGENCIA_MINUTOS),
        usado=False,
        intentos=0
    )
    db.add(validacion)
    db.commit()
    db.refresh(validacion)
    return validacion


def serializar_validacion(validacion: ValidacionArribo):
    return {
        "id_validacion": validacion.id,
        "id_incidente": validacion.id_incidente,
        "id_asignacion": validacion.id_asignacion,
        "pin": validacion.codigo_pin,
        "qr_token": validacion.qr_token,
        "fecha_generacion": validacion.fecha_generacion,
        "fecha_expiracion": validacion.fecha_expiracion,
        "vigencia_minutos": PIN_VIGENCIA_MINUTOS,
        "usado": validacion.usado
    }


def validar_ubicacion_arribo(
    incidente: Incidente,
    id_incidente: int,
    latitud: float | None,
    longitud: float | None
):
    lat_tecnico = latitud
    lon_tecnico = longitud
    fecha_ubicacion = None

    if lat_tecnico is None or lon_tecnico is None:
        ubicacion = ubicaciones_en_vivo.get(id_incidente)
        if not ubicacion:
            raise HTTPException(
                status_code=400,
                detail="No hay ubicacion del tecnico para validar cercania"
            )
        fecha_ubicacion, _ = validar_ubicacion_vigente(ubicacion)
        lat_tecnico = ubicacion["latitud"]
        lon_tecnico = ubicacion["longitud"]

    distancia_km = calcular_distancia_km(
        lat_tecnico,
        lon_tecnico,
        incidente.latitud,
        incidente.longitud
    )
    distancia_metros = distancia_km * 1000

    if distancia_metros > MAX_DISTANCIA_ARRIBO_METROS:
        raise HTTPException(
            status_code=400,
            detail=f"El tecnico esta a {round(distancia_metros, 2)} metros del cliente"
        )

    return {
        "latitud": lat_tecnico,
        "longitud": lon_tecnico,
        "fecha": fecha_ubicacion,
        "distancia_metros": round(distancia_metros, 2)
    }


@router.get("/incidente/{id_incidente}/codigo")
def obtener_codigo_arribo_cliente(
    id_incidente: int,
    db: Session = Depends(get_db)
):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    asignacion = obtener_asignacion_en_camino_por_incidente(db, id_incidente)
    if not asignacion:
        raise HTTPException(
            status_code=404,
            detail="No hay tecnico en camino para generar PIN o QR"
        )

    validacion = obtener_validacion_activa(db, asignacion.id)
    if not validacion:
        validacion = crear_validacion(db, asignacion)

    return serializar_validacion(validacion)


@router.post("/asignacion/{id_asignacion}/validar")
def validar_arribo_tecnico(
    id_asignacion: int,
    datos: ValidarArriboRequest,
    request: Request,
    tecnico: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    if not datos.pin and not datos.qr_token:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar pin o qr_token"
        )

    asignacion = db.query(Asignacion).filter(Asignacion.id == id_asignacion).first()
    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    if asignacion.id_tecnico != tecnico.codigo:
        raise HTTPException(
            status_code=403,
            detail="Solo el tecnico asignado puede validar el arribo"
        )

    if asignacion.id_estado_asignacion != ESTADO_EN_CAMINO:
        raise HTTPException(
            status_code=400,
            detail="El servicio debe estar en estado Tecnico en camino"
        )

    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    validacion = obtener_validacion_activa(db, asignacion.id)
    if not validacion:
        raise HTTPException(
            status_code=404,
            detail="No existe un PIN o QR vigente para esta asignacion"
        )

    if validacion.intentos >= MAX_INTENTOS:
        raise HTTPException(
            status_code=400,
            detail="Se supero el maximo de intentos de validacion"
        )

    pin_correcto = datos.pin is not None and datos.pin == validacion.codigo_pin
    qr_correcto = datos.qr_token is not None and datos.qr_token == validacion.qr_token

    if not pin_correcto and not qr_correcto:
        validacion.intentos += 1
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="PIN o QR incorrecto"
        )

    ubicacion_validada = validar_ubicacion_arribo(
        incidente,
        asignacion.id_incidente,
        datos.latitud,
        datos.longitud
    )

    validacion.usado = True
    validacion.fecha_uso = datetime.now()
    asignacion.id_estado_asignacion = ESTADO_TECNICO_LLEGO
    asignacion.observacion = "Arribo validado por PIN o QR"

    db.add(HistorialEstado(
        fecha_cambio=datetime.now(),
        id_incidente=asignacion.id_incidente
    ))

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=tecnico.codigo,
        id_taller=asignacion.id_taller,
        accion="VALIDAR_ARRIBO",
        modulo="VALIDACION_ARRIBO",
        descripcion=f"El tecnico {tecnico.codigo} valido arribo para la asignacion {asignacion.id}",
        ip_address=request.client.host if request.client else None
    )
    notificar_cambio_asignacion(
        db,
        asignacion,
        "El tecnico llego al lugar y valido su arribo.",
        f"El tecnico {tecnico.codigo} valido arribo para la asignacion {asignacion.id}."
    )

    db.commit()
    db.refresh(asignacion)
    db.refresh(validacion)

    return {
        "mensaje": "Arribo validado correctamente",
        "id_incidente": asignacion.id_incidente,
        "id_asignacion": asignacion.id,
        "id_tecnico": asignacion.id_tecnico,
        "id_estado_asignacion": asignacion.id_estado_asignacion,
        "estado": "Tecnico llego",
        "validacion": {
            "id_validacion": validacion.id,
            "fecha_uso": validacion.fecha_uso,
            "usado": validacion.usado
        },
        "ubicacion_validada": ubicacion_validada
    }
