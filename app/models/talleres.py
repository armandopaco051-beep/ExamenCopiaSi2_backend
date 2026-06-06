from sqlite3 import Time
from sqlite3.dbapi2 import Timestamp
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey,
    TIMESTAMP, Float, Text, func, Time
)
from sqlalchemy.orm import relationship
from app.database import Base


class Taller(Base):
    __tablename__ = "taller"
    __table_args__ = {"schema": "talleres"}

    codigo = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(20), nullable=False)
    direccion = Column(Text, nullable=False)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    radio_cobertura_km = Column(Float, nullable=False, default=10.0, server_default="10")
    activo = Column(Boolean, default=True, nullable=False)
    estado_registro = Column(String(20), nullable=False, default="pendiente")
    observacion_admin = Column(Text, nullable=True)
    fecha_solicitud = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    fecha_respuesta = Column(TIMESTAMP, nullable=True)
    horario_inicio = Column(Time, nullable=True)
    horario_fin = Column(Time, nullable=True)
    usuario_id = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    tecnicos = relationship("Tecnico", back_populates="taller")
    asignaciones = relationship("Asignacion", back_populates="taller")


class Tecnico(Base):
    __tablename__ = "tecnico"
    __table_args__ = {"schema": "talleres"}

    codigo = Column(String(100), primary_key=True, index=True)   # CI
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)     # CI también
    password = Column(String(255), nullable=False)               # hash del CI
    disponibilidad = Column(Boolean, nullable=False, default=True)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    telefono = Column(String(100), nullable=False)
    id_taller = Column(
        Integer,
        ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False
    )
    id_rol = Column(Integer, nullable=False, default=3)
    taller = relationship("Taller", back_populates="tecnicos")
    asignaciones = relationship("Asignacion", back_populates="tecnico")


    
