import json
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import ConflictoSincronizacion, Incidente
from app.routers.incidentes import crear_incidente, serializar_incidente
from app.schemas.sync import ResolverConflictoRequest, SyncIncidenteRequest
from app.services.auth_service import registrar_bitacora


router = APIRouter(prefix="/sync", tags=["Sincronizacion Offline"])

ACCIONES_RESOLUCION = {"CONSERVAR_SERVIDOR", "CREAR_NUEVO", "FUSIONAR_EVIDENCIAS", "DESCARTAR_LOCAL"}


# Calcula la distancia en kilómetros entre dos coordenadas usando fórmula Haversine
# Caso de uso: Detección de duplicados por cercanía geográfica
def distancia_km(lat1, lon1, lat2, lon2) -> float:
    radio_tierra_km = 6371
    d_lat = radians(float(lat2) - float(lat1))
    d_lon = radians(float(lon2) - float(lon1))
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(float(lat1)))
        * cos(radians(float(lat2)))
        * sin(d_lon / 2) ** 2
    )
    return radio_tierra_km * 2 * atan2(sqrt(a), sqrt(1 - a))


# Serializa un conflicto de sincronización a formato JSON
# Caso de uso: Normalización de datos de conflictos de sincronización
def serializar_conflicto(conflicto: ConflictoSincronizacion):
    return {
        "id": conflicto.id,
        "id_local_origen": conflicto.id_local_origen,
        "codigo_usuario": conflicto.codigo_usuario,
        "id_incidente_backend": conflicto.id_incidente_backend,
        "tipo_conflicto": conflicto.tipo_conflicto,
        "estado": conflicto.estado,
        "regla_arbitraje": conflicto.regla_arbitraje,
        "datos_locales": json.loads(conflicto.datos_locales_json),
        "datos_servidor": json.loads(conflicto.datos_servidor_json) if conflicto.datos_servidor_json else None,
        "resolucion": conflicto.resolucion,
        "observacion": conflicto.observacion,
        "resuelto_por": conflicto.resuelto_por,
        "fecha_deteccion": conflicto.fecha_deteccion,
        "fecha_resolucion": conflicto.fecha_resolucion,
    }


# Busca un conflicto pendiente de sincronización para un incidente local
# Caso de uso: Verificación de conflictos existentes antes de sincronizar
def buscar_conflicto_pendiente(db: Session, datos: SyncIncidenteRequest):
    return db.query(ConflictoSincronizacion).filter(
        ConflictoSincronizacion.codigo_usuario == datos.codigo_usuario,
        ConflictoSincronizacion.id_local_origen == datos.id_local_origen,
        ConflictoSincronizacion.estado == "PENDIENTE",
    ).first()


# Busca posibles incidentes duplicados basándose en usuario, vehículo, tiempo y ubicación
# Caso de uso: Detección de duplicados en sincronización offline
def buscar_posible_duplicado(db: Session, datos: SyncIncidenteRequest):
    desde = datos.fecha_reporte - timedelta(hours=2)
    hasta = datos.fecha_reporte + timedelta(hours=2)
    candidatos = db.query(Incidente).filter(
        Incidente.codigo_usuario == datos.codigo_usuario,
        Incidente.id_vehiculo == datos.id_vehiculo,
        Incidente.fecha_reporte.between(desde, hasta),
    ).all()

    for incidente in candidatos:
        if incidente.id_local_origen == datos.id_local_origen:
            continue
        distancia = distancia_km(datos.latitud, datos.longitud, incidente.latitud, incidente.longitud)
        if distancia <= 0.5:
            return incidente
    return None


# Crea un conflicto de sincronización entre datos locales y del servidor
# Caso de uso: Registro de conflictos para arbitraje manual
def crear_conflicto(db: Session, datos: SyncIncidenteRequest, incidente_backend: Incidente):
    tipo = "POSIBLE_DUPLICADO"
    regla = "RA2_NO_DUPLICAR_INCIDENTE"
    if datos.estado_local_origen == "CONCLUIDO_LOCAL" and incidente_backend.id_estado_incidente in [2, 3, 8]:
        tipo = "CONFLICTO_ESTADO"
        regla = "RA7_SERVIDOR_CON_ASIGNACION_TIENE_PRIORIDAD"

    conflicto = ConflictoSincronizacion(
        id_local_origen=datos.id_local_origen,
        codigo_usuario=datos.codigo_usuario,
        id_incidente_backend=incidente_backend.codigo,
        tipo_conflicto=tipo,
        estado="PENDIENTE",
        regla_arbitraje=regla,
        datos_locales_json=json.dumps(datos.model_dump(mode="json"), default=str),
        datos_servidor_json=json.dumps(serializar_incidente(incidente_backend), default=str),
        fecha_deteccion=datetime.now(),
    )
    db.add(conflicto)
    db.flush()
    return conflicto


