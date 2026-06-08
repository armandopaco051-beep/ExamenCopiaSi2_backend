from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models.operaciones import Incidente, Asignacion
from app.models.talleres import Taller, Tecnico
from app.services.auth_service import registrar_bitacora
from app.routers.tecnicos import get_current_usuario, get_current_tecnico, get_taller_admin
from app.services.notificaciones_service import crear_notificacion, notificar_cambio_asignacion
from app.services.suscripciones_service import validar_limite_incidentes_mensuales, validar_taller_operativo
import math
from app.schemas.asignacion import ResponderAsignacion, AsignacionCreate, AsignarTecnicoRequest
from sqlalchemy import text
from app.models.seguridad import Usuario
router =  APIRouter(prefix="/asignacion", tags=["Asignacion"])


# Valida que el usuario tenga acceso a operar sobre un taller específico
# Caso de uso: Control de acceso para administradores y administradores de taller
def validar_acceso_taller(usuario: Usuario, db: Session, id_taller: int):
    if usuario.id_rol == 1:
        return

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if taller.codigo == id_taller:
            return

    raise HTTPException(status_code=403, detail="No autorizado para operar sobre este taller")


# Valida que el usuario tenga acceso a operar sobre una asignación específica
# Caso de uso: Control de acceso para operaciones sobre asignaciones
def validar_acceso_asignacion_taller(usuario: Usuario, db: Session, asignacion: Asignacion):
    validar_acceso_taller(usuario, db, asignacion.id_taller)

# Calcula la distancia en kilómetros entre dos coordenadas usando la fórmula de Haversine
# Caso de uso: Motor de asignación inteligente para determinar talleres cercanos
def calcular_distancia(lat1, lon1, lat2, lon2) -> float:
    """Distancia en km con fórmula de Haversine"""
    R = 6371
    d_lat = math.radians(float(lat2) - float(lat1))
    d_lon = math.radians(float(lon2) - float(lon1))
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(float(lat1))) *
         math.cos(math.radians(float(lat2))) *
         math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Obtiene el radio de cobertura de un taller en kilómetros
# Caso de uso: Motor de asignación inteligente para verificar si un incidente está dentro del área de cobertura
def obtener_radio_cobertura(taller: Taller) -> float:
    return float(taller.radio_cobertura_km or 10.0)


# Calcula la distancia entre un taller y un incidente
# Caso de uso: Motor de asignación inteligente para ordenar talleres por cercanía
def calcular_distancia_taller_incidente(taller: Taller, incidente: Incidente) -> float:
    return calcular_distancia(
        incidente.latitud,
        incidente.longitud,
        taller.latitud,
        taller.longitud
    )
