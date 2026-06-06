from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.operaciones import Asignacion, ChatIncidente, Incidente, MensajeChat
from app.models.seguridad import Usuario
from app.models.talleres import Taller, Tecnico
from app.services.auth_service import decode_token


router = APIRouter(prefix="/chat", tags=["Chat Duplex"])

ESTADOS_CHAT_ACTIVO = [4, 5, 9, 10, 11]


class MensajeChatRequest(BaseModel):
    mensaje: str
    tipo_mensaje: str = "texto"


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, id_incidente: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(id_incidente, []).append(websocket)

    def disconnect(self, id_incidente: int, websocket: WebSocket):
        connections = self.active_connections.get(id_incidente, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections and id_incidente in self.active_connections:
            del self.active_connections[id_incidente]

    async def broadcast(self, id_incidente: int, message: dict):
        for connection in self.active_connections.get(id_incidente, []):
            await connection.send_json(message)


manager = ConnectionManager()


def serializar_mensaje(mensaje: MensajeChat):
    return {
        "id": mensaje.id,
        "id_chat": mensaje.id_chat,
        "id_incidente": mensaje.id_incidente,
        "emisor_id": mensaje.emisor_id,
        "emisor_tipo": mensaje.emisor_tipo,
        "mensaje": mensaje.mensaje,
        "tipo_mensaje": mensaje.tipo_mensaje,
        "leido": mensaje.leido,
        "fecha_hora": mensaje.fecha_hora
    }


def obtener_asignacion_chat(db: Session, id_incidente: int):
    return db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente,
        Asignacion.id_estado_asignacion.in_(ESTADOS_CHAT_ACTIVO)
    ).order_by(Asignacion.fecha_asignacion.desc()).first()


def obtener_o_crear_chat(db: Session, id_incidente: int):
    chat = db.query(ChatIncidente).filter(
        ChatIncidente.id_incidente == id_incidente
    ).first()

    if chat:
        return chat

    chat = ChatIncidente(
        id_incidente=id_incidente,
        activo=True,
        fecha_creacion=datetime.now()
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def validar_chat_activo(db: Session, id_incidente: int):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    asignacion = obtener_asignacion_chat(db, id_incidente)
    if not asignacion or not asignacion.id_tecnico:
        raise HTTPException(
            status_code=400,
            detail="El chat esta disponible solo cuando existe tecnico asignado y servicio activo"
        )

    return incidente, asignacion


def obtener_participante_desde_token(db: Session, token: str, id_incidente: int, permitir_admin: bool = False):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido")

    codigo = payload.get("sub")
    tipo = payload.get("tipo")
    rol = payload.get("rol")

    incidente, asignacion = validar_chat_activo(db, id_incidente)

    if tipo == "usuario" and rol == 4 and incidente.codigo_usuario == codigo:
        return {
            "id": codigo,
            "tipo": "cliente",
            "puede_enviar": True,
            "asignacion": asignacion
        }

    if tipo == "tecnico" and asignacion.id_tecnico == codigo:
        return {
            "id": codigo,
            "tipo": "tecnico",
            "puede_enviar": True,
            "asignacion": asignacion
        }

    if permitir_admin and tipo == "usuario" and rol == 2:
        taller = db.query(Taller).filter(Taller.usuario_id == codigo).first()
        if taller and taller.codigo == asignacion.id_taller:
            return {
                "id": codigo,
                "tipo": "admin_taller",
                "puede_enviar": False,
                "asignacion": asignacion
            }

    raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este chat")


def guardar_mensaje(
    db: Session,
    id_incidente: int,
    emisor_id: str,
    emisor_tipo: str,
    mensaje_texto: str,
    tipo_mensaje: str
):
    if not mensaje_texto or not mensaje_texto.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacio")

    chat = obtener_o_crear_chat(db, id_incidente)
    if not chat.activo:
        raise HTTPException(status_code=400, detail="El chat esta cerrado")

    mensaje = MensajeChat(
        id_chat=chat.id,
        id_incidente=id_incidente,
        emisor_id=emisor_id,
        emisor_tipo=emisor_tipo,
        mensaje=mensaje_texto.strip(),
        tipo_mensaje=tipo_mensaje or "texto",
        leido=False,
        fecha_hora=datetime.now()
    )
    db.add(mensaje)
    db.commit()
    db.refresh(mensaje)
    return mensaje


@router.get("/incidentes/{id_incidente}/mensajes")
def listar_mensajes_chat(
    id_incidente: int,
    token: str,
    db: Session = Depends(get_db)
):
    participante = obtener_participante_desde_token(
        db,
        token,
        id_incidente,
        permitir_admin=True
    )
    chat = obtener_o_crear_chat(db, id_incidente)

    mensajes = db.query(MensajeChat).filter(
        MensajeChat.id_chat == chat.id
    ).order_by(MensajeChat.fecha_hora.asc()).all()

    return {
        "id_incidente": id_incidente,
        "id_chat": chat.id,
        "chat_activo": chat.activo,
        "participante": {
            "id": participante["id"],
            "tipo": participante["tipo"],
            "puede_enviar": participante["puede_enviar"]
        },
        "mensajes": [serializar_mensaje(mensaje) for mensaje in mensajes]
    }


@router.post("/incidentes/{id_incidente}/mensajes")
async def enviar_mensaje_chat_http(
    id_incidente: int,
    datos: MensajeChatRequest,
    token: str,
    db: Session = Depends(get_db)
):
    participante = obtener_participante_desde_token(db, token, id_incidente)
    if not participante["puede_enviar"]:
        raise HTTPException(status_code=403, detail="No puedes enviar mensajes en este chat")

    mensaje = guardar_mensaje(
        db,
        id_incidente,
        participante["id"],
        participante["tipo"],
        datos.mensaje,
        datos.tipo_mensaje
    )
    data = serializar_mensaje(mensaje)
    await manager.broadcast(id_incidente, data)
    return data


@router.websocket("/ws/incidentes/{id_incidente}")
async def websocket_chat_incidente(websocket: WebSocket, id_incidente: int):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        participante = obtener_participante_desde_token(db, token, id_incidente)
    except HTTPException:
        db.close()
        await websocket.close(code=1008)
        return

    await manager.connect(id_incidente, websocket)

    try:
        while True:
            payload = await websocket.receive_json()
            datos = MensajeChatRequest(**payload)
            mensaje = guardar_mensaje(
                db,
                id_incidente,
                participante["id"],
                participante["tipo"],
                datos.mensaje,
                datos.tipo_mensaje
            )
            await manager.broadcast(id_incidente, serializar_mensaje(mensaje))
    except WebSocketDisconnect:
        manager.disconnect(id_incidente, websocket)
    finally:
        db.close()
