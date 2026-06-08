from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import CotizacionTaller, Incidente, SolicitudCotizacion
from app.models.seguridad import Usuario
from app.models.talleres import Taller, Tecnico
from app.routers.tecnicos import get_current_usuario, get_taller_admin
from app.schemas.cotizaciones import (
    CotizacionTallerCreate,
    RechazarCotizacionRequest,
    SolicitarAjusteRequest,
    SolicitudCotizacionCreate,
)
from app.services.cotizaciones_service import (
    actualizar_vencimiento_solicitud,
    crear_solicitud_express,
    obtener_solicitud,
    seleccionar_cotizacion,
)
from app.services.notificaciones_service import crear_notificacion
from app.services.suscripciones_service import validar_taller_operativo


router = APIRouter(prefix="/cotizaciones", tags=["Cotizaciones Express"])


# Serializa una oferta de cotización con información del taller y técnico
# Caso de uso: Normalización de datos de cotizaciones
def serializar_oferta(db: Session, oferta: CotizacionTaller):
    taller = db.query(Taller).filter(Taller.codigo == oferta.id_taller).first()
    tecnico = None
    if oferta.id_tecnico:
        tecnico = db.query(Tecnico).filter(Tecnico.codigo == oferta.id_tecnico).first()

    return {
        "id": oferta.id,
        "id_solicitud": oferta.id_solicitud,
        "id_taller": oferta.id_taller,
        "taller": {
            "nombre": taller.nombre if taller else None,
            "telefono": taller.telefono if taller else None,
            "direccion": taller.direccion if taller else None,
        },
        "id_tecnico": oferta.id_tecnico,
        "tecnico": tecnico.nombre if tecnico else None,
        "estado": oferta.estado,
        "distancia_km": float(oferta.distancia_km),
        "monto_estimado": float(oferta.monto_estimado) if oferta.monto_estimado is not None else None,
        "tiempo_llegada_minutos": oferta.tiempo_llegada_minutos,
        "tiempo_reparacion_minutos": oferta.tiempo_reparacion_minutos,
        "descripcion_servicio": oferta.descripcion_servicio,
        "observacion": oferta.observacion,
        "fecha_invitacion": oferta.fecha_invitacion,
        "fecha_respuesta": oferta.fecha_respuesta,
        "fecha_vencimiento": oferta.fecha_vencimiento,
    }


# Serializa una solicitud de cotización con todas sus ofertas
# Caso de uso: Normalización de datos de solicitudes de cotización
def serializar_solicitud(db: Session, solicitud: SolicitudCotizacion):
    actualizar_vencimiento_solicitud(db, solicitud)
    ofertas = db.query(CotizacionTaller).filter(
        CotizacionTaller.id_solicitud == solicitud.id
    ).order_by(CotizacionTaller.distancia_km.asc()).all()

    return {
        "id": solicitud.id,
        "id_incidente": solicitud.id_incidente,
        "ronda": solicitud.ronda,
        "estado": solicitud.estado,
        "radio_busqueda_km": float(solicitud.radio_busqueda_km),
        "max_talleres": solicitud.max_talleres,
        "tiempo_limite_minutos": solicitud.tiempo_limite_minutos,
        "fecha_solicitud": solicitud.fecha_solicitud,
        "fecha_vencimiento": solicitud.fecha_vencimiento,
        "fecha_finalizacion": solicitud.fecha_finalizacion,
        "id_cotizacion_aceptada": solicitud.id_cotizacion_aceptada,
        "observacion": solicitud.observacion,
        "ofertas": [serializar_oferta(db, oferta) for oferta in ofertas],
    }


# Serializa una solicitud de cotización filtrando solo las ofertas de un taller específico
# Caso de uso: Vista de solicitudes para un taller específico
def serializar_solicitud_taller(
    db: Session,
    solicitud: SolicitudCotizacion,
    id_taller: int
):
    resultado = serializar_solicitud(db, solicitud)
    resultado["ofertas"] = [
        oferta
        for oferta in resultado["ofertas"]
        if oferta["id_taller"] == id_taller
    ]
    return resultado


