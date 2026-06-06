from tokenize import String
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.database import get_db
from app.models.operaciones import Incidente , Asignacion
from app.schemas.incidente import IncidenteCreate, IncidenteUpdate, IncidenteResponse
from app.models.talleres import Taller, Tecnico
from app.models.seguridad import Bitacora
from app.models.catalogo import EstadoIncidente, EstadoAsignacion
from app.routers.asignacion import crear_asignacion_automatica
from app.services.cotizaciones_service import crear_solicitud_express
from app.services.notificaciones_service import notificar_incidente_cliente
from fastapi import Request

router = APIRouter(prefix="/incidentes", tags=["Incidentes - CU10"])


# CU-10 — Crear incidente (reporte de emergencia)
@router.post("/", response_model=IncidenteResponse, status_code=201)
def crear_incidente(datos: IncidenteCreate, db: Session = Depends(get_db), request: Request = None):
    # 1. Crear el incidente
    nuevo = Incidente(
        descripcion=datos.descripcion,
        latitud=datos.latitud,
        longitud=datos.longitud,
        fecha_reporte=datos.fecha_reporte,
        id_prioridad=datos.id_prioridad,
        id_categoria_problema=datos.id_categoria_problema,
        id_estado_incidente=datos.id_estado_incidente,
        id_vehiculo=datos.id_vehiculo,
        codigo_usuario=datos.codigo_usuario,
    )

    db.add(nuevo)

    # ✅ CAMBIO: genera el código del incidente antes del commit
    db.flush()
    notificar_incidente_cliente(
        db,
        nuevo,
        "Tu reporte fue recibido. Estamos buscando un taller cercano."
    )

    # ✅ CAMBIO: envía la emergencia al taller más cercano
    if datos.cotizacion_express:
        crear_solicitud_express(db, nuevo)
        asignacion = None
    else:
        asignacion = crear_asignacion_automatica(
            id_incidente=nuevo.codigo,
            request=request,
            db=db
        )

    if asignacion:
        # ✅ Opcional: cambiar estado del incidente si tienes estado "en búsqueda/asignado"
        nuevo.id_estado_incidente = 2
    else:
        # ✅ Opcional: si no hay talleres disponibles
        # nuevo.id_estado_incidente = 1
        pass

    db.commit()
    db.refresh(nuevo)

    return nuevo


# Obtener incidente por código
@router.get("/{codigo}", response_model=IncidenteResponse)
def obtener_incidente(codigo: int, db: Session = Depends(get_db)):
    inc = db.query(Incidente).filter(Incidente.codigo == codigo).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    return inc


# Historial de incidentes por usuario
@router.get("/usuario/{codigo_usuario}", response_model=List[IncidenteResponse])
def historial_usuario(codigo_usuario: str, db: Session = Depends(get_db)):
    return db.query(Incidente).filter(
        Incidente.codigo_usuario == codigo_usuario
    ).order_by(Incidente.fecha_reporte.desc()).all()


# Actualizar estado del incidente
@router.put("/{codigo}", response_model=IncidenteResponse)
def actualizar_incidente(
    codigo: int,
    datos: IncidenteUpdate,
    db: Session = Depends(get_db)
):
    inc = db.query(Incidente).filter(Incidente.codigo == codigo).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(inc, campo, valor)
    db.commit()
    db.refresh(inc)
    return inc


# CU — Cancelar incidente
@router.put("/{codigo}/cancelar", response_model=IncidenteResponse)
def cancelar_incidente(codigo: int, db: Session = Depends(get_db)):
    inc = db.query(Incidente).filter(Incidente.codigo == codigo).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    inc.id_estado_incidente = 4  # 4 = cancelado
    inc.fecha_cierre = datetime.now()
    db.commit()
    db.refresh(inc)
    return inc


# Listar todos los incidentes (para admin/taller)
@router.get("/", response_model=List[IncidenteResponse])
def listar_incidentes(db: Session = Depends(get_db)):
    return db.query(Incidente).order_by(
        Incidente.fecha_reporte.desc()
    ).all()


def agregar_evento(eventos: list, codigo: str, titulo: str, descripcion: str, fecha, estado: str = "completado", datos: dict | None = None):
    if not fecha:
        return

    eventos.append({
        "codigo": codigo,
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha": fecha,
        "estado": estado,
        "datos": datos or {}
    })


