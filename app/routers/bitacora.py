from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.seguridad import Bitacora, Usuario
from app.models.talleres import Taller, Tecnico
from app.schemas.usuario import BitacoraResponse

# usa la misma dependencia que ya usas en tecnicos.py
from app.routers.tecnicos import get_current_usuario


router = APIRouter(prefix="/bitacora", tags=["Bitácora"])


# Lista los registros de bitácora con filtros por módulo, usuario, técnico o taller
# Caso de uso: Auditoría y seguimiento de acciones en el sistema
@router.get("", response_model=List[BitacoraResponse])
def listar_bitacora(
    modulo: Optional[str] = None,
    codigo_usuario: Optional[str] = None,
    codigo_tecnico: Optional[str] = None,
    id_taller: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_usuario)
):
    query = db.query(Bitacora)

    if modulo:
        query = query.filter(Bitacora.modulo == modulo)

    # admin_plataforma ve todo
    if usuario_actual.id_rol == 1:
        if codigo_usuario:
            query = query.filter(Bitacora.codigo_usuario == codigo_usuario)
        if codigo_tecnico:
            query = query.filter(Bitacora.codigo_tecnico == codigo_tecnico)
        if id_taller:
            query = query.filter(Bitacora.id_taller == id_taller)

    # admin_taller ve solo lo de su taller
    #hace ? para que sirve esto? respuestA: para que el admin_taller solo vea lo de su taller
    elif usuario_actual.id_rol == 2:
        taller = db.query(Taller).filter(Taller.usuario_id == usuario_actual.codigo).first()
        if not taller:
            raise HTTPException(status_code=404, detail="No se encontró taller asociado")

        query = query.filter(Bitacora.id_taller == taller.codigo)

    else:
        raise HTTPException(status_code=403, detail="No autorizado")

    registros = query.order_by(Bitacora.fecha.desc()).limit(200).all()

    resultado = []
    for r in registros:
        nombre_actor = "Desconocido"
        codigo_actor = None

        if r.codigo_usuario:
            u = db.query(Usuario).filter(Usuario.codigo == r.codigo_usuario).first()
            if u:
                nombre_actor = f"{u.nombre} {u.apellido}".strip()
                codigo_actor = u.codigo
            else:
                codigo_actor = r.codigo_usuario

        elif r.codigo_tecnico:
            t = db.query(Tecnico).filter(Tecnico.codigo == r.codigo_tecnico).first()
            if t:
                nombre_actor = t.nombre
                codigo_actor = t.codigo
            else:
                codigo_actor = r.codigo_tecnico

        resultado.append({
            "id": r.id,
            "codigo_usuario": codigo_actor,
            "codigo_tecnico": r.codigo_tecnico,
            "id_taller": r.id_taller,
            "accion": r.accion,
            "modulo": r.modulo,
            "descripcion": r.descripcion,
            "ip_address": r.ip_address,
            "fecha": r.fecha,
            "nombre_usuario": nombre_actor
        })

    return resultado