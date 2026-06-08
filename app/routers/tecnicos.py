from fastapi import APIRouter, Depends, HTTPException, status , Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional
from jose import jwt, JWTError
from pydantic import BaseModel
from app.services.auth_service import registrar_bitacora
from app.services.notificaciones_service import notificar_cambio_asignacion
from app.services.suscripciones_service import validar_limite_tecnicos, validar_taller_operativo
from app.database import get_db
from app.models.talleres import Tecnico, Taller
from app.models.seguridad import Usuario
from app.schemas.tecnico import (
    TecnicoCreate,
    TecnicoUpdate,
    TecnicoResponse,
    TecnicoLoginRequest ,
    TecnicoCreateAdminTaller
)
from app.services.auth_service import hash_password, verify_password, create_access_token
from app.config import settings
from datetime import datetime, date
from sqlalchemy import func
from app.models.operaciones import Asignacion, HistorialEstado, Incidente


router = APIRouter(prefix="/tecnicos", tags=["Técnicos"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ESTADO_ACEPTADA_TALLER = 2
ESTADO_ASIGNADA_TECNICO = 4
ESTADO_EN_CAMINO = 5
ESTADO_FINALIZADA = 6
ESTADO_TECNICO_ACEPTO = 9
ESTADO_TECNICO_LLEGO = 10
ESTADO_ATENCION_INICIADA = 11


class ProgresoTecnicoRequest(BaseModel):
    observacion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None


def get_current_usuario(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido"
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        codigo: str = payload.get("sub")
        if codigo is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    usuario = db.query(Usuario).filter(Usuario.codigo == codigo).first()
    if not usuario:
        raise credentials_exception

    return usuario


def get_taller_admin(usuario: Usuario, db: Session):
    taller = db.query(Taller).filter(Taller.usuario_id == usuario.codigo).first()
    if not taller:
        raise HTTPException(status_code=404, detail="No tienes un taller asociado")
    return taller

# ✅ CAMBIO: helper específico para técnico logueado
def get_current_tecnico(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido"
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )

        codigo: str = payload.get("sub")
        tipo: str = payload.get("tipo")
        rol = payload.get("rol")

        if codigo is None:
            raise credentials_exception

        # ✅ CAMBIO: opcional, pero ayuda a validar que sea técnico
        if tipo != "tecnico" or rol != 3:
            raise HTTPException(
                status_code=403,
                detail="No autorizado como técnico"
            )

    except JWTError:
        raise credentials_exception

    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == codigo
    ).first()

    if not tecnico:
        raise credentials_exception

    return tecnico

# =========================
# LOGIN TÉCNICO
# =========================

@router.post("/login")
def login_tecnico(datos: TecnicoLoginRequest, request : Request,db: Session = Depends(get_db)):
    tecnico = db.query(Tecnico).filter(Tecnico.email == datos.email).first()

    if not tecnico or not verify_password(datos.password, tecnico.password):
        raise HTTPException(status_code=401, detail="CI o contraseña incorrectos")

    token = create_access_token({
        "sub": tecnico.codigo,
        "tipo": "tecnico",
        "rol": tecnico.id_rol
    })
    registrar_bitacora(
    db=db,
    codigo_usuario=None,
    codigo_tecnico=tecnico.codigo,
    id_taller=tecnico.id_taller,
    accion="LOGIN_TECNICO",
    modulo="TECNICOS",
    descripcion=f"Inicio de sesión del técnico {tecnico.codigo}",
    ip_address=request.client.host if request.client else None
    )
    db.commit()
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "tecnico": {
            "codigo": tecnico.codigo,
            "nombre": tecnico.nombre,
            "email": tecnico.email,
            "id_taller": tecnico.id_taller,
            "id_rol": tecnico.id_rol
        }
    }


# =========================
# ADMIN TALLER - SOLO SU TALLER
# =========================

@router.get("/mis-tecnicos", response_model=List[TecnicoResponse])
def listar_mis_tecnicos(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="No autorizado")

    taller = get_taller_admin(usuario, db)
    return db.query(Tecnico).filter(Tecnico.id_taller == taller.codigo).all()


@router.post("/mis-tecnicos", response_model=TecnicoResponse, status_code=201)
def crear_mi_tecnico(
    datos: TecnicoCreateAdminTaller,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
    request: Request = None
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="No autorizado")

    taller = get_taller_admin(usuario, db)
    validar_limite_tecnicos(db, taller.codigo)

    existe_codigo = db.query(Tecnico).filter(Tecnico.codigo == datos.codigo).first()
    if existe_codigo:
        raise HTTPException(status_code=400, detail="El CI ya está registrado")

    email_ci = datos.codigo.strip()

    existe_email = db.query(Tecnico).filter(Tecnico.email == email_ci).first()
    if existe_email:
        raise HTTPException(status_code=400, detail="El acceso del técnico ya está registrado")

    nuevo_tecnico = Tecnico(
        codigo=datos.codigo.strip(),
        nombre=datos.nombre.strip(),
        email=email_ci,
        password=hash_password(email_ci),
        telefono=datos.telefono.strip(),
        disponibilidad=datos.disponibilidad,
        latitud=float(taller.latitud),
        longitud=float(taller.longitud),
        id_taller=taller.codigo,
        id_rol=3
    )

    db.add(nuevo_tecnico)
    db.commit()
    db.refresh(nuevo_tecnico)
    registrar_bitacora(
        db,
        usuario.codigo,
        "Crear Tecnico",
        "Tecnicos",
        f"Se creo el tecnico{nuevo_tecnico.nombre} con Ci{ nuevo_tecnico.codigo} en el Taller{taller.codigo}",
        request.client.host if request.client else "None",  codigo_tecnico = nuevo_tecnico.codigo, id_taller = taller.codigo
    )
    return nuevo_tecnico


@router.patch("/mis-tecnicos/{codigo}", response_model=TecnicoResponse)
def actualizar_mi_tecnico(
    codigo: str,
    datos: TecnicoUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
    request: Request = None
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="No autorizado")

    taller = get_taller_admin(usuario, db)

    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == codigo,
        Tecnico.id_taller == taller.codigo
    ).first()

    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado en tu taller")

    disponibilidad_anterior = tecnico.disponibilidad
    datos_dict = datos.model_dump(exclude_unset=True)
    datos_dict.pop("id_taller", None)

    for campo, valor in datos_dict.items():
        setattr(tecnico, campo, float(valor) if campo in ["latitud", "longitud"] else valor)

    db.commit()
    db.refresh(tecnico)
    if "disponibilidad" in datos_dict and disponibilidad_anterior != tecnico.disponibilidad:
        registrar_bitacora(
            db,
            usuario.codigo,
            "CAMBIAR_DISPONIBILIDAD",
            "TECNICOS",
            f"Se cambió la disponibilidad del técnico {tecnico.codigo} a {'Disponible' if tecnico.disponibilidad else 'Ocupado'}",
            request.client.host if request.client else None
        )
    else:
        registrar_bitacora(
            db,
            usuario.codigo,
            "EDITAR_TECNICO",
            "TECNICOS",
            f"Se actualizó el técnico {tecnico.nombre} con CI {tecnico.codigo}",
            request.client.host if request.client else None,
            codigo_tecnico=tecnico.codigo,
            id_taller=taller.codigo
        )
    return tecnico


