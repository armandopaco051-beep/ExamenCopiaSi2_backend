from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import now
from app.database import get_db
from app.models.seguridad import Usuario
from app.schemas.usuario import (
    UsuarioCreate, UsuarioResponse, LoginRequest,
    Token, RecuperarPasswordRequest, CambiarPasswordRequest

)
from app.schemas.taller import TallerCreate
from app.models.talleres import Taller
from app.models.talleres import Tecnico

from app.services.auth_service import (
    hash_password, verify_password, create_access_token , get_permisos_usuario, registrar_bitacora
    )
from app.services.suscripciones_service import aprovisionar_tenant_gratis_taller

from datetime import datetime
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_

router = APIRouter(prefix="/auth", tags=["Autenticación - CU01 al CU04"])



# Construye la respuesta del usuario con su rol y permisos asociados
# Caso de uso: Helper function para normalizar respuestas de usuario
def build_usuario_response(usuario : Usuario, db :Session) -> dict : 
    "Construye la respuesta del usuario con rol y permisos "
    permisos  = get_permisos_usuario(db,usuario.id_rol)
    nombre_rol = usuario.rol.nombre if usuario.rol else ""
    return {
        "codigo": usuario.codigo,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "telefono": usuario.telefono,
        "fecha_registro": usuario.fecha_registro,
        "id_rol": usuario.id_rol,
        "estado": usuario.estado,
        "nombre_rol": nombre_rol,
        "permisos": permisos

    }

