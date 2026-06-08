from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, TIMESTAMP, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Incidente(Base):
    __tablename__ = "incidente"
    __table_args__ = (
        UniqueConstraint("codigo_usuario", "id_local_origen", name="uq_incidente_usuario_id_local_origen"),
        {"schema": "operaciones"},
    )

    codigo = Column(Integer, primary_key=True, index=True)
    descripcion = Column(Text, nullable=False)
    latitud = Column(Numeric(10, 7), nullable=False)
    longitud = Column(Numeric(10, 7), nullable=False)
    fecha_reporte = Column(TIMESTAMP, nullable=False)
    fecha_cierre = Column(TIMESTAMP, nullable=True)
    id_prioridad = Column(Integer, ForeignKey("catalogo.prioridad.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_categoria_problema = Column(Integer, ForeignKey("catalogo.categoria_problema.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_estado_incidente = Column(Integer, ForeignKey("catalogo.estado_incidente.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_vehiculo = Column(Integer, ForeignKey("clientes.vehiculo.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    codigo_usuario = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_local_origen = Column(String(100), nullable=True)
    origen_registro = Column(String(20), nullable=False, default="ONLINE")
    fecha_creacion_local = Column(TIMESTAMP, nullable=True)
    version_local = Column(Integer, nullable=True)
    estado_local_origen = Column(String(30), nullable=True)

    historial = relationship("HistorialEstado", back_populates="incidente")
    asignaciones = relationship("Asignacion", back_populates="incidente")
    evidencias = relationship("Evidencia", back_populates="incidente")


class ConflictoSincronizacion(Base):
    __tablename__ = "conflicto_sincronizacion"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_local_origen = Column(String(100), nullable=False)
    codigo_usuario = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_incidente_backend = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="SET NULL"), nullable=True)
    tipo_conflicto = Column(String(50), nullable=False)
    estado = Column(String(30), nullable=False, default="PENDIENTE")
    regla_arbitraje = Column(String(100), nullable=True)
    datos_locales_json = Column(Text, nullable=False)
    datos_servidor_json = Column(Text, nullable=True)
    resolucion = Column(String(50), nullable=True)
    observacion = Column(Text, nullable=True)
    resuelto_por = Column(String(100), nullable=True)
    fecha_deteccion = Column(TIMESTAMP, nullable=False)
    fecha_resolucion = Column(TIMESTAMP, nullable=True)


class HistorialEstado(Base):
    __tablename__ = "historial_estado"
    __table_args__ = {"schema": "operaciones"}

    codigo = Column(Integer, primary_key=True, index=True)
    fecha_cambio = Column(TIMESTAMP, nullable=False)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    incidente = relationship("Incidente", back_populates="historial")


class Asignacion(Base):
    __tablename__ = "asignacion"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    fecha_asignacion = Column(TIMESTAMP, nullable=False)
    fecha_aceptacion = Column(TIMESTAMP, nullable=False)
    tiempo = Column(String(50), nullable=False)
    observacion = Column(Text, nullable=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_tecnico = Column(String(100), ForeignKey("talleres.tecnico.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=True)
    id_taller = Column(Integer, ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_estado_asignacion = Column(Integer, ForeignKey("catalogo.estado_asignacion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    incidente = relationship("Incidente", back_populates="asignaciones")
    tecnico = relationship("Tecnico", back_populates="asignaciones")
    taller = relationship("Taller", back_populates="asignaciones")


class ValidacionArribo(Base):
    __tablename__ = "validacion_arribo"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_asignacion = Column(Integer, ForeignKey("operaciones.asignacion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    codigo_pin = Column(String(6), nullable=False)
    qr_token = Column(String(100), nullable=False)
    fecha_generacion = Column(TIMESTAMP, nullable=False)
    fecha_expiracion = Column(TIMESTAMP, nullable=False)
    usado = Column(Boolean, default=False, nullable=False)
    fecha_uso = Column(TIMESTAMP, nullable=True)
    intentos = Column(Integer, default=0, nullable=False)


class ChatIncidente(Base):
    __tablename__ = "chat_incidente"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(TIMESTAMP, nullable=False)
    fecha_cierre = Column(TIMESTAMP, nullable=True)


class MensajeChat(Base):
    __tablename__ = "mensaje_chat"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_chat = Column(Integer, ForeignKey("operaciones.chat_incidente.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    emisor_id = Column(String(100), nullable=False)
    emisor_tipo = Column(String(20), nullable=False)
    mensaje = Column(Text, nullable=False)
    tipo_mensaje = Column(String(20), nullable=False, default="texto")
    leido = Column(Boolean, default=False, nullable=False)
    fecha_hora = Column(TIMESTAMP, nullable=False)


class ConceptoCobro(Base):
    __tablename__ = "concepto_cobro"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), nullable=False, unique=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=False)
    descripcion = Column(Text, nullable=True)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    id_taller = Column(Integer, ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="SET NULL"), nullable=True)


class CobroServicio(Base):
    __tablename__ = "cobro_servicio"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_asignacion = Column(Integer, ForeignKey("operaciones.asignacion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    estado_pago = Column(String(30), nullable=False, default="PENDIENTE")
    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    descuento = Column(Numeric(10, 2), nullable=False, default=0)
    total = Column(Numeric(10, 2), nullable=False, default=0)
    fecha_generacion = Column(TIMESTAMP, nullable=False)
    fecha_aceptacion = Column(TIMESTAMP, nullable=True)
    fecha_pago = Column(TIMESTAMP, nullable=True)
    fecha_comprobante = Column(TIMESTAMP, nullable=True)


class DetalleCobro(Base):
    __tablename__ = "detalle_cobro"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_cobro = Column(Integer, ForeignKey("operaciones.cobro_servicio.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_concepto = Column(Integer, ForeignKey("operaciones.concepto_cobro.id", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    descripcion = Column(Text, nullable=False)
    tipo = Column(String(50), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    observacion = Column(Text, nullable=True)


class PagoServicio(Base):
    __tablename__ = "pago_servicio"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_cobro = Column(Integer, ForeignKey("operaciones.cobro_servicio.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    metodo_pago = Column(String(50), nullable=False)
    referencia_pago = Column(String(100), nullable=True)
    monto_pagado = Column(Numeric(10, 2), nullable=False)
    estado_pago = Column(String(30), nullable=False)
    fecha_pago = Column(TIMESTAMP, nullable=False)


class ComprobantePago(Base):
    __tablename__ = "comprobante_pago"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_cobro = Column(Integer, ForeignKey("operaciones.cobro_servicio.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    numero_comprobante = Column(String(50), nullable=False, unique=True)
    fecha_emision = Column(TIMESTAMP, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    contenido_json = Column(Text, nullable=False)


class EvaluacionServicio(Base):
    __tablename__ = "evaluacion_servicio"
    __table_args__ = {"schema": "operaciones"}

    id = Column(Integer, primary_key=True, index=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_asignacion = Column(Integer, ForeignKey("operaciones.asignacion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    codigo_cliente = Column(String(100), ForeignKey("seguridad.usuario.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    codigo_tecnico = Column(String(100), ForeignKey("talleres.tecnico.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_taller = Column(Integer, ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    calificacion = Column(Integer, nullable=False)
    puntualidad = Column(Integer, nullable=True)
    trato = Column(Integer, nullable=True)
    solucion = Column(Integer, nullable=True)
    precio = Column(Integer, nullable=True)
    comentario = Column(Text, nullable=True)
    fecha_evaluacion = Column(TIMESTAMP, nullable=False)


class SolicitudCotizacion(Base):
    __tablename__ = "solicitud_cotizacion"
    __table_args__ = (
        UniqueConstraint("id_incidente", "ronda", name="uq_solicitud_cotizacion_incidente_ronda"),
        {"schema": "operaciones"},
    )

    id = Column(Integer, primary_key=True, index=True)
    id_incidente = Column(Integer, ForeignKey("operaciones.incidente.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    ronda = Column(Integer, nullable=False, default=1)
    estado = Column(String(30), nullable=False, default="ABIERTA")
    radio_busqueda_km = Column(Numeric(10, 2), nullable=False)
    max_talleres = Column(Integer, nullable=False, default=3)
    tiempo_limite_minutos = Column(Integer, nullable=False, default=10)
    fecha_solicitud = Column(TIMESTAMP, nullable=False)
    fecha_vencimiento = Column(TIMESTAMP, nullable=False)
    fecha_finalizacion = Column(TIMESTAMP, nullable=True)
    id_cotizacion_aceptada = Column(
        Integer,
        ForeignKey(
            "operaciones.cotizacion_taller.id",
            onupdate="CASCADE",
            ondelete="SET NULL"
        ),
        nullable=True
    )
    observacion = Column(Text, nullable=True)


class CotizacionTaller(Base):
    __tablename__ = "cotizacion_taller"
    __table_args__ = (
        UniqueConstraint("id_solicitud", "id_taller", name="uq_cotizacion_solicitud_taller"),
        {"schema": "operaciones"},
    )

    id = Column(Integer, primary_key=True, index=True)
    id_solicitud = Column(Integer, ForeignKey("operaciones.solicitud_cotizacion.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_taller = Column(Integer, ForeignKey("talleres.taller.codigo", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)
    id_tecnico = Column(String(100), ForeignKey("talleres.tecnico.codigo", onupdate="CASCADE", ondelete="SET NULL"), nullable=True)
    estado = Column(String(30), nullable=False, default="INVITADA")
    distancia_km = Column(Numeric(10, 2), nullable=False)
    monto_estimado = Column(Numeric(10, 2), nullable=True)
    tiempo_llegada_minutos = Column(Integer, nullable=True)
    tiempo_reparacion_minutos = Column(Integer, nullable=True)
    descripcion_servicio = Column(Text, nullable=True)
    observacion = Column(Text, nullable=True)
    fecha_invitacion = Column(TIMESTAMP, nullable=False)
    fecha_respuesta = Column(TIMESTAMP, nullable=True)
    fecha_vencimiento = Column(TIMESTAMP, nullable=False)
