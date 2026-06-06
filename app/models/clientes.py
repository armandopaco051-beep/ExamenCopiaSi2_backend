from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Vehiculo(Base):
    __tablename__ = "vehiculo"
    __table_args__ = {"schema": "clientes"}

    codigo = Column(Integer, primary_key=True, index=True)
    modelo = Column(String(100), nullable=False)
    marca = Column(String(100), nullable=False)
    placa = Column(String(20), nullable=False, unique=True)
    anio = Column("año", String(100), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    id_usuario = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    usuario = relationship("Usuario", back_populates="vehiculos")