# ✅ CAMBIO: busca el siguiente taller más cercano que todavía NO recibió ese incidente
# Busca el siguiente taller más cercano disponible que aún no haya recibido el incidente
# Caso de uso: CU-17 Motor de asignación inteligente - Reasignación automática
def asignar_siguiente_taller(db: Session, incidente: Incidente):
    """
    Busca el taller más cercano disponible que aún no haya recibido
    este incidente. Crea una asignación pendiente para ese taller.
    """
 # evitar crear otra asignación si ya hay una pendiente/aceptada/asignada
    asignacion_activa = db.query(Asignacion).filter(
        Asignacion.id_incidente == incidente.codigo,
        Asignacion.id_estado_asignacion.in_([1, 2, 4, 5])
    ).first()

    if asignacion_activa:
        return asignacion_activa

    # talleres que ya recibieron este incidente
    talleres_ya_intentados = db.query(Asignacion.id_taller).filter(
        Asignacion.id_incidente == incidente.codigo
    ).all()

    ids_excluidos = [t[0] for t in talleres_ya_intentados]

    # buscar talleres activos, aprobados y con ubicación
    query = db.query(Taller).filter(
        Taller.activo == True,
        Taller.latitud.isnot(None),
        Taller.longitud.isnot(None)
    )

    #  si tu tabla tiene estado_registro, usamos solo aprobados
    query = query.filter(Taller.estado_registro == "aprobado")

    if ids_excluidos:
        query = query.filter(~Taller.codigo.in_(ids_excluidos))

    talleres = query.all()

    if not talleres:
        return None

    candidatos_en_cobertura = []
    for taller in talleres:
        distancia = calcular_distancia_taller_incidente(taller, incidente)
        if distancia <= obtener_radio_cobertura(taller):
            candidatos_en_cobertura.append({
                "taller": taller,
                "distancia": distancia
            })

    if not candidatos_en_cobertura:
        return None

    candidatos_en_cobertura.sort(key=lambda c: c["distancia"])
    mejor = candidatos_en_cobertura[0]
    taller_elegido = mejor["taller"]
    distancia = mejor["distancia"]

    # crear solicitud pendiente para el taller más cercano
    nueva_asignacion = Asignacion(
        fecha_asignacion=datetime.now(),
        fecha_aceptacion=None,
        tiempo=str(round(distancia, 2)),
        observacion="Solicitud pendiente de aceptación por el taller",
        id_incidente=incidente.codigo,
        id_tecnico=None,              # ✅ Todavía no hay técnico
        id_taller=taller_elegido.codigo,
        id_estado_asignacion=1        # ✅ 1 = Pendiente
    )

    db.add(nueva_asignacion)
    db.flush()
    notificar_cambio_asignacion(
        db,
        nueva_asignacion,
        "Estamos buscando confirmacion de un taller cercano para atender tu emergencia.",
        f"Nueva emergencia cercana disponible: incidente {incidente.codigo}."
    )

    return nueva_asignacion

# Obtiene la lista de talleres candidatos para atender un incidente con sus scores
# Caso de uso: CU-17 Motor de asignación inteligente - Retorna lista de técnicos candidatos
@router.get("/candidatos/{id_incidente}")
def obtener_candidatos(id_incidente: int ,  db: Session = Depends(get_db)): 
    #Cu17 motor de asignacion inteligente retorna lista de tecnicos candidatos
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    talleres_activos = db.query(Taller).filter(Taller.activo == True).all()
    candidatos=[] 
    for taller in talleres_activos: 
        #tecnicos disponible
        tecnicos_disponible = db.query(Tecnico).filter(Tecnico.id_taller == taller.codigo, Tecnico.disponibilidad == True).all()
        if not tecnicos_disponible: 
            continue 
        #calcular las distancia 
        distancia  = calcular_distancia(
            incidente.latitud, incidente.longitud, taller.latitud, taller.longitud 
        )
        radio_cobertura = obtener_radio_cobertura(taller)
        if distancia > radio_cobertura:
            continue
        #Score menor distancia = mayor Score 
        #prioridad alta de suma de puntos
        score_distancia = max(0,100 - distancia * 5 )
        bonus_prioridad = 20 if incidente.id_prioridad == 1 else 0
        bonus_tecnicos = min (20, len(tecnicos_disponible)*5)
        score_total = score_distancia + bonus_prioridad + bonus_tecnicos
        candidatos.append({
            "taller": { 
                "codigo" : taller.codigo,
                "nombre": taller.nombre,
                "telefono" : taller.telefono,
                "direccion" : taller.direccion,
                "radio_cobertura_km": radio_cobertura
                
            },
            "distancia_km" : round(distancia,2),
            "dentro_cobertura": True,
            "tecnicos_disponible" : len(tecnicos_disponible),
            "tecnico":[{
                "codigo" : t.codigo,
                "telefono" : t.telefono,
                "disponibilidad" : t.disponibilidad
            } for t in tecnicos_disponible],
            "score": round(score_total,1),
            "recomendado" : False 
        })
        #ordenar por score 
        #que hace la linea 73 ? respuesta : ordena la lista de candidatos por score en orden descendente
        
    candidatos.sort(key = lambda x: x["score"], reverse=True)
    #marca el mejor candidato
    if candidatos : 
        candidatos[0]["recomendado"] = True
    return {
    "id_incidente":  id_incidente,
    "total_candidatos" : len(candidatos), 
    "candidatos": candidatos[:5] #top 5 significa ? respuesta : los primeros 5 candidatos de la lista ordenada por score
    
    }