# Valida que el usuario sea el cliente propietario del incidente
# Caso de uso: Control de acceso para operaciones de cliente
def validar_cliente_incidente(usuario: Usuario, incidente: Incidente):
    if usuario.id_rol != 4 or incidente.codigo_usuario != usuario.codigo:
        raise HTTPException(status_code=403, detail="Solo el cliente del incidente puede realizar esta accion")


# Valida que el usuario sea administrador de la plataforma
# Caso de uso: Control de acceso para operaciones administrativas
def validar_admin(usuario: Usuario):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede supervisar cotizaciones")


# Lista todas las solicitudes de cotización para el administrador de la plataforma
# Caso de uso: Supervisión de cotizaciones por administrador
@router.get("/admin/solicitudes")
def listar_solicitudes_admin(
    estado: str | None = None,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    query = db.query(SolicitudCotizacion)
    if estado:
        query = query.filter(SolicitudCotizacion.estado == estado.upper())

    solicitudes = query.order_by(SolicitudCotizacion.fecha_solicitud.desc()).all()
    resultado = [serializar_solicitud(db, solicitud) for solicitud in solicitudes]
    db.commit()
    return resultado


# Lista las invitaciones de cotización recibidas por un taller
# Caso de uso: Gestión de invitaciones por admin de taller
@router.get("/mis-solicitudes")
def listar_solicitudes_taller(
    estado: str | None = None,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede consultar invitaciones")

    taller = get_taller_admin(usuario, db)
    query = (
        db.query(CotizacionTaller)
        .join(SolicitudCotizacion, SolicitudCotizacion.id == CotizacionTaller.id_solicitud)
        .filter(CotizacionTaller.id_taller == taller.codigo)
    )
    if estado:
        query = query.filter(CotizacionTaller.estado == estado.upper())

    ofertas = query.order_by(CotizacionTaller.fecha_invitacion.desc()).all()
    resultado = []
    for oferta in ofertas:
        solicitud = obtener_solicitud(db, oferta.id_solicitud)
        incidente = db.query(Incidente).filter(Incidente.codigo == solicitud.id_incidente).first()
        resultado.append({
            "solicitud": {
                "id": solicitud.id,
                "id_incidente": solicitud.id_incidente,
                "ronda": solicitud.ronda,
                "estado": solicitud.estado,
                "fecha_vencimiento": solicitud.fecha_vencimiento,
            },
            "incidente": {
                "descripcion": incidente.descripcion if incidente else None,
                "latitud": float(incidente.latitud) if incidente else None,
                "longitud": float(incidente.longitud) if incidente else None,
                "id_categoria_problema": incidente.id_categoria_problema if incidente else None,
                "id_prioridad": incidente.id_prioridad if incidente else None,
            },
            "cotizacion": serializar_oferta(db, oferta),
        })
    db.commit()
    return resultado


# Crea una solicitud de cotización express para un incidente
# Caso de uso: Solicitud de cotizaciones express por cliente
@router.post("/incidentes/{id_incidente}/solicitar", status_code=201)
def solicitar_cotizaciones(
    id_incidente: int,
    datos: SolicitudCotizacionCreate = SolicitudCotizacionCreate(),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    validar_cliente_incidente(usuario, incidente)

    solicitud = crear_solicitud_express(
        db,
        incidente,
        max_talleres=datos.max_talleres,
        tiempo_limite_minutos=datos.tiempo_limite_minutos,
        radio_busqueda_km=datos.radio_busqueda_km,
        observacion=datos.observacion,
    )
    db.commit()
    db.refresh(solicitud)
    return serializar_solicitud(db, solicitud)


# Obtiene todas las cotizaciones de un incidente
# Caso de uso: Consulta de cotizaciones por incidente
@router.get("/incidentes/{id_incidente}")
def obtener_cotizaciones_incidente(
    id_incidente: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    id_taller_usuario = None
    if usuario.id_rol == 4:
        validar_cliente_incidente(usuario, incidente)
    elif usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        id_taller_usuario = taller.codigo
        invitada = (
            db.query(CotizacionTaller)
            .join(SolicitudCotizacion, SolicitudCotizacion.id == CotizacionTaller.id_solicitud)
            .filter(
                SolicitudCotizacion.id_incidente == id_incidente,
                CotizacionTaller.id_taller == taller.codigo
            )
            .first()
        )
        if not invitada:
            raise HTTPException(status_code=403, detail="Tu taller no fue invitado a esta cotizacion")
    elif usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    solicitudes = db.query(SolicitudCotizacion).filter(
        SolicitudCotizacion.id_incidente == id_incidente
    ).order_by(SolicitudCotizacion.ronda.desc()).all()
    if id_taller_usuario is not None:
        respuesta = [
            serializar_solicitud_taller(db, solicitud, id_taller_usuario)
            for solicitud in solicitudes
        ]
    else:
        respuesta = [serializar_solicitud(db, solicitud) for solicitud in solicitudes]
    db.commit()
    return respuesta


# Permite a un taller responder una invitación de cotización con su oferta
# Caso de uso: Respuesta a solicitud de cotización por taller
@router.post("/solicitudes/{id_solicitud}/responder")
def responder_cotizacion(
    id_solicitud: int,
    datos: CotizacionTallerCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede responder cotizaciones")

    taller = get_taller_admin(usuario, db)
    validar_taller_operativo(db, taller.codigo)
    solicitud = obtener_solicitud(db, id_solicitud, bloquear=True)
    if solicitud.estado not in ["ABIERTA", "CON_RESPUESTAS"]:
        db.commit()
        raise HTTPException(status_code=400, detail=f"La solicitud esta {solicitud.estado}")

    oferta = db.query(CotizacionTaller).filter(
        CotizacionTaller.id_solicitud == id_solicitud,
        CotizacionTaller.id_taller == taller.codigo
    ).with_for_update().first()
    if not oferta:
        raise HTTPException(status_code=403, detail="Tu taller no fue invitado")
    if oferta.estado not in ["INVITADA", "AJUSTE_SOLICITADO"]:
        raise HTTPException(status_code=400, detail="Tu taller ya respondio esta ronda")
    if oferta.fecha_vencimiento <= datetime.now():
        oferta.estado = "VENCIDA"
        db.commit()
        raise HTTPException(status_code=400, detail="La invitacion esta vencida")

    if datos.id_tecnico:
        tecnico = db.query(Tecnico).filter(
            Tecnico.codigo == datos.id_tecnico,
            Tecnico.id_taller == taller.codigo,
            Tecnico.disponibilidad == True
        ).first()
        if not tecnico:
            raise HTTPException(status_code=400, detail="Tecnico no disponible en tu taller")

    oferta.id_tecnico = datos.id_tecnico
    oferta.monto_estimado = datos.monto_estimado
    oferta.tiempo_llegada_minutos = datos.tiempo_llegada_minutos
    oferta.tiempo_reparacion_minutos = datos.tiempo_reparacion_minutos
    oferta.descripcion_servicio = datos.descripcion_servicio
    oferta.observacion = datos.observacion
    oferta.estado = "ENVIADA"
    oferta.fecha_respuesta = datetime.now()
    solicitud.estado = "CON_RESPUESTAS"

    incidente = db.query(Incidente).filter(Incidente.codigo == solicitud.id_incidente).first()
    if incidente:
        crear_notificacion(
            db,
            incidente.codigo_usuario,
            incidente.codigo,
            f"Recibiste una cotizacion del taller {taller.nombre} por Bs {datos.monto_estimado}."
        )

    db.commit()
    db.refresh(oferta)
    return {
        "mensaje": "Cotizacion enviada correctamente",
        "cotizacion": serializar_oferta(db, oferta)
    }


# Permite a un taller rechazar una invitación de cotización
# Caso de uso: Rechazo de invitación de cotización por taller
@router.put("/solicitudes/{id_solicitud}/rechazar")
def rechazar_invitacion(
    id_solicitud: int,
    datos: RechazarCotizacionRequest = RechazarCotizacionRequest(),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede rechazar invitaciones")

    taller = get_taller_admin(usuario, db)
    solicitud = obtener_solicitud(db, id_solicitud, bloquear=True)
    if solicitud.estado not in ["ABIERTA", "CON_RESPUESTAS"]:
        db.commit()
        raise HTTPException(status_code=400, detail=f"La solicitud esta {solicitud.estado}")
    oferta = db.query(CotizacionTaller).filter(
        CotizacionTaller.id_solicitud == id_solicitud,
        CotizacionTaller.id_taller == taller.codigo
    ).with_for_update().first()
    if not oferta:
        raise HTTPException(status_code=403, detail="Tu taller no fue invitado")
    if oferta.estado not in ["INVITADA", "AJUSTE_SOLICITADO"]:
        raise HTTPException(status_code=400, detail="La invitacion ya fue respondida")

    oferta.estado = "RETIRADA"
    oferta.observacion = datos.observacion
    oferta.fecha_respuesta = datetime.now()

    incidente = db.query(Incidente).filter(Incidente.codigo == solicitud.id_incidente).first()
    if incidente:
        crear_notificacion(
            db,
            incidente.codigo_usuario,
            incidente.codigo,
            f"El taller {taller.nombre} no participara en esta ronda de cotizacion."
        )

    db.commit()
    return {"mensaje": "Invitacion rechazada correctamente"}


# Permite al cliente aceptar una cotización y asignar el taller
# Caso de uso: Aceptación de cotización por cliente
@router.put("/ofertas/{id_cotizacion}/aceptar")
def aceptar_cotizacion(
    id_cotizacion: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 4:
        raise HTTPException(status_code=403, detail="Solo el cliente puede aceptar una cotizacion")

    solicitud, cotizacion, asignacion = seleccionar_cotizacion(
        db,
        id_cotizacion,
        usuario.codigo
    )
    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Cotizacion aceptada y taller asignado",
        "id_solicitud": solicitud.id,
        "id_cotizacion": cotizacion.id,
        "id_asignacion": asignacion.id,
        "id_incidente": asignacion.id_incidente,
        "id_taller": asignacion.id_taller,
        "id_estado_asignacion": asignacion.id_estado_asignacion
    }


# Permite al administrador solicitar un ajuste a una cotización enviada
# Caso de uso: Solicitud de ajuste de cotización por administrador
@router.put("/ofertas/{id_cotizacion}/solicitar-ajuste")
def solicitar_ajuste(
    id_cotizacion: int,
    datos: SolicitarAjusteRequest,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    oferta = db.query(CotizacionTaller).filter(
        CotizacionTaller.id == id_cotizacion
    ).with_for_update().first()
    if not oferta:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    solicitud = obtener_solicitud(db, oferta.id_solicitud, bloquear=True)
    if solicitud.estado not in ["ABIERTA", "CON_RESPUESTAS"]:
        db.commit()
        raise HTTPException(status_code=400, detail=f"La solicitud esta {solicitud.estado}")

    db.refresh(oferta)
    if oferta.estado != "ENVIADA":
        raise HTTPException(status_code=400, detail="Solo se puede solicitar ajuste de una cotizacion enviada")

    oferta.estado = "AJUSTE_SOLICITADO"
    oferta.observacion = datos.observacion

    taller = db.query(Taller).filter(Taller.codigo == oferta.id_taller).first()
    if taller:
        crear_notificacion(
            db,
            taller.usuario_id,
            solicitud.id_incidente,
            f"Se solicito un ajuste para tu cotizacion del incidente {solicitud.id_incidente}."
        )

    db.commit()
    return {"mensaje": "Ajuste solicitado correctamente"}
