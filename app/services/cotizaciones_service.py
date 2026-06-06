from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.operaciones import Asignacion, CotizacionTaller, Incidente, SolicitudCotizacion
from app.models.talleres import Taller, Tecnico
from app.services.notificaciones_service import crear_notificacion


ESTADO_INCIDENTE_REPORTADO = 1
ESTADO_INCIDENTE_ASIGNADO = 3
ESTADO_INCIDENTE_EN_COTIZACION = 8
ESTADO_ASIGNACION_ACEPTADA = 2


def calcular_distancia_km(lat1, lon1, lat2, lon2) -> float:
    from math import atan2, cos, radians, sin, sqrt

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


def actualizar_vencimiento_solicitud(db: Session, solicitud: SolicitudCotizacion):
    ahora = datetime.now()
    if solicitud.estado in ["ABIERTA", "CON_RESPUESTAS"] and solicitud.fecha_vencimiento <= ahora:
        solicitud.estado = "VENCIDA"
        solicitud.fecha_finalizacion = ahora
        db.query(CotizacionTaller).filter(
            CotizacionTaller.id_solicitud == solicitud.id,
            CotizacionTaller.estado.in_(["INVITADA", "ENVIADA", "AJUSTE_SOLICITADO"])
        ).update({"estado": "VENCIDA"}, synchronize_session=False)

        incidente = db.query(Incidente).filter(
            Incidente.codigo == solicitud.id_incidente
        ).first()
        if incidente and incidente.id_estado_incidente == ESTADO_INCIDENTE_EN_COTIZACION:
            incidente.id_estado_incidente = ESTADO_INCIDENTE_REPORTADO
            crear_notificacion(
                db,
                incidente.codigo_usuario,
                incidente.codigo,
                "La ronda de cotizaciones vencio. Puedes solicitar una nueva ronda."
            )
        db.flush()


def obtener_solicitud(db: Session, id_solicitud: int, bloquear: bool = False):
    query = db.query(SolicitudCotizacion).filter(SolicitudCotizacion.id == id_solicitud)
    if bloquear:
        query = query.with_for_update()
    solicitud = query.first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud de cotizacion no encontrada")
    actualizar_vencimiento_solicitud(db, solicitud)
    return solicitud


def crear_solicitud_express(
    db: Session,
    incidente: Incidente,
    max_talleres: int = 3,
    tiempo_limite_minutos: int = 10,
    radio_busqueda_km: Decimal | None = None,
    observacion: str | None = None,
):
    if max_talleres < 1 or max_talleres > 3:
        raise HTTPException(
            status_code=422,
            detail="La licitacion express admite entre 1 y 3 talleres"
        )

    activa = db.query(SolicitudCotizacion).filter(
        SolicitudCotizacion.id_incidente == incidente.codigo,
        SolicitudCotizacion.estado.in_(["ABIERTA", "CON_RESPUESTAS"])
    ).first()
    if activa:
        actualizar_vencimiento_solicitud(db, activa)
        if activa.estado in ["ABIERTA", "CON_RESPUESTAS"]:
            raise HTTPException(status_code=400, detail="El incidente ya tiene una ronda de cotizacion activa")

    asignacion = db.query(Asignacion).filter(
        Asignacion.id_incidente == incidente.codigo,
        Asignacion.id_estado_asignacion.notin_([3, 7])
    ).first()
    if asignacion:
        raise HTTPException(status_code=400, detail="El incidente ya tiene una asignacion activa")

    talleres = db.query(Taller).filter(
        Taller.activo == True,
        Taller.estado_registro.in_(["aceptado", "aprobado"]),
        Taller.latitud.isnot(None),
        Taller.longitud.isnot(None)
    ).all()

    candidatos = []
    for taller in talleres:
        tiene_tecnico = db.query(Tecnico.codigo).filter(
            Tecnico.id_taller == taller.codigo,
            Tecnico.disponibilidad == True
        ).first()
        if not tiene_tecnico:
            continue

        distancia = calcular_distancia_km(
            incidente.latitud,
            incidente.longitud,
            taller.latitud,
            taller.longitud
        )
        limite = float(radio_busqueda_km) if radio_busqueda_km else float(taller.radio_cobertura_km or 10)
        if distancia <= limite:
            candidatos.append((taller, distancia))

    candidatos.sort(key=lambda item: item[1])
    seleccionados = candidatos[:max_talleres]
    if not seleccionados:
        raise HTTPException(status_code=404, detail="No hay talleres disponibles dentro de cobertura")

    ultima_ronda = db.query(SolicitudCotizacion.ronda).filter(
        SolicitudCotizacion.id_incidente == incidente.codigo
    ).order_by(SolicitudCotizacion.ronda.desc()).first()
    ronda = (ultima_ronda[0] if ultima_ronda else 0) + 1
    ahora = datetime.now()
    vencimiento = ahora + timedelta(minutes=tiempo_limite_minutos)
    radio = max(
        float(radio_busqueda_km or 0),
        max(distancia for _, distancia in seleccionados)
    )

    solicitud = SolicitudCotizacion(
        id_incidente=incidente.codigo,
        ronda=ronda,
        estado="ABIERTA",
        radio_busqueda_km=round(radio, 2),
        max_talleres=max_talleres,
        tiempo_limite_minutos=tiempo_limite_minutos,
        fecha_solicitud=ahora,
        fecha_vencimiento=vencimiento,
        observacion=observacion
    )
    db.add(solicitud)
    db.flush()

    for taller, distancia in seleccionados:
        db.add(CotizacionTaller(
            id_solicitud=solicitud.id,
            id_taller=taller.codigo,
            estado="INVITADA",
            distancia_km=round(distancia, 2),
            fecha_invitacion=ahora,
            fecha_vencimiento=vencimiento
        ))
        crear_notificacion(
            db,
            taller.usuario_id,
            incidente.codigo,
            f"Nueva solicitud de cotizacion express para el incidente {incidente.codigo}."
        )

    incidente.id_estado_incidente = ESTADO_INCIDENTE_EN_COTIZACION
    crear_notificacion(
        db,
        incidente.codigo_usuario,
        incidente.codigo,
        f"Tu solicitud de cotizacion fue enviada a {len(seleccionados)} talleres."
    )
    db.flush()
    return solicitud


