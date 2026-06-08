from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, TIMESTAMP

from app.database import Base


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = {"schema": "notificaciones"}

    codigo = Column(Integer, primary_key=True, index=True)
    fecha_envio = Column(TIMESTAMP, nullable=False)
    mensaje = Column(Text, nullable=False)
    leido = Column(Boolean, nullable=False, default=False)
    id_usuario = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=True)