# Crea una asignación automática enviando el incidente al taller más cercano disponible
# Caso de uso: CU-17 Motor de asignación inteligente - Asignación automática de incidentes
@router.post("/auto/{id_incidente}", status_code=201)
def crear_asignacion_automatica(
    id_incidente: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Crea una asignación automática para que el taller más cercano
    reciba la solicitud del incidente.
    """

    # 1. Buscar incidente
    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    # 2. Evitar asignaciones duplicadas para el mismo incidente
    asignacion_existente = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente
    ).first()

    if asignacion_existente:
        return {
            "mensaje": "El incidente ya tiene una asignación",
            "id_asignacion": asignacion_existente.id,
            "id_taller": asignacion_existente.id_taller,
            "id_estado_asignacion": asignacion_existente.id_estado_asignacion
        }

    # 3. Buscar talleres activos con ubicación
    talleres = db.query(Taller).filter(
        Taller.activo == True,
        Taller.latitud.isnot(None),
        Taller.longitud.isnot(None)
    ).all()

    if not talleres:
        raise HTTPException(
            status_code=404,
            detail="No hay talleres activos disponibles"
        )

    candidatos = []

    # 4. Calcular distancia y verificar técnicos disponibles
    for taller in talleres:
        tecnicos_disponibles = db.query(Tecnico).filter(
            Tecnico.id_taller == taller.codigo,
            Tecnico.disponibilidad == True
        ).all()

        # Si quieres que solo reciban talleres con técnicos disponibles,
        # deja este continue. Si quieres que cualquier taller activo reciba,
        # puedes quitar este bloque.
        if not tecnicos_disponibles:
            continue

        distancia = calcular_distancia(
            incidente.latitud,
            incidente.longitud,
            taller.latitud,
            taller.longitud
        )

        radio_cobertura = obtener_radio_cobertura(taller)
        if distancia > radio_cobertura:
            continue

        candidatos.append({
            "taller": taller,
            "distancia": distancia,
            "radio_cobertura_km": radio_cobertura,
            "tecnicos_disponibles": len(tecnicos_disponibles)
        })

    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail="No hay talleres con técnicos disponibles"
        )

    # 5. Elegir el taller más cercano
    candidatos.sort(key=lambda x: x["distancia"])
    mejor = candidatos[0]
    taller_elegido = mejor["taller"]

    # 6. Crear asignación PENDIENTE para el taller
    nueva = Asignacion(
        fecha_asignacion=datetime.now(),
        fecha_aceptacion=None,
        tiempo=round(mejor["distancia"] * 3),  # estimación simple en minutos
        observacion="Asignación automática pendiente de aceptación por el taller",
        id_incidente=incidente.codigo,
        id_tecnico=None,  # todavía no se asigna técnico
        id_taller=taller_elegido.codigo,
        id_estado_asignacion=1  # pendiente
    )

    db.add(nueva)

    # 7. Cambiar estado del incidente a "en revisión" o "en proceso"
    incidente.id_estado_incidente = 2
    notificar_cambio_asignacion(
        db,
        nueva,
        f"Tu emergencia fue enviada al taller {taller_elegido.nombre}.",
        f"Nueva emergencia cercana disponible: incidente {incidente.codigo}."
    )

    registrar_bitacora(
        db=db,
        codigo_usuario=incidente.codigo_usuario,
        accion="ASIGNACION_AUTOMATICA_TALLER",
        modulo="ASIGNACION",
        descripcion=f"Incidente {incidente.codigo} enviado al taller {taller_elegido.codigo}",
        ip_address=request.client.host if request.client else None,
        id_taller=taller_elegido.codigo
    )

    db.commit()
    db.refresh(nueva)

    return {
        "mensaje": "Incidente enviado al taller más cercano",
        "id_asignacion": nueva.id,
        "id_incidente": incidente.codigo,
        "id_taller": taller_elegido.codigo,
        "nombre_taller": taller_elegido.nombre,
        "distancia_km": round(mejor["distancia"], 2),
        "radio_cobertura_km": mejor["radio_cobertura_km"],
        "dentro_cobertura": True,
        "id_estado_asignacion": nueva.id_estado_asignacion
    }

# Crea una asignación manual de un técnico a una orden de trabajo
# Caso de uso: CU-19 Asignar técnico a orden de trabajo
@router.post("", status_code=201)
def crear_asignacion(
    datos: AsignacionCreate,
    request: Request,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    """CU-19: Asignar técnico a orden de trabajo"""
    incidente = db.query(Incidente).filter(
        Incidente.codigo == datos.id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    taller = db.query(Taller).filter(Taller.codigo == datos.id_taller).first()
    if not taller:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    validar_acceso_taller(usuario, db, datos.id_taller)

    distancia_taller = calcular_distancia_taller_incidente(taller, incidente)
    radio_cobertura = obtener_radio_cobertura(taller)
    if distancia_taller > radio_cobertura:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El incidente esta a {round(distancia_taller, 2)} km "
                f"y supera el radio de cobertura de {radio_cobertura} km"
            )
        )

    nueva = Asignacion(
        fecha_asignacion=datetime.now(),
        fecha_aceptacion=datetime.now(),
        tiempo=datos.tiempo_estimado,
        observacion=datos.observacion,
        id_incidente=datos.id_incidente,
        id_tecnico=datos.id_tecnico,
        id_taller=datos.id_taller,
        id_estado_asignacion=1  # pendiente
    )
    db.add(nueva)

    # Actualizar estado del incidente a "en proceso"
    incidente.id_estado_incidente = 2

    # Marcar técnico como no disponible
    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == datos.id_tecnico).first()
    if tecnico:
        tecnico.disponibilidad = False
    registrar_bitacora(
        db=db,
        codigo_usuario=incidente.codigo_usuario,
        accion="ASIGNACION_AUTOMATICA",
        modulo="ASIGNACION",
        descripcion=f"Incidente {incidente.codigo} asignado automáticamente al taller {datos.id_taller}",
        ip_address=request.client.host if request.client else None,
        id_taller=datos.id_taller
    )
    db.commit()
    db.refresh(nueva)


    return {
        "id_asignacion": nueva.id,
        "mensaje": "Técnico asignado correctamente",
        "estado": "pendiente"
    }


# Permite que un taller acepte una solicitud de asignación pendiente
# Caso de uso: Aceptación de solicitudes de emergencia por parte del taller
@router.put("/{id_asignacion}/aceptar")
def aceptar_asignacion(
    id_asignacion: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id == id_asignacion
    ).first()

    if asignacion:
        validar_acceso_asignacion_taller(usuario, db, asignacion)

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    validar_limite_incidentes_mensuales(db, asignacion.id_taller)

    if asignacion.id_estado_asignacion != 1:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede aceptar una solicitud pendiente"
        )

    # ✅ CAMBIO:
    # El taller acepta, pero todavía NO se asigna técnico.
    asignacion.id_estado_asignacion = 2  # 2 = Aceptada
    asignacion.fecha_aceptacion = datetime.now()
    asignacion.observacion = "Solicitud aceptada por el taller"
    notificar_cambio_asignacion(
        db,
        asignacion,
        "Tu solicitud fue aceptada por el taller. Pronto se asignara un tecnico.",
        f"Solicitud {asignacion.id_incidente} aceptada por tu taller."
    )

    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Solicitud aceptada correctamente",
        "id_asignacion": asignacion.id,
        "id_incidente": asignacion.id_incidente,
        "id_taller": asignacion.id_taller,
        "estado": asignacion.id_estado_asignacion
    }

# Busca el siguiente taller más cercano que no haya rechazado el incidente
# Caso de uso: Reasignación automática cuando un taller rechaza una solicitud
def buscar_siguiente_taller_para_incidente(
    db: Session,
    id_incidente: int
):
    sql = text("""
        SELECT 
            t.codigo AS id_taller,
            t.nombre AS taller_nombre,
            t.usuario_id AS id_usuario_taller,
            (
                6371 * acos(
                    cos(radians(i.latitud)) *
                    cos(radians(t.latitud)) *
                    cos(radians(t.longitud) - radians(i.longitud)) +
                    sin(radians(i.latitud)) *
                    sin(radians(t.latitud))
                )
            ) AS distancia_km
        FROM operaciones.incidente i
        JOIN talleres.taller t
            ON t.activo = true
        WHERE i.codigo = :id_incidente
          AND t.latitud IS NOT NULL
          AND t.longitud IS NOT NULL

          -- Evita mandar otra vez al mismo taller que ya rechazó
          AND t.codigo NOT IN (
              SELECT a.id_taller
              FROM operaciones.asignacion a
              WHERE a.id_incidente = :id_incidente
          )

        ORDER BY distancia_km ASC
        LIMIT 1
    """)

    return db.execute(sql, {"id_incidente": id_incidente}).mappings().first()


# Busca el siguiente taller más cercano dentro del radio de cobertura que no haya rechazado el incidente
# Caso de uso: Reasignación automática con filtro de cobertura geográfica
def buscar_siguiente_taller_en_cobertura_para_incidente(
    db: Session,
    id_incidente: int
):
    sql = text("""
        WITH talleres_candidatos AS (
            SELECT
                t.codigo AS id_taller,
                t.nombre AS taller_nombre,
                t.usuario_id AS id_usuario_taller,
                COALESCE(t.radio_cobertura_km, 10.0) AS radio_cobertura_km,
                (
                    6371 * acos(
                        LEAST(1, GREATEST(-1,
                            cos(radians(i.latitud)) *
                            cos(radians(t.latitud)) *
                            cos(radians(t.longitud) - radians(i.longitud)) +
                            sin(radians(i.latitud)) *
                            sin(radians(t.latitud))
                        ))
                    )
                ) AS distancia_km
            FROM operaciones.incidente i
            JOIN talleres.taller t
                ON t.activo = true
            WHERE i.codigo = :id_incidente
              AND t.latitud IS NOT NULL
              AND t.longitud IS NOT NULL
              AND t.codigo NOT IN (
                  SELECT a.id_taller
                  FROM operaciones.asignacion a
                  WHERE a.id_incidente = :id_incidente
              )
        )
        SELECT
            id_taller,
            taller_nombre,
            id_usuario_taller,
            radio_cobertura_km,
            distancia_km
        FROM talleres_candidatos
        WHERE distancia_km <= radio_cobertura_km
        ORDER BY distancia_km ASC
        LIMIT 1
    """)

    return db.execute(sql, {"id_incidente": id_incidente}).mappings().first()
# Permite que un taller rechace una solicitud de asignación y la reenvía al siguiente taller cercano
# Caso de uso: Rechazo de solicitudes de emergencia con reasignación automática
@router.put("/{id_asignacion}/rechazar")
def rechazar_asignacion(
    id_asignacion: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    # 1. Buscar la asignación actual
    asignacion = db.execute(text("""
        SELECT 
            id,
            id_incidente,
            id_taller,
            id_tecnico,
            id_estado_asignacion
        FROM operaciones.asignacion
        WHERE id = :id_asignacion
    """), {"id_asignacion": id_asignacion}).mappings().first()

    if not asignacion:
        raise HTTPException(
            status_code=404,
            detail="Asignación no encontrada"
        )

    validar_acceso_taller(usuario, db, asignacion["id_taller"])
    id_incidente = asignacion["id_incidente"]

    # 2. Marcar asignación actual como rechazada
    # CAMBIA este ID según tu tabla catalogo.estado_asignacion
    ID_ESTADO_RECHAZADO = 5

    db.execute(text("""
        UPDATE operaciones.asignacion
        SET id_estado_asignacion = :estado
        WHERE id = :id_asignacion
    """), {
        "estado": ID_ESTADO_RECHAZADO,
        "id_asignacion": id_asignacion
    })

    # 3. Buscar siguiente taller cercano
    siguiente_taller = buscar_siguiente_taller_en_cobertura_para_incidente(
        db,
        id_incidente
    )

    if not siguiente_taller:
        # Si no hay más talleres, actualizar incidente como sin disponibilidad
        db.execute(text("""
            UPDATE operaciones.incidente
            SET id_estado_incidente = id_estado_incidente
            WHERE codigo = :id_incidente
        """), {"id_incidente": id_incidente})

        incidente_sin_taller = db.query(Incidente).filter(
            Incidente.codigo == id_incidente
        ).first()
        if incidente_sin_taller:
            crear_notificacion(
                db,
                incidente_sin_taller.codigo_usuario,
                id_incidente,
                "Tu solicitud fue rechazada y no se encontraron talleres disponibles en cobertura."
            )

        db.commit()

        return {
            "ok": True,
            "mensaje": "Solicitud rechazada. No hay más talleres cercanos disponibles.",
            "reasignado": False
        }

    # 4. Crear nueva asignación para el siguiente taller
    # CAMBIA este ID según tu tabla catalogo.estado_asignacion
    ID_ESTADO_PENDIENTE = 1

    nueva_asignacion = db.execute(text("""
        INSERT INTO operaciones.asignacion (
            id_incidente,
            id_taller,
            id_tecnico,
            id_estado_asignacion,
            fecha_asignacion
        )
        VALUES (
            :id_incidente,
            :id_taller,
            NULL,
            :estado,
            NOW()
        )
        RETURNING id
    """), {
        "id_incidente": id_incidente,
        "id_taller": siguiente_taller["id_taller"],
        "estado": ID_ESTADO_PENDIENTE
    }).mappings().first()

    # 5. Crear notificación para el nuevo taller
    # Ajusta los nombres de columnas según tu tabla notificaciones.notificacion
    #db.execute(text("""
    #    INSERT INTO notificaciones.notificacion (
    #        id_incidente,
    #        codigo_usuario,
    #        titulo,
    #        mensaje,
    #        leida,
      #      fecha_creacion
        #)
       # :codigo_usuario,
       # :titulo,
       # :mensaje,
       # false,
       # NOW()
  #      )
   # """), {
    #    "id_incidente": id_incidente,
     #   "codigo_usuario": siguiente_taller["id_usuario_taller"],
      #  "titulo": "Nueva solicitud de emergencia",
       # "mensaje": f"Nuevo incidente cercano asignado al taller {siguiente_taller['taller_nombre']}"
    #})

    incidente_reasignado = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()
    if incidente_reasignado:
        crear_notificacion(
            db,
            incidente_reasignado.codigo_usuario,
            id_incidente,
            f"Tu solicitud fue reenviada al taller {siguiente_taller['taller_nombre']}."
        )

    crear_notificacion(
        db,
        siguiente_taller["id_usuario_taller"],
        id_incidente,
        f"Nueva solicitud de emergencia asignada a tu taller: incidente {id_incidente}."
    )

    db.commit()

    return {
        "ok": True,
        "mensaje": "Solicitud rechazada y reenviada a otro taller cercano.",
        "reasignado": True,
        "nuevo_taller": {
            "id_taller": siguiente_taller["id_taller"],
            "nombre": siguiente_taller["taller_nombre"],
            "distancia_km": float(siguiente_taller["distancia_km"]),
            "radio_cobertura_km": float(siguiente_taller["radio_cobertura_km"]),
            "dentro_cobertura": True
        },
        "nueva_asignacion": nueva_asignacion["id"]
    }
    
# Lista todas las asignaciones activas de un taller específico
# Caso de uso: Gestión de solicitudes por parte del administrador del taller
@router.get("/taller/{id_taller}")
def asignaciones_del_taller(
    id_taller: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    """Lista las asignaciones activas de un taller"""
    validar_acceso_taller(usuario, db, id_taller)

    # ❌ ANTES:
    # asignaciones = db.query(Asignacion).filter(
    #     Asignacion.id_taller == id_taller
    # ).order_by(Asignacion.fecha_asignacion.desc()).all()

    # ✅ CAMBIO:
    # Mostramos solo solicitudes activas del taller:
    # 1 pendiente, 2 aceptada, 4 asignada a técnico, 5 en camino
    asignaciones = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        Asignacion.id_estado_asignacion.in_([1, 2, 4, 5, 6, 9, 10, 11])
    ).order_by(Asignacion.fecha_asignacion.desc()).all()

    resultado = []

    for a in asignaciones:
        inc = db.query(Incidente).filter(
            Incidente.codigo == a.id_incidente
        ).first()

        usuario = None

        # ✅ CAMBIO: buscamos el cliente que reportó el incidente
        if inc:
            usuario = db.query(Usuario).filter(
                Usuario.codigo == inc.codigo_usuario
            ).first()

        resultado.append({
            "id": a.id,
            "id_incidente": a.id_incidente,
            "id_tecnico": a.id_tecnico,
            "id_estado_asignacion": a.id_estado_asignacion,
            "fecha_asignacion": a.fecha_asignacion,
            "fecha_aceptacion": a.fecha_aceptacion,
            "tiempo": a.tiempo,
            "observacion": a.observacion,
            "incidente": {
                "descripcion": inc.descripcion if inc else "",
                "latitud": float(inc.latitud) if inc else 0,
                "longitud": float(inc.longitud) if inc else 0,
                "id_categoria": inc.id_categoria_problema if inc else 0,
                "id_prioridad": inc.id_prioridad if inc else 0,

                # ✅ CAMBIO: datos del cliente para el modal de detalle
                "usuario": {
                    "codigo": usuario.codigo if usuario else "",
                    "nombre": usuario.nombre if usuario else "",
                    "apellido": usuario.apellido if usuario else "",
                    "telefono": usuario.telefono if usuario else "",
                    "email": usuario.email if usuario else "",
                }
            } if inc else {}
        })

    return resultado

# Asigna un técnico específico a una asignación que ya fue aceptada por el taller
# Caso de uso: Asignación de técnico a una solicitud aceptada
@router.put("/{id_asignacion}/tecnico/{codigo_tecnico}")
def asignar_tecnico_a_asignacion(
    id_asignacion: int,
    datos: AsignarTecnicoRequest,
    request: Request,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(Asignacion.id == id_asignacion).first()
    if asignacion:
        validar_acceso_asignacion_taller(usuario, db, asignacion)

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    validar_taller_operativo(db, asignacion.id_taller)

    if asignacion.id_estado_asignacion != 2:
        raise HTTPException(
            status_code=400,
            detail="Primero el taller debe aceptar la asignación"
        )

    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == datos.codigo_tecnico,
        Tecnico.id_taller == asignacion.id_taller,
        Tecnico.disponibilidad == True
    ).first()

    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado en este taller")

    if not tecnico.disponibilidad:
        raise HTTPException(status_code=400, detail="El técnico no está disponible")

    asignacion.id_tecnico = tecnico.codigo
    asignacion.id_estado_asignacion = 4  # asignada_tecnico
    asignacion.observacion = datos.observacion

    tecnico.disponibilidad = False
    notificar_cambio_asignacion(
        db,
        asignacion,
        f"Se asigno el tecnico {tecnico.nombre} a tu servicio.",
        f"Se asigno el tecnico {tecnico.nombre} al incidente {asignacion.id_incidente}."
    )

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=tecnico.codigo,
        accion="ASIGNAR_TECNICO",
        modulo="ASIGNACION",
        descripcion=f"Se asignó el técnico {tecnico.codigo} a la asignación {asignacion.id}",
        ip_address=request.client.host if request.client else None,
        id_taller=asignacion.id_taller
    )

    db.commit()

    return {
        "mensaje": "Técnico asignado correctamente",
        "id_asignacion": asignacion.id,
        "id_tecnico": tecnico.codigo
    }
