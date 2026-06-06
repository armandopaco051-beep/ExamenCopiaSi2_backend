from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import List, Optional

from jose import jwt, JWTError
from pwdlib import PasswordHash
from app.models.seguridad import RolPermiso, Usuario, Rol, Permiso, Bitacora
from app.config import settings
from sqlalchemy.orm import Session

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None
# hace la consulta para obtener los permisos de un rol
def get_permisos_usuario(db: Session, id_rol: int) ->List[str]:
    "obtener la lista de permisos de un rol"
    #hace la consulta para obtener los permisos de un rol
    permisos = (
        db.query(Permiso.nombre) 
        .join(RolPermiso, RolPermiso.id_permiso == Permiso.id)
        .filter(RolPermiso.id_rol == id_rol)
        .all()
    )
    return [p.nombre for p in permisos]



def registrar_bitacora(
    db: Session,
    codigo_usuario: Optional[str],
    accion: str,
    modulo: str,
    descripcion: str,
    ip_address: Optional[str] = None,
    codigo_tecnico: Optional[str] = None,
    id_taller: Optional[int] = None
):
    nuevo = Bitacora(
        codigo_usuario=codigo_usuario,
        codigo_tecnico=codigo_tecnico,
        id_taller=id_taller,
        accion=accion,
        modulo=modulo,
        descripcion=descripcion,
        ip_address=ip_address
    )
    db.add(nuevo)
    db.flush()
    return nuevo
