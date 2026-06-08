from pydantic import BaseModel

from app.schemas.incidente import IncidenteOfflineSync


class ResolverConflictoRequest(BaseModel):
    accion: str
    resuelto_por: str | None = None
    observacion: str | None = None


class SyncIncidenteRequest(IncidenteOfflineSync):
    pass
