import string
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.seguridad import Usuario, Rol, Permiso, RolPermiso
from app.schemas.usuario import (
    UsuarioResponse, UsuarioUpdate,
    RolCreate, RolResponse,
    PermisoCreate, PermisoResponse, AsignarRolRequest, AsignarPermisoRequest, CambiarRolRequest
)
from app.services.auth_service import get_permisos_usuario, registrar_bitacora, hash_password

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])
roles_router = APIRouter(prefix="/roles", tags=["Roles"])
permisos_router = APIRouter(prefix="/permisos", tags=["Permisos"])

# Construye la respuesta de usuario con sus permisos
# Caso de uso: Normalización de datos de usuario con permisos
def build_response(usuario: Usuario, db : Session) -> dict: 
    permisos  = get_permisos_usuario(db, usuario.id_rol) 
    return {
        "codigo": usuario.codigo,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "telefono": usuario.telefono,
        "estado": usuario.estado,
        "fecha_registro": usuario.fecha_registro,
        "id_rol": usuario.id_rol,
        "nombre_rol": usuario.rol.nombre if usuario.rol else "",
        "permisos": permisos
    }

# Obtiene un usuario específico por su código
# Caso de uso: CU-05 Ver perfil de usuario
@router.get("/{codigo}", response_model = UsuarioResponse)
def obtener_usuario(codigo : str , deb :Session = Depends(get_db)):
    usuario = deb.query(Usuario).filter(Usuario.codigo == codigo).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario

# Actualiza los datos de un usuario
# Caso de uso: CU-05 Actualizar perfil de usuario
@router.put ("/{codigo}", response_model = UsuarioResponse)
def actualizar_usuario(codigo: str , datos : UsuarioUpdate, db : Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.codigo == codigo).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if datos.id_rol is not None:
        rol = db.query(Rol).filter(Rol.id == datos.id_rol).first()
        if not rol:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items(): 
        setattr(usuario, campo, valor)
    db.commit()
    db.refresh(usuario)
    return usuario

# Lista todos los usuarios del sistema
# Caso de uso: Consulta general de usuarios
@router.get("/", response_model = List[UsuarioResponse])
def listar_usuarios(db:Session = Depends(get_db)):
    return db.query(Usuario).all()

# Desactiva un usuario del sistema
# Caso de uso: Desactivación de usuario
@router.delete("/{codigo}")
def desactivar_usuario(codigo: str, db : Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.codigo == codigo).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    usuario.activo = False
    db.delete(usuario)
    db.commit()
    # db.refresh(usuario)
    return {"mensaje:" "Usuario Desactivado"}

# Cambia el rol de un usuario
# Caso de uso: Gestión de roles de usuarios
@router.put("/{codigo}/rol")
def cambiar_rol_usuario(
    codigo: str,
    datos: CambiarRolRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    u = db.query(Usuario).filter(Usuario.codigo == codigo).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    rol_anterior = u.id_rol
    u.id_rol = datos.id_rol
    db.commit()
    registrar_bitacora(
        db, codigo, "CAMBIO_ROL", "USUARIOS",
        f"Rol cambiado de {rol_anterior} a {datos.id_rol}",
        request.client.host if request.client else None
    )
    return {"mensaje": "Rol actualizado correctamente"
}


# Lista todos los roles del sistema
# Caso de uso: CU-06 Gestionar roles - Consulta
@roles_router.get("/", response_model=List[RolResponse])
def listar_roles(db : Session = Depends(get_db)):
    return db.query(Rol).all()
# Crea un nuevo rol en el sistema
# Caso de uso: CU-06 Gestionar roles - Creación
@roles_router.post ("/", response_model=RolResponse)
def crear_rol(datos: RolCreate, db: Session = Depends(get_db)):
    nuevo = Rol(nombre = datos.nombre)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo



# Elimina un rol del sistema
# Caso de uso: CU-06 Gestionar roles - Eliminación
@roles_router.delete("/{id_rol}")
def eliminar_rol(id_rol: int , db : Session = Depends(get_db)):
    rol = db.query(Rol).filter(Rol.id == id_rol).first()
    if not rol : 
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    db.delete(rol)
    db.commit()
    return {"mensaje": "Rol eliminado"}

# Obtiene los permisos asignados a un rol
# Caso de uso: Consulta de permisos por rol
@roles_router.get("/{id_rol}/permisos", response_model=List[PermisoResponse])
def permisos_del_rol(id_rol: int, db: Session = Depends(get_db)):
    permisos = (
        db.query(Permiso)
        .join(RolPermiso, RolPermiso.id_permiso == Permiso.id)
        .filter(RolPermiso.id_rol == id_rol)
        .all()
    )
    return permisos

# Agrega un permiso a un rol
# Caso de uso: Asignación de permisos a roles
def agregar_permiso_rol(
    id_rol: int,
    datos: AsignarPermisoRequest,
    db: Session = Depends(get_db)
):
    existe = db.query(RolPermiso).filter(
        RolPermiso.id_rol == id_rol,
        RolPermiso.id_permiso == datos.id_permiso
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail="Permiso ya asignado")
    db.add(RolPermiso(id_rol=id_rol, id_permiso=datos.id_permiso))
    db.commit()
    return {"mensaje": "Permiso agregado al rol"
}
# Quita un permiso de un rol
# Caso de uso: Revocación de permisos de roles
@roles_router.delete("/{id_rol}/permisos/{id_permiso}")
def quitar_permiso_rol(
    id_rol: int,
    id_permiso: int,
    db: Session = Depends(get_db)
):
    rp = db.query(RolPermiso).filter(
        RolPermiso.id_rol == id_rol,
        RolPermiso.id_permiso == id_permiso
    ).first()
    if not rp:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    db.delete(rp)
    db.commit()
    return {"mensaje": "Permiso quitado del rol"}



# Lista todos los permisos del sistema
# Caso de uso: CU-07 Gestionar permisos - Consulta
@permisos_router.get("/", response_model=List[PermisoResponse])
def listar_permisos(db: Session = Depends(get_db)):
    return db.query(Permiso).all()

# Crea un nuevo permiso en el sistema
# Caso de uso: CU-07 Gestionar permisos - Creación
@permisos_router.post("/", response_model=PermisoResponse)
def crear_permiso(datos: PermisoCreate, db: Session = Depends(get_db)):
    nuevo = Permiso(nombre=datos.nombre)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

# Asigna un permiso a un rol
# Caso de uso: Asignación de permisos
@permisos_router.post("/{id_rol}/asignar/{id_permiso}")
def asignar_permiso(id_rol: int, id_permiso: int, db: Session = Depends(get_db)):
    existe = db.query(RolPermiso).filter(
        RolPermiso.id_rol == id_rol,
        RolPermiso.id_permiso == id_permiso
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail="Permiso ya asignado")
    db.add(RolPermiso(id_rol=id_rol, id_permiso=id_permiso))
    db.commit()
    return {"mensaje": "Permiso asignado correctamente"}
# Elimina un permiso del sistema
# Caso de uso: CU-07 Gestionar permisos - Eliminación
@permisos_router.delete("/{id_permiso}")
def eliminar_permiso(id_permiso: int, db: Session = Depends(get_db)):
    p = db.query(Permiso).filter(Permiso.id == id_permiso).first()
    if not p:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    db.delete(p)
    db.commit()
    return {"mensaje": "Permiso eliminado"}
