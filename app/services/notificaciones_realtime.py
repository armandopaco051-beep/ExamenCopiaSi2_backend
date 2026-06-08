import asyncio

import anyio
from fastapi import WebSocket


class NotificacionesConnectionManager:
    def __init__(self):
        self._conexiones: dict[str, set[WebSocket]] = {}

    async def conectar(self, id_usuario: str, websocket: WebSocket):
        await websocket.accept()
        self._conexiones.setdefault(id_usuario, set()).add(websocket)

    def desconectar(self, id_usuario: str, websocket: WebSocket):
        conexiones = self._conexiones.get(id_usuario)
        if not conexiones:
            return
        conexiones.discard(websocket)
        if not conexiones:
            self._conexiones.pop(id_usuario, None)

    async def enviar_usuario(self, id_usuario: str, payload: dict):
        conexiones = list(self._conexiones.get(id_usuario, set()))
        for websocket in conexiones:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.desconectar(id_usuario, websocket)


notificaciones_manager = NotificacionesConnectionManager()


def emitir_notificacion_realtime(id_usuario: str | None, payload: dict):
    if not id_usuario:
        return

    try:
        anyio.from_thread.run(notificaciones_manager.enviar_usuario, id_usuario, payload)
        return
    except RuntimeError:
        pass

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notificaciones_manager.enviar_usuario(id_usuario, payload))
    except RuntimeError:
        return
