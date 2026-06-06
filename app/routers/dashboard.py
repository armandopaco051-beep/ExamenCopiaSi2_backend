from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import Incidente, Asignacion
from app.models.talleres import Taller, Tecnico
from app.models.seguridad import Usuario, Bitacora
from app.routers.tecnicos import get_current_usuario, get_taller_admin

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def validar_admin_global(usuario: Usuario):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede consultar el dashboard global")


def obtener_id_taller_autorizado(id_taller: int, usuario: Usuario, db: Session) -> int:
    if usuario.id_rol == 1:
        return id_taller

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if taller.codigo != id_taller:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otro taller")
        return taller.codigo

    raise HTTPException(status_code=403, detail="No autorizado")


def nombre_dia_es(fecha):
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return dias[fecha.weekday()]


def nombre_categoria(codigo: int) -> str:
    mapa = {
        1: "Batería",
        2: "Llanta",
        3: "Motor",
        4: "Choque",
        5: "Otros"
    }
    return mapa.get(codigo, "Otros")


@router.get("/admin-plataforma")
def dashboard_admin(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    """Dashboard para Admin Plataforma"""
    validar_admin_global(usuario)

    total_incidentes = db.query(Incidente).count()

    pendientes = db.query(Incidente).filter(
        Incidente.id_estado_incidente == 1
    ).count()

    en_proceso = db.query(Incidente).filter(
        Incidente.id_estado_incidente == 2
    ).count()

    atendidos = db.query(Incidente).filter(
        Incidente.id_estado_incidente == 3
    ).count()

    total_talleres = db.query(Taller).filter(Taller.activo == True).count()

    tecnicos_disponibles = db.query(Tecnico).filter(
        Tecnico.disponibilidad == True
    ).count()

    total_tecnicos = db.query(Tecnico).count()
    total_usuarios = db.query(Usuario).count()

    # Últimos incidentes
    ultimos = db.query(Incidente).order_by(
        Incidente.fecha_reporte.desc()
    ).limit(10).all()

    # -----------------------------
    # ACTIVIDAD RECIENTE (BITÁCORA)
    # -----------------------------
    movimientos = (
        db.query(Bitacora, Usuario)
        .outerjoin(Usuario, Usuario.codigo == Bitacora.codigo_usuario)
        .order_by(Bitacora.fecha.desc())   # si en tu modelo no se llama fecha, cámbialo aquí
        .limit(8)
        .all()
    )

    actividad_reciente = []
    for b, u in movimientos:
        nombre_usuario = "Sistema"
        if u:
            nombre_usuario = f"{u.nombre} {u.apellido}".strip()

        actividad_reciente.append({
            "id": b.id,
            "accion": b.accion,
            "modulo": b.modulo,
            "descripcion": b.descripcion,
            "usuario": nombre_usuario,
            "fecha": b.fecha   # si en tu modelo no se llama fecha, cámbialo aquí
        })

    # ------------------------------------
    # TENDENCIA SEMANAL (ÚLTIMOS 7 DÍAS)
    # ------------------------------------
    hoy = datetime.now().date()
    hace_6_dias = hoy - timedelta(days=6)

    incidentes_semana = db.query(Incidente).filter(
        Incidente.fecha_reporte >= hace_6_dias
    ).all()

    conteo_por_fecha = defaultdict(int)
    for inc in incidentes_semana:
        fecha = inc.fecha_reporte.date()
        conteo_por_fecha[fecha] += 1

    tendencia_semanal = []
    for i in range(6, -1, -1):
        fecha = hoy - timedelta(days=i)
        tendencia_semanal.append({
            "dia": nombre_dia_es(fecha),
            "fecha": str(fecha),
            "total": conteo_por_fecha.get(fecha, 0)
        })

    # ------------------------------------
    # TIPO DE EMERGENCIA (ÚLTIMOS 7 DÍAS)
    # ------------------------------------
    conteo_categoria = Counter()
    for inc in incidentes_semana:
        conteo_categoria[nombre_categoria(inc.id_categoria_problema)] += 1

    tipo_emergencia = [
        {
            "categoria": categoria,
            "total": total
        }
        for categoria, total in conteo_categoria.most_common(5)
    ]

    return {
        "stats": {
            "total_incidentes": total_incidentes,
            "pendientes": pendientes,
            "en_proceso": en_proceso,
            "atendidos": atendidos,
            "total_talleres": total_talleres,
            "tecnicos_disponibles": tecnicos_disponibles,
            "total_tecnicos": total_tecnicos,
            "total_usuarios": total_usuarios
        },
        "ultimos_incidentes": [
            {
                "codigo": i.codigo,
                "descripcion": i.descripcion,
                "id_categoria": i.id_categoria_problema,
                "id_prioridad": i.id_prioridad,
                "id_estado": i.id_estado_incidente,
                "fecha_reporte": i.fecha_reporte,
                "latitud": float(i.latitud),
                "longitud": float(i.longitud)
            }
            for i in ultimos
        ],
        "actividad_reciente": actividad_reciente,
        "tendencia_semanal": tendencia_semanal,
        "tipo_emergencia": tipo_emergencia
    }


def construir_dashboard_taller(id_taller: int, db: Session):
    """CU-16: Dashboard para Admin Taller"""

    asignaciones = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller
    ).all()

    ids_incidentes = [a.id_incidente for a in asignaciones]

    total = len(ids_incidentes)

    pendientes = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        Asignacion.id_estado_asignacion == 1
    ).count()

    aceptadas = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        Asignacion.id_estado_asignacion == 2
    ).count()

    completadas = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        Asignacion.id_estado_asignacion == 5
    ).count()

    tecnicos = db.query(Tecnico).filter(
        Tecnico.id_taller == id_taller
    ).all()

    disponibles = sum(1 for t in tecnicos if t.disponibilidad)

    asig_pendientes = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        Asignacion.id_estado_asignacion == 1
    ).order_by(Asignacion.fecha_asignacion.desc()).limit(20).all()

    solicitudes = []
    for a in asig_pendientes:
        inc = db.query(Incidente).filter(
            Incidente.codigo == a.id_incidente
        ).first()

        if inc:
            solicitudes.append({
                "id_asignacion": a.id,
                "id_incidente": inc.codigo,
                "descripcion": inc.descripcion,
                "id_categoria": inc.id_categoria_problema,
                "id_prioridad": inc.id_prioridad,
                "latitud": float(inc.latitud),
                "longitud": float(inc.longitud),
                "fecha": inc.fecha_reporte,
                "id_estado_asignacion": a.id_estado_asignacion
            })

    return {
        "stats": {
            "total_solicitudes": total,
            "pendientes": pendientes,
            "aceptadas": aceptadas,
            "completadas": completadas,
            "total_tecnicos": len(tecnicos),
            "tecnicos_disponibles": disponibles
        },
        "solicitudes_pendientes": solicitudes
    }


@router.get("/admin-taller/{id_taller}")
def dashboard_taller(
    id_taller: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    id_taller_autorizado = obtener_id_taller_autorizado(id_taller, usuario, db)
    return construir_dashboard_taller(id_taller_autorizado, db)


@router.get("/mi-taller")
def dashboard_mi_taller(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede consultar este dashboard")

    taller = get_taller_admin(usuario, db)
    return construir_dashboard_taller(taller.codigo, db)