def seleccionar_cotizacion(
    db: Session,
    id_cotizacion: int,
    codigo_cliente: str
):
    cotizacion = db.query(CotizacionTaller).filter(
        CotizacionTaller.id == id_cotizacion
    ).with_for_update().first()
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    solicitud = obtener_solicitud(db, cotizacion.id_solicitud, bloquear=True)
    incidente = db.query(Incidente).filter(
        Incidente.codigo == solicitud.id_incidente
    ).with_for_update().first()

    if not incidente or incidente.codigo_usuario != codigo_cliente:
        raise HTTPException(status_code=403, detail="Solo el cliente del incidente puede aceptar la cotizacion")

    if solicitud.estado not in ["ABIERTA", "CON_RESPUESTAS"]:
        db.commit()
        raise HTTPException(status_code=400, detail=f"La solicitud esta {solicitud.estado}")

    if solicitud.id_cotizacion_aceptada:
        raise HTTPException(status_code=409, detail="Ya existe una cotizacion aceptada")

    if cotizacion.estado != "ENVIADA":
        raise HTTPException(status_code=400, detail="La cotizacion no esta disponible para aceptacion")

    if cotizacion.fecha_vencimiento <= datetime.now():
        cotizacion.estado = "VENCIDA"
        db.commit()
        raise HTTPException(status_code=400, detail="La cotizacion esta vencida")

    taller = db.query(Taller).filter(
        Taller.codigo == cotizacion.id_taller,
        Taller.activo == True
    ).first()
    if not taller:
        raise HTTPException(status_code=400, detail="El taller ya no esta disponible")

    asignacion_existente = db.query(Asignacion).filter(
        Asignacion.id_incidente == incidente.codigo,
        Asignacion.id_estado_asignacion.notin_([3, 7])
    ).first()
    if asignacion_existente:
        raise HTTPException(status_code=409, detail="El incidente ya tiene una asignacion activa")

    cotizacion.estado = "ACEPTADA"
    solicitud.estado = "FINALIZADA"
    solicitud.fecha_finalizacion = datetime.now()
    solicitud.id_cotizacion_aceptada = cotizacion.id

    otras = db.query(CotizacionTaller).filter(
        CotizacionTaller.id_solicitud == solicitud.id,
        CotizacionTaller.id != cotizacion.id
    ).all()
    for otra in otras:
        if otra.estado not in ["VENCIDA", "RETIRADA"]:
            otra.estado = "RECHAZADA"
        otro_taller = db.query(Taller).filter(Taller.codigo == otra.id_taller).first()
        if otro_taller:
            crear_notificacion(
                db,
                otro_taller.usuario_id,
                incidente.codigo,
                f"Tu cotizacion para el incidente {incidente.codigo} no fue seleccionada."
            )

    asignacion = Asignacion(
        fecha_asignacion=datetime.now(),
        fecha_aceptacion=datetime.now(),
        tiempo=str(cotizacion.tiempo_llegada_minutos),
        observacion=f"Asignacion generada por cotizacion {cotizacion.id}",
        id_incidente=incidente.codigo,
        id_tecnico=None,
        id_taller=cotizacion.id_taller,
        id_estado_asignacion=ESTADO_ASIGNACION_ACEPTADA
    )
    db.add(asignacion)
    incidente.id_estado_incidente = ESTADO_INCIDENTE_ASIGNADO

    crear_notificacion(
        db,
        incidente.codigo_usuario,
        incidente.codigo,
        f"Aceptaste la cotizacion del taller {taller.nombre} por Bs {cotizacion.monto_estimado}."
    )
    crear_notificacion(
        db,
        taller.usuario_id,
        incidente.codigo,
        f"Tu cotizacion fue aceptada para el incidente {incidente.codigo}. Asigna un tecnico."
    )

    db.flush()
    return solicitud, cotizacion, asignacion