# Registra un nuevo usuario en el sistema con validaciones de CI y email únicos
# Caso de uso: CU-01 Registrar usuario
@router.post("/registro", response_model=UsuarioResponse, status_code=201)
def registrar_usuario(datos: UsuarioCreate,request : Request ,db: Session = Depends(get_db)):
      # Verificar CI único
    if db.query(Usuario).filter(Usuario.codigo == datos.codigo).first():
        raise HTTPException(status_code=400, detail="El CI ya está registrado")
    # Verificar email único
    if db.query(Usuario).filter(Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    # Regla: admin_taller debe tener taller asignado
    if datos.id_rol == 2 and not datos.codigo_taller:
        raise HTTPException(
            status_code=400,
            detail="El Admin Taller debe estar vinculado a un taller")
    nuevo = Usuario(
        codigo=datos.codigo,
        nombre=datos.nombre,
        apellido=datos.apellido,
        email=datos.email,
        password=hash_password(datos.password),
        telefono=datos.telefono,
        id_rol=datos.id_rol,
        estado=True,
        fecha_registro=datetime.now()
    )
    db.add(nuevo)
    db.flush()
    # Si es admin_taller vincular al taller
    if datos.id_rol == 2 and datos.codigo_taller:
        asignacion = TallerUsuario(
            id_usuario=datos.codigo,
            codigo_taller=datos.codigo_taller,
            fecha_asignacion=datetime.now()
        )
        db.add(asignacion)
    db.commit()
    db.refresh(nuevo)
    registrar_bitacora(
        db, datos.codigo, "REGISTRO_USUARIO",
        "AUTH", f"Usuario {datos.email} registrado con rol {datos.id_rol}",
        request.client.host if request.client else None

    )
    return build_usuario_response(nuevo, db)



# Autentica un usuario o técnico en el sistema y genera un token de acceso
# Caso de uso: CU-02 Login
@router.post("/login", response_model=Token)
def login(datos: LoginRequest, request: Request, db: Session = Depends(get_db)):
    identificador = datos.identificador.strip()

    # 1. Buscar primero en USUARIO
    usuario = db.query(Usuario).filter(
        or_(
            Usuario.email == identificador,
            Usuario.codigo == identificador
        )
    ).first()

    if usuario:
        if not verify_password(datos.password, usuario.password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        if not usuario.estado:
            raise HTTPException(status_code=403, detail="Usuario inactivo")

        if usuario.id_rol == 4:
            user_agent = request.headers.get("user-agent", "").lower()
            if "flutter" not in user_agent and "dart" not in user_agent:
                raise HTTPException(
                    status_code=403,
                    detail="Usuario no autorizado entrar desde el móvil"
                )

        permisos = get_permisos_usuario(db, usuario.id_rol)

        token = create_access_token({
            "sub": str(usuario.codigo),
            "rol": usuario.id_rol,
            "tipo": "usuario",
            "permisos": permisos
        })

        id_taller = None
        accion_bitacora = "LOGIN_USUARIO"
        modulo_bitacora = "USUARIOS"

        if usuario.id_rol == 1:
            accion_bitacora = "LOGIN_ADMIN_PLATAFORMA"
            modulo_bitacora = "USUARIOS"

        elif usuario.id_rol == 2:
            accion_bitacora = "LOGIN_ADMIN_TALLER"
            modulo_bitacora = "TALLERES"

            taller = db.query(Taller).filter(Taller.usuario_id == usuario.codigo).first()
            if taller:
                id_taller = taller.codigo

        elif usuario.id_rol == 4:
            accion_bitacora = "LOGIN_CLIENTE"
            modulo_bitacora = "CLIENTES"

        registrar_bitacora(
            db=db,
            codigo_usuario=usuario.codigo,
            codigo_tecnico=None,
            id_taller=id_taller,
            accion=accion_bitacora,
            modulo=modulo_bitacora,
            descripcion=f"Inicio de sesión del usuario {usuario.codigo}",
            ip_address=request.client.host if request.client else None
        )
        db.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "usuario": build_usuario_response(usuario, db),
            "id_taller": id_taller
        }

    # 2. Si no existe en usuario, buscar en TECNICO
    tecnico = db.query(Tecnico).filter(Tecnico.codigo == identificador).first()

    if tecnico:
        if not verify_password(datos.password, tecnico.password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        token = create_access_token({
            "sub": tecnico.codigo,
            "rol": tecnico.id_rol,
            "tipo": "tecnico",
            "permisos": []
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

        # IMPORTANTE:
        # devolvemos "usuario" normalizado para que el front no cambie mucho
        return {
            "access_token": token,
            "token_type": "bearer",
            "usuario": {
                "codigo": tecnico.codigo,
                "nombre": tecnico.nombre,
                "apellido": "",
                "email": f"{tecnico.codigo}@gmail.com",
                "telefono": tecnico.telefono,
                "fecha_registro": datetime.now(), 
                "id_rol": tecnico.id_rol,
                "estado": True,
                "nombre_rol": "TÉCNICO",
                "permisos": []
            },
            "id_taller": tecnico.id_taller
        }

    raise HTTPException(status_code=401, detail="Credenciales incorrectas")


# Inicia el proceso de recuperación de contraseña enviando un correo al usuario
# Caso de uso: CU-03 Recuperar contraseña
@router.post("/recuperar-password")
def recuperar_password(datos: RecuperarPasswordRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == datos.email).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="No existe cuenta con ese email")
    return {"mensaje": f"Correo de recuperación enviado a {datos.email}"}

# Permite al usuario cambiar su contraseña después de validar la nueva contraseña
# Caso de uso: CU-03 Cambiar contraseña
@router.put("/cambiar-password")
def cambiar_password(datos: CambiarPasswordRequest, db: Session = Depends(get_db)):
    if datos.new_password != datos.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    usuario = db.query(Usuario).filter(Usuario.email == datos.email).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    usuario.password = hash_password(datos.new_password)
    db.commit()
    db.refresh(usuario)
    return {"mensaje": "Password actualizada correctamente"}





# Cierra la sesión del usuario actual
# Caso de uso: CU-04 Cerrar sesión
@router.post("/logout")
def logout():
    return {"mensaje": "Sesión cerrada correctamente"}

# Permite al administrador de la plataforma crear un usuario con rol de admin_taller
# Caso de uso: Gestión de usuarios por administrador de plataforma
@router.post("/registro-admin-taller/usuario")
def registrar_usuario_admin_taller(datos: dict, db: Session = Depends(get_db)):
    existe = db.query(Usuario).filter(Usuario.codigo == datos["codigo"]).first()
    if existe:
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    nuevo_usuario = Usuario(
        codigo=datos["codigo"],
        nombre=datos["nombre"],
        apellido=datos["apellido"],
        email=datos["email"],
        password=hash_password(datos["password"]),
        telefono=datos["telefono"],
        id_rol=2,   # admin_taller
        estado=True,
        fecha_registro=datetime.now()
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    return {
        "mensaje": "Usuario admin_taller creado",
        "codigo_usuario": nuevo_usuario.codigo
    }
    
# Permite al administrador de la plataforma crear un taller y vincularlo a un usuario admin_taller
# Caso de uso: Gestión de talleres por administrador de plataforma
@router.post("/registro-admin-taller/taller/{codigo_usuario}")
def registrar_taller_para_admin(
    codigo_usuario: str,
    datos: TallerCreate,
    db: Session = Depends(get_db)
):
    usuario = db.query(Usuario).filter(Usuario.codigo == codigo_usuario).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    nuevo_taller = Taller(
        nombre=datos.nombre,
        telefono=datos.telefono,
        direccion=datos.direccion,
        latitud=datos.latitud,
        longitud=datos.longitud,
        activo=True,
        estado_registro="aprobado",
        horario_inicio=datos.horario_inicio,
        horario_fin=datos.horario_fin,
        usuario_id=usuario.codigo
    )

    db.add(nuevo_taller)
    db.flush()
    aprovisionar_tenant_gratis_taller(db, nuevo_taller)
    db.commit()
    db.refresh(nuevo_taller)

    return {
        "mensaje": "Taller creado correctamente",
        "codigo_taller": nuevo_taller.codigo,
        "codigo_usuario": codigo_usuario
    }

# Login especial para Swagger/Angular frontend usando OAuth2PasswordRequestForm
# Caso de uso: Autenticación para documentación Swagger y frontend Angular
@router.post("/token")
def login_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Login especial para Swagger Authorize.
    Swagger manda username/password como formulario.
    Aquí aceptamos usuario normal o técnico.
    """

    identificador = form_data.username.strip()
    password = form_data.password

    # 1. Buscar primero en USUARIO por email o código
    usuario = db.query(Usuario).filter(
        or_(
            Usuario.email == identificador,
            Usuario.codigo == identificador
        )
    ).first()

    if usuario:
        if not verify_password(password, usuario.password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        if not usuario.estado:
            raise HTTPException(status_code=403, detail="Usuario inactivo")

        permisos = get_permisos_usuario(db, usuario.id_rol)

        token = create_access_token({
            "sub": str(usuario.codigo),
            "rol": usuario.id_rol,
            "tipo": "usuario",
            "permisos": permisos
        })

        return {
            "access_token": token,
            "token_type": "bearer"
        }

    # 2. Si no existe en usuario, buscar en TÉCNICO por código o email
    tecnico = db.query(Tecnico).filter(
        or_(
            Tecnico.codigo == identificador,
            Tecnico.email == identificador
        )
    ).first()

    if tecnico:
        if not verify_password(password, tecnico.password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        token = create_access_token({
            "sub": tecnico.codigo,
            "rol": tecnico.id_rol,
            "tipo": "tecnico",
            "permisos": []
        })

        return {
            "access_token": token,
            "token_type": "bearer"
        }

    raise HTTPException(status_code=401, detail="Credenciales incorrectas")