# Permite que el técnico asignado inicie la ruta hacia la ubicación del cliente
# Caso de uso: Inicio de ruta por parte del técnico asignado
@router.put("/{id_asignacion}/iniciar-ruta")
def iniciar_ruta(
    id_asignacion: int ,
    request : Request,
    tecnico_actual: Tecnico = Depends(get_current_tecnico),
    db: Session= Depends(get_db)
): 
    asignacion = db.query(Asignacion).filter(Asignacion.id == id_asignacion).first() 
    if asignacion and asignacion.id_tecnico != tecnico_actual.codigo:
        raise HTTPException(status_code=403, detail="Solo el tecnico asignado puede iniciar ruta")

    if not asignacion: 
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    validar_taller_operativo(db, asignacion.id_taller)

    if asignacion.id_estado_asignacion != 4:
        raise HTTPException(status_code=400, detail="La asignación no está en estado 'asignada_tecnico'")
    
    asignacion.id_estado_asignacion = 5  # en_ruta
    asignacion.observacion = "Tecnico en camino al Cliente";

    incidente = db.query(Incidente).filter(Incidente.codigo == asignacion.id_incidente).first()

    if incidente: 
        #ajusta este numero segun tu catologo de estado de incidente
        incidente.id_estado_incidente=2

    notificar_cambio_asignacion(
        db,
        asignacion,
        "El tecnico esta en camino a tu ubicacion.",
        f"El tecnico {asignacion.id_tecnico} inicio ruta para la asignacion {asignacion.id}."
    )

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=asignacion.id_tecnico,
        accion="INICIAR_RUTA",
        modulo="ASIGNACION",
        descripcion=f"Se inició la ruta para la asignación {asignacion.id}",
        ip_address=request.client.host if request.client else None,
        id_taller=asignacion.id_taller
    )

    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Ruta iniciada correctamente",
        "id_asignacion": asignacion.id
    }