# Sincroniza un incidente creado offline con el servidor
# Caso de uso: Sincronización de incidentes offline con detección de conflictos
@router.post("/incidentes")
def sincronizar_incidente(
    datos: SyncIncidenteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    existente = db.query(Incidente).filter(
        Incidente.codigo_usuario == datos.codigo_usuario,
        Incidente.id_local_origen == datos.id_local_origen,
    ).first()
    if existente:
        return {
            "estado_sync": "SINCRONIZADO",
            "duplicado": True,
            "id_local_origen": datos.id_local_origen,
            "id_backend": existente.codigo,
            "incidente": serializar_incidente(existente),
        }

    conflicto_pendiente = buscar_conflicto_pendiente(db, datos)
    if conflicto_pendiente:
        return {
            "estado_sync": "CONFLICTO",
            "requiere_arbitraje": True,
            "conflicto": serializar_conflicto(conflicto_pendiente),
        }

    duplicado = buscar_posible_duplicado(db, datos)
    if duplicado:
        conflicto = crear_conflicto(db, datos, duplicado)
        registrar_bitacora(
            db=db,
            codigo_usuario=datos.codigo_usuario,
            accion="CONFLICTO_SINCRONIZACION",
            modulo="SYNC",
            descripcion=f"Conflicto offline {conflicto.id} para incidente local {datos.id_local_origen}",
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
        db.refresh(conflicto)
        return {
            "estado_sync": "CONFLICTO",
            "requiere_arbitraje": True,
            "conflicto": serializar_conflicto(conflicto),
        }

    nuevo = crear_incidente(datos, db, request)
    return {
        "estado_sync": "SINCRONIZADO",
        "duplicado": False,
        "id_local_origen": datos.id_local_origen,
        "id_backend": nuevo.codigo,
        "incidente": serializar_incidente(nuevo),
    }


# Lista los conflictos de sincronización con filtros opcionales
# Caso de uso: Consulta de conflictos de sincronización
@router.get("/conflictos")
def listar_conflictos(
    estado: str = "PENDIENTE",
    codigo_usuario: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ConflictoSincronizacion)
    if estado:
        query = query.filter(ConflictoSincronizacion.estado == estado.upper())
    if codigo_usuario:
        query = query.filter(ConflictoSincronizacion.codigo_usuario == codigo_usuario)
    conflictos = query.order_by(ConflictoSincronizacion.fecha_deteccion.desc()).all()
    return [serializar_conflicto(conflicto) for conflicto in conflictos]


# Lista los conflictos pendientes de arbitraje
# Caso de uso: Consulta de conflictos pendientes para administrador
@router.get("/pendientes")
def listar_pendientes_arbitraje(db: Session = Depends(get_db)):
    conflictos = db.query(ConflictoSincronizacion).filter(
        ConflictoSincronizacion.estado == "PENDIENTE"
    ).order_by(ConflictoSincronizacion.fecha_deteccion.desc()).all()
    return [serializar_conflicto(conflicto) for conflicto in conflictos]


# Resuelve un conflicto de sincronización según la acción especificada
# Caso de uso: Arbitraje manual de conflictos de sincronización
@router.post("/resolver-conflicto/{id_conflicto}")
def resolver_conflicto(
    id_conflicto: int,
    datos: ResolverConflictoRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    accion = datos.accion.upper()
    if accion not in ACCIONES_RESOLUCION:
        raise HTTPException(status_code=400, detail="Accion de resolucion no valida")

    conflicto = db.query(ConflictoSincronizacion).filter(
        ConflictoSincronizacion.id == id_conflicto
    ).with_for_update().first()
    if not conflicto:
        raise HTTPException(status_code=404, detail="Conflicto no encontrado")
    if conflicto.estado != "PENDIENTE":
        raise HTTPException(status_code=400, detail="El conflicto ya fue resuelto")

    id_backend = conflicto.id_incidente_backend
    incidente = None

    if accion == "CREAR_NUEVO":
        datos_locales = json.loads(conflicto.datos_locales_json)
        nuevo_payload = SyncIncidenteRequest.model_validate(datos_locales)
        incidente = crear_incidente(nuevo_payload, db, request)
        id_backend = incidente.codigo
    elif accion in ["CONSERVAR_SERVIDOR", "FUSIONAR_EVIDENCIAS"]:
        incidente = db.query(Incidente).filter(Incidente.codigo == conflicto.id_incidente_backend).first()
        if not incidente:
            raise HTTPException(status_code=404, detail="Incidente servidor no encontrado")
    elif accion == "DESCARTAR_LOCAL":
        incidente = None

    conflicto.estado = "RESUELTO"
    conflicto.resolucion = accion
    conflicto.observacion = datos.observacion
    conflicto.resuelto_por = datos.resuelto_por
    conflicto.id_incidente_backend = id_backend
    conflicto.fecha_resolucion = datetime.now()

    registrar_bitacora(
        db=db,
        codigo_usuario=datos.resuelto_por,
        accion="RESOLVER_CONFLICTO_SYNC",
        modulo="SYNC",
        descripcion=f"Conflicto {id_conflicto} resuelto con accion {accion}",
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(conflicto)
    if incidente:
        db.refresh(incidente)

    return {
        "mensaje": "Conflicto resuelto correctamente",
        "id_backend": id_backend,
        "accion": accion,
        "conflicto": serializar_conflicto(conflicto),
        "incidente": serializar_incidente(incidente) if incidente else None,
    }