def buscar_fecha_bitacora(db: Session, asignacion_id: int, accion: str):
    patrones = [
        f"%asignación {asignacion_id}%",
        f"%asignacion {asignacion_id}%",
    ]

    query = db.query(Bitacora).filter(Bitacora.accion == accion)
    query = query.filter(
        (Bitacora.descripcion.ilike(patrones[0])) |
        (Bitacora.descripcion.ilike(patrones[1]))
    )

    registro = query.order_by(Bitacora.fecha.desc()).first()
    return registro.fecha if registro else None


@router.get("/{id_incidente}/linea-tiempo")
def obtener_linea_tiempo_servicio(
    id_incidente: int,
    db: Session = Depends(get_db)
):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    estado_incidente = db.query(EstadoIncidente).filter(
        EstadoIncidente.id == incidente.id_estado_incidente
    ).first()

    eventos = []
    agregar_evento(
        eventos,
        "solicitud_creada",
        "Solicitud creada",
        "El cliente reportó la emergencia vehicular.",
        incidente.fecha_reporte,
        datos={
            "id_incidente": incidente.codigo,
            "latitud": float(incidente.latitud),
            "longitud": float(incidente.longitud),
            "descripcion": incidente.descripcion,
        }
    )

    asignaciones = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente
    ).order_by(Asignacion.fecha_asignacion.asc()).all()

    for asignacion in asignaciones:
        taller = db.query(Taller).filter(Taller.codigo == asignacion.id_taller).first()
        tecnico = None
        if asignacion.id_tecnico:
            tecnico = db.query(Tecnico).filter(Tecnico.codigo == asignacion.id_tecnico).first()

        estado_asignacion = db.query(EstadoAsignacion).filter(
            EstadoAsignacion.id == asignacion.id_estado_asignacion
        ).first()

        datos_base = {
            "id_asignacion": asignacion.id,
            "id_taller": asignacion.id_taller,
            "taller": taller.nombre if taller else None,
            "id_estado_asignacion": asignacion.id_estado_asignacion,
            "estado_asignacion": estado_asignacion.nombre if estado_asignacion else None,
        }

        agregar_evento(
            eventos,
            "taller_asignado",
            "Taller asignado",
            f"Se envió la solicitud al taller {taller.nombre if taller else asignacion.id_taller}.",
            asignacion.fecha_asignacion,
            datos=datos_base
        )

        agregar_evento(
            eventos,
            "taller_acepto",
            "Solicitud aceptada",
            f"El taller {taller.nombre if taller else asignacion.id_taller} aceptó la solicitud.",
            asignacion.fecha_aceptacion if asignacion.id_estado_asignacion in [2, 4, 5, 6, 9, 10, 11] else None,
            datos=datos_base
        )

        if tecnico:
            fecha_tecnico = buscar_fecha_bitacora(db, asignacion.id, "ASIGNAR_TECNICO")
            agregar_evento(
                eventos,
                "tecnico_asignado",
                "Técnico asignado",
                f"Se asignó el técnico {tecnico.nombre}.",
                fecha_tecnico or asignacion.fecha_aceptacion or asignacion.fecha_asignacion,
                datos={
                    **datos_base,
                    "codigo_tecnico": tecnico.codigo,
                    "tecnico": tecnico.nombre,
                    "telefono_tecnico": tecnico.telefono,
                }
            )

            fecha_aceptacion_tecnico = buscar_fecha_bitacora(db, asignacion.id, "TECNICO_ACEPTAR_SERVICIO")
            agregar_evento(
                eventos,
                "tecnico_acepto_servicio",
                "Servicio aceptado por tecnico",
                f"El tecnico {tecnico.nombre} acepto el servicio asignado.",
                fecha_aceptacion_tecnico if asignacion.id_estado_asignacion in [5, 6, 9, 10, 11] else None,
                datos={
                    **datos_base,
                    "codigo_tecnico": tecnico.codigo,
                    "tecnico": tecnico.nombre,
                    "telefono_tecnico": tecnico.telefono,
                }
            )

        fecha_ruta = buscar_fecha_bitacora(db, asignacion.id, "INICIAR_RUTA")
        agregar_evento(
            eventos,
            "tecnico_en_camino",
            "Técnico en camino",
            "El técnico inició la ruta hacia el cliente.",
            fecha_ruta if asignacion.id_estado_asignacion in [5, 6, 10, 11] else None,
            datos=datos_base
        )

        fecha_llegada = (
            buscar_fecha_bitacora(db, asignacion.id, "VALIDAR_ARRIBO")
            or buscar_fecha_bitacora(db, asignacion.id, "MARCAR_LLEGADA")
        )
        agregar_evento(
            eventos,
            "tecnico_llego",
            "Tecnico llego",
            "El tecnico marco su llegada al lugar del incidente.",
            fecha_llegada if asignacion.id_estado_asignacion in [6, 10, 11] else None,
            datos=datos_base
        )

        fecha_inicio_atencion = buscar_fecha_bitacora(db, asignacion.id, "INICIAR_ATENCION")
        agregar_evento(
            eventos,
            "atencion_iniciada",
            "Atencion iniciada",
            "El tecnico inicio la atencion del servicio.",
            fecha_inicio_atencion if asignacion.id_estado_asignacion in [6, 11] else None,
            datos=datos_base
        )

        fecha_finalizacion = buscar_fecha_bitacora(db, asignacion.id, "FINALIZAR_SERVICIO")
        agregar_evento(
            eventos,
            "servicio_finalizado",
            "Servicio finalizado",
            "El técnico finalizó la atención del servicio.",
            fecha_finalizacion or incidente.fecha_cierre if asignacion.id_estado_asignacion == 6 else None,
            datos=datos_base
        )

    if incidente.fecha_cierre:
        agregar_evento(
            eventos,
            "incidente_cerrado",
            "Incidente cerrado",
            "La solicitud fue cerrada en el sistema.",
            incidente.fecha_cierre,
            datos={"id_incidente": incidente.codigo}
        )

    eventos.sort(key=lambda e: e["fecha"])

    return {
        "id_incidente": incidente.codigo,
        "estado_actual": estado_incidente.nombre if estado_incidente else None,
        "id_estado_actual": incidente.id_estado_incidente,
        "total_eventos": len(eventos),
        "eventos": eventos
    }

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db