# Permite que el técnico finalice el servicio y marque la asignación como completada
# Caso de uso: Finalización de servicio por parte del técnico
@router.put("/{id_asignacion}/finalizar")
def finalizar_servicio(
    id_asignacion: int,
    request: Request,
    tecnico_actual: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id == id_asignacion
    ).first()

    if asignacion and asignacion.id_tecnico != tecnico_actual.codigo:
        raise HTTPException(status_code=403, detail="Solo el tecnico asignado puede finalizar este servicio")

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    if asignacion.id_estado_asignacion not in [4, 5]:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede finalizar una asignación activa"
        )

    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == asignacion.id_tecnico
    ).first()

    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()

    asignacion.id_estado_asignacion = 6
    asignacion.observacion = "Servicio finalizado por el técnico"

    if tecnico:
        tecnico.disponibilidad = True

    if incidente:
        # Ajusta este número según tu catálogo de estado_incidente
        incidente.id_estado_incidente = 4
        incidente.fecha_cierre = datetime.now()

    notificar_cambio_asignacion(
        db,
        asignacion,
        "Tu servicio fue finalizado. Ya puedes revisar el pago o evaluar el servicio.",
        f"El tecnico {asignacion.id_tecnico} finalizo la asignacion {asignacion.id}."
    )

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=asignacion.id_tecnico,
        id_taller=asignacion.id_taller,
        accion="FINALIZAR_SERVICIO",
        modulo="ASIGNACION",
        descripcion=f"El técnico finalizó la asignación {asignacion.id}",
        ip_address=request.client.host if request.client else None
    )

    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Servicio finalizado correctamente",
        "id_asignacion": asignacion.id,
        "id_estado_asignacion": asignacion.id_estado_asignacion
    }