@router.delete("/mis-tecnicos/{codigo}")
def eliminar_mi_tecnico(
    codigo: str,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
    request: Request = None
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="No autorizado")

    taller = get_taller_admin(usuario, db)

    tecnico = db.query(Tecnico).filter(
        Tecnico.codigo == codigo,
        Tecnico.id_taller == taller.codigo
    ).first()

    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado en tu taller")

    db.delete(tecnico)
    db.commit()
    registrar_bitacora(
        db, usuario.codigo, "Eliminar Tecnico", "Tecnicos", f"Se elimino el tecnico {tecnico.nombre} con CI {tecnico.codigo}",
        request.client.host if request.client else "None",
        codigo_tecnico=tecnico.codigo,
        id_taller=taller.codigo
    )
    return {"mensaje": "Técnico eliminado"}


# =========================
# ADMIN PLATAFORMA - GLOBAL
# =========================

@router.post("/crear", response_model=TecnicoResponse, status_code=201)
def crear_tecnico(
    datos: TecnicoCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede crear tecnicos globalmente")

    existe_codigo = db.query(Tecnico).filter(Tecnico.codigo == datos.codigo).first()
    if existe_codigo:
        raise HTTPException(status_code=400, detail="El CI ya está registrado")

    email_ci = datos.codigo.strip()

    existe_email = db.query(Tecnico).filter(Tecnico.email == email_ci).first()
    if existe_email:
        raise HTTPException(status_code=400, detail="El acceso del técnico ya está registrado")

    taller = db.query(Taller).filter(Taller.codigo == datos.id_taller).first()
    if not taller:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    nuevo_tecnico = Tecnico(
        codigo=datos.codigo.strip(),
        nombre=datos.nombre.strip(),
        email=email_ci,
        password=hash_password(email_ci),
        telefono=datos.telefono.strip(),
        disponibilidad=datos.disponibilidad,
        latitud=float(datos.latitud),
        longitud=float(datos.longitud),
        id_taller=datos.id_taller,
        id_rol=3
    )

    db.add(nuevo_tecnico)
    db.commit()
    db.refresh(nuevo_tecnico)
    return nuevo_tecnico


@router.get("/taller/{id_taller}", response_model=List[TecnicoResponse])
def listar_por_taller(
    id_taller: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if taller.codigo != id_taller:
            raise HTTPException(status_code=403, detail="No autorizado para consultar tecnicos de otro taller")
    elif usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    return db.query(Tecnico).filter(Tecnico.id_taller == id_taller).all()





@router.patch("/{codigo}", response_model=TecnicoResponse)
def actualizar_tecnico(
    codigo: str,
    datos: TecnicoUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tecnico = db.query(Tecnico).filter(Tecnico.codigo == codigo).first()
    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado")

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if tecnico.id_taller != taller.codigo:
            raise HTTPException(status_code=403, detail="No autorizado para modificar tecnicos de otro taller")
    elif usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    datos_dict = datos.model_dump(exclude_unset=True)
    if usuario.id_rol == 2:
        datos_dict.pop("id_taller", None)

    for campo, valor in datos_dict.items():
        setattr(tecnico, campo, float(valor) if campo in ["latitud", "longitud"] else valor)

    db.commit()
    db.refresh(tecnico)
    return tecnico


@router.delete("/{codigo}")
def eliminar_tecnico(
    codigo: str,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tecnico = db.query(Tecnico).filter(Tecnico.codigo == codigo).first()
    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado")

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if tecnico.id_taller != taller.codigo:
            raise HTTPException(status_code=403, detail="No autorizado para eliminar tecnicos de otro taller")
    elif usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    db.delete(tecnico)
    db.commit()
    return {"mensaje": "Técnico eliminado"}

# ✅ CAMBIO: nombres simples para mostrar en frontend
def nombre_estado_asignacion(id_estado: int) -> str:
    estados = {
        1: "Pendiente",
        2: "Aceptada",
        3: "Rechazada",
        4: "Asignada a técnico",
        5: "En camino",
        6: "Finalizada",
        7: "Cancelada",
        8: "Sin taller disponible",
        9: "Servicio aceptado por tecnico",
        10: "Tecnico llego",
        11: "Atencion iniciada"
    }
    return estados.get(id_estado, "Desconocido")


# ✅ CAMBIO: categorías según tu catálogo base
def nombre_categoria(id_categoria: int) -> str:
    categorias = {
        1: "Batería descargada",
        2: "Llanta pinchada",
        3: "Falla de motor",
        4: "Sobrecalentamiento",
        5: "Accidente leve",
        6: "Falta de combustible",
        7: "Cerrajería vehicular",
        8: "No arranca",
        9: "Falla eléctrica",
        10: "Otro problema"
    }
    return categorias.get(id_categoria, "Otro problema")


# ✅ CAMBIO: arma respuesta común para incidente del técnico
def build_incidente_tecnico_response(asignacion: Asignacion, db: Session):
    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()

    if not incidente:
        return None

    cliente = db.query(Usuario).filter(
        Usuario.codigo == incidente.codigo_usuario
    ).first()

    return {
        "id_asignacion": asignacion.id,
        "id_incidente": incidente.codigo,
        "categoria": nombre_categoria(incidente.id_categoria_problema),
        "descripcion": incidente.descripcion,
        "cliente": f"{cliente.nombre} {cliente.apellido}".strip() if cliente else "Cliente no encontrado",
        "telefono": cliente.telefono if cliente else "",
        "fecha": asignacion.fecha_asignacion,
        "estado": nombre_estado_asignacion(asignacion.id_estado_asignacion),
        "latitud": float(incidente.latitud),
        "longitud": float(incidente.longitud),
        "id_estado_asignacion": asignacion.id_estado_asignacion
    }

# ✅ CAMBIO: dashboard real del técnico logueado
@router.get("/dashboard")
def dashboard_tecnico(
    tecnico: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    asignaciones = db.query(Asignacion).filter(
        Asignacion.id_tecnico == tecnico.codigo
    ).all()

    activos = len([
        a for a in asignaciones
        if a.id_estado_asignacion in [4, 5, 9, 10, 11]
    ])

    finalizados = len([
        a for a in asignaciones
        if a.id_estado_asignacion == 6
    ])

    hoy = db.query(Asignacion).filter(
        Asignacion.id_tecnico == tecnico.codigo,
        func.date(Asignacion.fecha_asignacion) == date.today()
    ).count()

    return {
        "activos": activos,
        "finalizados": finalizados,
        "hoy": hoy,

        # ✅ CAMBIO: por ahora fijo, luego se puede calcular con calificaciones reales
        "calificacion": 5.0,

        "tecnico": {
            "codigo": tecnico.codigo,
            "nombre": tecnico.nombre,
            "telefono": tecnico.telefono,
            "disponibilidad": tecnico.disponibilidad,
            "id_taller": tecnico.id_taller
        }
    }
# ✅ CAMBIO: incidente actual asignado al técnico
@router.get("/asignacion-actual")
def asignacion_actual_tecnico(
    tecnico: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id_tecnico == tecnico.codigo,
        Asignacion.id_estado_asignacion.in_([4, 5, 9, 10, 11])
    ).order_by(
        Asignacion.fecha_asignacion.desc()
    ).first()

    if not asignacion:
        return None

    return build_incidente_tecnico_response(asignacion, db)
# ✅ CAMBIO: historial real del técnico
@router.get("/historial")
def historial_tecnico(
    tecnico: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    asignaciones = db.query(Asignacion).filter(
        Asignacion.id_tecnico == tecnico.codigo
    ).order_by(
        Asignacion.fecha_asignacion.desc()
    ).all()

    resultado = []

    for asignacion in asignaciones:
        item = build_incidente_tecnico_response(asignacion, db)
        if item:
            resultado.append(item)

    return resultado
# ✅ CAMBIO: técnico inicia ruta hacia el cliente
def obtener_asignacion_del_tecnico(
    id_asignacion: int,
    tecnico: Tecnico,
    db: Session
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id == id_asignacion
    ).first()

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    if asignacion.id_tecnico != tecnico.codigo:
        raise HTTPException(
            status_code=403,
            detail="Solo el tecnico asignado puede actualizar el progreso"
        )

    validar_taller_operativo(db, asignacion.id_taller)

    return asignacion


def registrar_progreso_tecnico(
    db: Session,
    request: Request,
    tecnico: Tecnico,
    asignacion: Asignacion,
    accion: str,
    descripcion: str,
):
    db.add(HistorialEstado(
        fecha_cambio=datetime.now(),
        id_incidente=asignacion.id_incidente
    ))

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=tecnico.codigo,
        id_taller=asignacion.id_taller,
        accion=accion,
        modulo="PROGRESO_TECNICO",
        descripcion=descripcion,
        ip_address=request.client.host if request.client else None
    )


def respuesta_progreso(mensaje: str, asignacion: Asignacion):
    return {
        "mensaje": mensaje,
        "id_asignacion": asignacion.id,
        "id_incidente": asignacion.id_incidente,
        "id_tecnico": asignacion.id_tecnico,
        "id_estado_asignacion": asignacion.id_estado_asignacion,
        "observacion": asignacion.observacion
    }


@router.put("/progreso/{id_asignacion}/aceptar")
def tecnico_aceptar_servicio(
    id_asignacion: int,
    datos: ProgresoTecnicoRequest = ProgresoTecnicoRequest(),
    tecnico: Tecnico = Depends(get_current_tecnico),
    request: Request = None,
    db: Session = Depends(get_db)
):
    asignacion = obtener_asignacion_del_tecnico(id_asignacion, tecnico, db)

    if asignacion.id_estado_asignacion != ESTADO_ASIGNADA_TECNICO:
        raise HTTPException(
            status_code=400,
            detail="El servicio debe estar asignado al tecnico para poder aceptarlo"
        )

    asignacion.id_estado_asignacion = ESTADO_TECNICO_ACEPTO
    asignacion.observacion = datos.observacion or "Servicio aceptado por el tecnico"

    registrar_progreso_tecnico(
        db,
        request,
        tecnico,
        asignacion,
        "TECNICO_ACEPTAR_SERVICIO",
        f"El tecnico {tecnico.codigo} acepto la asignacion {asignacion.id}"
    )
    notificar_cambio_asignacion(
        db,
        asignacion,
        "El tecnico acepto tu servicio.",
        f"El tecnico {tecnico.codigo} acepto la asignacion {asignacion.id}."
    )

    db.commit()
    db.refresh(asignacion)
    return respuesta_progreso("Servicio aceptado correctamente", asignacion)


@router.put("/progreso/{id_asignacion}/en-camino")
def tecnico_marcar_en_camino(
    id_asignacion: int,
    datos: ProgresoTecnicoRequest = ProgresoTecnicoRequest(),
    tecnico: Tecnico = Depends(get_current_tecnico),
    request: Request = None,
    db: Session = Depends(get_db)
):
    asignacion = obtener_asignacion_del_tecnico(id_asignacion, tecnico, db)

    if asignacion.id_estado_asignacion not in [ESTADO_ASIGNADA_TECNICO, ESTADO_TECNICO_ACEPTO]:
        raise HTTPException(
            status_code=400,
            detail="El servicio debe estar aceptado por el tecnico antes de marcar en camino"
        )

    asignacion.id_estado_asignacion = ESTADO_EN_CAMINO
    asignacion.observacion = datos.observacion or "Tecnico en camino al cliente"

    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()
    if incidente:
        incidente.id_estado_incidente = 2

    registrar_progreso_tecnico(
        db,
        request,
        tecnico,
        asignacion,
        "INICIAR_RUTA",
        f"El tecnico {tecnico.codigo} inicio ruta para la asignacion {asignacion.id}"
    )
    notificar_cambio_asignacion(
        db,
        asignacion,
        "El tecnico esta en camino a tu ubicacion.",
        f"El tecnico {tecnico.codigo} marco en camino para la asignacion {asignacion.id}."
    )

    db.commit()
    db.refresh(asignacion)
    return respuesta_progreso("Tecnico marcado en camino", asignacion)


@router.put("/progreso/{id_asignacion}/llegada")
def tecnico_marcar_llegada(
    id_asignacion: int,
    datos: ProgresoTecnicoRequest = ProgresoTecnicoRequest(),
    tecnico: Tecnico = Depends(get_current_tecnico),
    request: Request = None,
    db: Session = Depends(get_db)
):
    raise HTTPException(
        status_code=400,
        detail="La llegada debe validarse con PIN o QR en /validacion-arribo/asignacion/{id_asignacion}/validar"
    )


@router.put("/progreso/{id_asignacion}/iniciar-atencion")
def tecnico_iniciar_atencion(
    id_asignacion: int,
    datos: ProgresoTecnicoRequest = ProgresoTecnicoRequest(),
    tecnico: Tecnico = Depends(get_current_tecnico),
    request: Request = None,
    db: Session = Depends(get_db)
):
    asignacion = obtener_asignacion_del_tecnico(id_asignacion, tecnico, db)

    if asignacion.id_estado_asignacion != ESTADO_TECNICO_LLEGO:
        raise HTTPException(
            status_code=400,
            detail="El tecnico debe marcar llegada antes de iniciar atencion"
        )

    asignacion.id_estado_asignacion = ESTADO_ATENCION_INICIADA
    asignacion.observacion = datos.observacion or "Atencion del servicio iniciada"

    registrar_progreso_tecnico(
        db,
        request,
        tecnico,
        asignacion,
        "INICIAR_ATENCION",
        f"El tecnico {tecnico.codigo} inicio atencion para la asignacion {asignacion.id}"
    )
    notificar_cambio_asignacion(
        db,
        asignacion,
        "La atencion de tu servicio fue iniciada.",
        f"El tecnico {tecnico.codigo} inicio la atencion de la asignacion {asignacion.id}."
    )

    db.commit()
    db.refresh(asignacion)
    return respuesta_progreso("Atencion iniciada correctamente", asignacion)


@router.put("/progreso/{id_asignacion}/finalizar")
def tecnico_finalizar_progreso(
    id_asignacion: int,
    datos: ProgresoTecnicoRequest = ProgresoTecnicoRequest(),
    tecnico: Tecnico = Depends(get_current_tecnico),
    request: Request = None,
    db: Session = Depends(get_db)
):
    asignacion = obtener_asignacion_del_tecnico(id_asignacion, tecnico, db)

    if asignacion.id_estado_asignacion != ESTADO_ATENCION_INICIADA:
        raise HTTPException(
            status_code=400,
            detail="El tecnico debe iniciar la atencion antes de finalizar el servicio"
        )

    incidente = db.query(Incidente).filter(
        Incidente.codigo == asignacion.id_incidente
    ).first()

    asignacion.id_estado_asignacion = ESTADO_FINALIZADA
    asignacion.observacion = datos.observacion or "Servicio finalizado por el tecnico"
    tecnico.disponibilidad = True

    if incidente:
        incidente.id_estado_incidente = 4
        incidente.fecha_cierre = datetime.now()

    registrar_progreso_tecnico(
        db,
        request,
        tecnico,
        asignacion,
        "FINALIZAR_SERVICIO",
        f"El tecnico {tecnico.codigo} finalizo la asignacion {asignacion.id}"
    )
    notificar_cambio_asignacion(
        db,
        asignacion,
        "Tu servicio fue finalizado. Ya puedes revisar el pago o evaluar el servicio.",
        f"El tecnico {tecnico.codigo} finalizo la asignacion {asignacion.id}."
    )

    db.commit()
    db.refresh(asignacion)
    return respuesta_progreso("Servicio finalizado correctamente", asignacion)


@router.put("/{id_asignacion}/iniciar-ruta")
def iniciar_ruta(
    id_asignacion: int,
    request: Request,
    tecnico_actual: Tecnico = Depends(get_current_tecnico),
    db: Session = Depends(get_db)
):
    asignacion = db.query(Asignacion).filter(
        Asignacion.id == id_asignacion
    ).first()

    if asignacion and asignacion.id_tecnico != tecnico_actual.codigo:
        raise HTTPException(status_code=403, detail="Solo el tecnico asignado puede iniciar ruta")

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    if asignacion.id_estado_asignacion != 4:
        raise HTTPException(
            status_code=400,
            detail="La asignación debe estar asignada a un técnico antes de iniciar ruta"
        )

    asignacion.id_estado_asignacion = 5
    asignacion.observacion = "Técnico en camino al cliente"

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=asignacion.id_tecnico,
        accion="INICIAR_RUTA",
        modulo="ASIGNACION",
        descripcion=f"El técnico inició ruta para la asignación {asignacion.id}",
        ip_address=request.client.host if request.client else None,
        id_taller=asignacion.id_taller
    )

    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Ruta iniciada correctamente",
        "id_asignacion": asignacion.id,
        "id_estado_asignacion": asignacion.id_estado_asignacion
    }
# ✅ CAMBIO: técnico finaliza el servicio
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
            detail="Solo se puede finalizar una asignación activa o en camino"
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
        incidente.id_estado_incidente = 4  # ajusta si tu estado finalizado usa otro número
        incidente.fecha_cierre = datetime.now()

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=asignacion.id_tecnico,
        accion="FINALIZAR_SERVICIO",
        modulo="ASIGNACION",
        descripcion=f"El técnico finalizó la asignación {asignacion.id}",
        ip_address=request.client.host if request.client else None,
        id_taller=asignacion.id_taller
    )

    db.commit()
    db.refresh(asignacion)

    return {
        "mensaje": "Servicio finalizado correctamente",
        "id_asignacion": asignacion.id,
        "id_estado_asignacion": asignacion.id_estado_asignacion
    }

@router.get("/{codigo}", response_model=TecnicoResponse)
def obtener_tecnico(
    codigo: str,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tecnico = db.query(Tecnico).filter(Tecnico.codigo == codigo).first()
    if not tecnico:
        raise HTTPException(status_code=404, detail="Técnico no encontrado")
    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if tecnico.id_taller != taller.codigo:
            raise HTTPException(status_code=403, detail="No autorizado para consultar tecnicos de otro taller")
    elif usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="No autorizado")

    return tecnico