@router.get("/{id_incidente}/seguimiento")
def obtener_seguimiento_incidente(
    id_incidente: int,
    db: Session = Depends(get_db)
):
    sql = text("""
        SELECT 
            i.codigo AS id_incidente,
            COALESCE(ei.nombre, 'Reporte recibido') AS estado_incidente,

            a.id_estado_asignacion,
            ea.nombre AS estado_asignacion,

            ta.nombre AS taller_nombre,

            a.id_tecnico AS tecnico_codigo,
            CONCAT(COALESCE(u.nombre, ''), ' ', COALESCE(u.apellido, '')) AS tecnico_nombre,
            COALESCE(te.telefono, u.telefono) AS tecnico_telefono,
            te.latitud AS tecnico_latitud,
            te.longitud AS tecnico_longitud

        FROM operaciones.incidente i

        LEFT JOIN catalogo.estado_incidente ei 
            ON ei.id = i.id_estado_incidente

        LEFT JOIN operaciones.asignacion a 
            ON a.id_incidente = i.codigo

        LEFT JOIN catalogo.estado_asignacion ea 
            ON ea.id = a.id_estado_asignacion

        LEFT JOIN talleres.tecnico te 
            ON te.codigo::text = a.id_tecnico::text

        LEFT JOIN seguridad.usuario u 
            ON u.codigo::text = a.id_tecnico::text

        LEFT JOIN talleres.taller ta 
            ON ta.codigo = a.id_taller

        WHERE i.codigo = :id_incidente

        ORDER BY a.fecha_asignacion DESC NULLS LAST
        LIMIT 1
    """)

    row = db.execute(sql, {"id_incidente": id_incidente}).mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Incidente no encontrado"
        )

    return {
        "id_incidente": row["id_incidente"],
        "estado_incidente": row["estado_incidente"],
        "id_estado_asignacion": row["id_estado_asignacion"],
        "estado_asignacion": row["estado_asignacion"],
        "taller_nombre": row["taller_nombre"],
        "tecnico": {
            "codigo": row["tecnico_codigo"],
            "nombre": row["tecnico_nombre"],
            "telefono": row["tecnico_telefono"],
            "latitud": float(row["tecnico_latitud"]) if row["tecnico_latitud"] is not None else None,
            "longitud": float(row["tecnico_longitud"]) if row["tecnico_longitud"] is not None else None,
        }
    }
