from datetime import datetime
import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import Asignacion, Incidente
from app.services.notificaciones_service import crear_notificacion
from app.services.suscripciones_service import validar_taller_operativo


router = APIRouter(prefix="/tracking", tags=["Tracking"])

# Memoria temporal: no se guarda en base de datos.
ubicaciones_en_vivo = {}
notificaciones_cercania_emitidas = set()

# Si pasa mas de 900 segundos sin actualizar, se considera offline.
TTL_SEGUNDOS = 900
VELOCIDAD_PROMEDIO_KMH = 30
DISTANCIA_CERCA_KM = 1
ETA_CERCA_MINUTOS = 5


class UbicacionTecnicoRequest(BaseModel):
    id_asignacion: int
    latitud: float
    longitud: float


# Calcula la distancia en kilómetros entre dos coordenadas usando fórmula Haversine
# Caso de uso: Cálculo de distancia para tracking de técnicos
def calcular_distancia_km(lat1, lon1, lat2, lon2) -> float:
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


# Calcula el tiempo estimado de llegada en minutos basándose en distancia y velocidad
# Caso de uso: Cálculo de ETA para seguimiento de técnicos
def calcular_eta_minutos(distancia_km: float, velocidad_promedio_kmh: float) -> int:
    if velocidad_promedio_kmh <= 0:
        raise HTTPException(
            status_code=400,
            detail="La velocidad promedio debe ser mayor a 0"
        )

    if distancia_km <= 0:
        return 0

    return math.ceil((distancia_km / velocidad_promedio_kmh) * 60)


# Valida que una ubicación esté vigente (no haya expirado el TTL)
# Caso de uso: Validación de ubicaciones en tiempo real
def validar_ubicacion_vigente(ubicacion: dict):
    fecha = datetime.fromisoformat(ubicacion["fecha"])
    segundos_desde_actualizacion = int((datetime.now() - fecha).total_seconds())

    if segundos_desde_actualizacion > TTL_SEGUNDOS:
        raise HTTPException(
            status_code=404,
            detail="La ubicacion del tecnico ya no esta actualizada"
        )

    return fecha, segundos_desde_actualizacion


# Construye la respuesta de ETA con información de ubicación y tiempo estimado
# Caso de uso: Respuesta de seguimiento para cliente
def construir_eta_response(
    asignacion: Asignacion,
    incidente: Incidente,
    ubicacion: dict,
    velocidad_promedio_kmh: float
):
    fecha_ubicacion, segundos_desde_actualizacion = validar_ubicacion_vigente(ubicacion)

    distancia_km = calcular_distancia_km(
        ubicacion["latitud"],
        ubicacion["longitud"],
        incidente.latitud,
        incidente.longitud
    )
    eta_minutos = calcular_eta_minutos(distancia_km, velocidad_promedio_kmh)

    return {
        "id_incidente": incidente.codigo,
        "id_asignacion": asignacion.id,
        "codigo_tecnico": asignacion.id_tecnico,
        "estado": "Tecnico en camino",
        "distancia_km": round(distancia_km, 2),
        "eta_minutos": eta_minutos,
        "velocidad_promedio_kmh": velocidad_promedio_kmh,
        "ubicacion_tecnico": {
            "latitud": ubicacion["latitud"],
            "longitud": ubicacion["longitud"],
            "fecha": fecha_ubicacion.isoformat(),
            "segundos_desde_actualizacion": segundos_desde_actualizacion
        },
        "ubicacion_cliente": {
            "latitud": float(incidente.latitud),
            "longitud": float(incidente.longitud)
        },
        "vigente": True
    }


# Actualiza la ubicación en tiempo real de un técnico durante una asignación
# Caso de uso: Tracking de ubicación de técnico
@router.post("/ubicacion")
def actualizar_ubicacion_tecnico(
    datos: UbicacionTecnicoRequest,
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id == datos.id_asignacion
    ).first()

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    if not asignacion.id_tecnico:
        raise HTTPException(
            status_code=400,
            detail="La asignacion no tiene tecnico asignado"
        )

    validar_taller_operativo(db, asignacion.id_taller)

    if asignacion.id_estado_asignacion != 5:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede enviar ubicacion cuando el tecnico esta en camino"
        )

    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    ubicacion = {
        "id_asignacion": asignacion.id,
        "id_incidente": asignacion.id_incidente,
        "codigo_tecnico": asignacion.id_tecnico,
        "latitud": datos.latitud,
        "longitud": datos.longitud,
        "estado": "En camino",
        "fecha": datetime.now().isoformat()
    }

    ubicaciones_en_vivo[asignacion.id_incidente] = ubicacion

    eta = construir_eta_response(
        asignacion,
        incidente,
        ubicacion,
        VELOCIDAD_PROMEDIO_KMH
    )

    clave_cercania = (asignacion.id, "TECNICO_CERCA")
    if (
        clave_cercania not in notificaciones_cercania_emitidas
        and (
            eta["distancia_km"] <= DISTANCIA_CERCA_KM
            or eta["eta_minutos"] <= ETA_CERCA_MINUTOS
        )
    ):
        crear_notificacion(
            db,
            incidente.codigo_usuario,
            incidente.codigo,
            f"Tu tecnico esta cerca: aproximadamente a {eta['distancia_km']} km y {eta['eta_minutos']} minutos."
        )
        notificaciones_cercania_emitidas.add(clave_cercania)
        db.commit()

    return {
        "mensaje": "Ubicacion actualizada correctamente",
        "ubicacion": ubicacion,
        "eta": eta
    }


# Obtiene la última ubicación reportada del técnico para un incidente
# Caso de uso: Consulta de ubicación actual del técnico
@router.get("/incidente/{id_incidente}/ultima")
def obtener_ultima_ubicacion_tecnico(id_incidente: int):
    ubicacion = ubicaciones_en_vivo.get(id_incidente)

    if not ubicacion:
        raise HTTPException(
            status_code=404,
            detail="Aun no hay ubicacion del tecnico para este incidente"
        )

    validar_ubicacion_vigente(ubicacion)
    return ubicacion


# Obtiene el tiempo estimado de llegada del técnico al incidente
# Caso de uso: Consulta de ETA para seguimiento
@router.get("/incidente/{id_incidente}/eta")
def obtener_eta_incidente(
    id_incidente: int,
    velocidad_promedio_kmh: float = VELOCIDAD_PROMEDIO_KMH,
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente,
        Asignacion.id_estado_asignacion == 5
    ).order_by(Asignacion.fecha_asignacion.desc()).first()

    if not asignacion:
        raise HTTPException(
            status_code=404,
            detail="No hay tecnico en camino para este incidente"
        )

    ubicacion = ubicaciones_en_vivo.get(id_incidente)
    if not ubicacion:
        raise HTTPException(
            status_code=404,
            detail="Aun no hay ubicacion del tecnico para calcular ETA"
        )

    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    return construir_eta_response(
        asignacion,
        incidente,
        ubicacion,
        velocidad_promedio_kmh
    )
