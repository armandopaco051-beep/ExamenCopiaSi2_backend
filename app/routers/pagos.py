from datetime import datetime
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.operaciones import (
    Asignacion,
    CobroServicio,
    ComprobantePago,
    ConceptoCobro,
    DetalleCobro,
    Incidente,
    PagoServicio,
)
from app.models.talleres import Taller, Tecnico
from app.services.auth_service import decode_token, registrar_bitacora


router = APIRouter(prefix="/pagos", tags=["Pagos y Comprobantes"])

ESTADO_MONTO_GENERADO = "MONTO_GENERADO"
ESTADO_ACEPTADO = "ACEPTADO_POR_CLIENTE"
ESTADO_PAGADO = "PAGADO"
ESTADO_COMPROBANTE = "COMPROBANTE_GENERADO"


class ConceptoCobroItem(BaseModel):
    id_concepto: int
    cantidad: Decimal = Decimal("1")
    observacion: str | None = None


class RegistrarConceptosRequest(BaseModel):
    conceptos: list[ConceptoCobroItem]
    descuento: Decimal = Decimal("0")


class RegistrarPagoRequest(BaseModel):
    metodo_pago: str
    referencia_pago: str | None = None


def decimal_to_float(valor) -> float:
    return float(valor or 0)


def obtener_payload(token: str):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido")
    return payload


def obtener_incidente_y_asignacion(db: Session, id_incidente: int):
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    asignacion = db.query(Asignacion).filter(
        Asignacion.id_incidente == id_incidente
    ).order_by(Asignacion.fecha_asignacion.desc()).first()

    if not asignacion:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    return incidente, asignacion


def validar_tecnico_asignado(db: Session, token: str, asignacion: Asignacion):
    payload = obtener_payload(token)
    if payload.get("tipo") != "tecnico" or payload.get("sub") != asignacion.id_tecnico:
        raise HTTPException(
            status_code=403,
            detail="Solo el tecnico asignado puede registrar conceptos de cobro"
        )

    tecnico = db.query(Tecnico).filter(Tecnico.codigo == payload.get("sub")).first()
    if not tecnico:
        raise HTTPException(status_code=404, detail="Tecnico no encontrado")
    return tecnico


def validar_cliente_incidente(token: str, incidente: Incidente):
    payload = obtener_payload(token)
    if payload.get("tipo") != "usuario" or payload.get("rol") != 4 or payload.get("sub") != incidente.codigo_usuario:
        raise HTTPException(
            status_code=403,
            detail="Solo el cliente del incidente puede realizar esta accion"
        )
    return payload


def validar_consulta_pago(db: Session, token: str, incidente: Incidente, asignacion: Asignacion):
    payload = obtener_payload(token)
    codigo = payload.get("sub")
    tipo = payload.get("tipo")
    rol = payload.get("rol")

    if tipo == "usuario" and rol == 4 and codigo == incidente.codigo_usuario:
        return {"tipo": "cliente", "codigo": codigo}

    if tipo == "tecnico" and codigo == asignacion.id_tecnico:
        return {"tipo": "tecnico", "codigo": codigo}

    if tipo == "usuario" and rol == 2:
        taller = db.query(Taller).filter(Taller.usuario_id == codigo).first()
        if taller and taller.codigo == asignacion.id_taller:
            return {"tipo": "admin_taller", "codigo": codigo}

    raise HTTPException(status_code=403, detail="No tienes permiso para consultar este pago")


def obtener_o_crear_cobro(db: Session, incidente: Incidente, asignacion: Asignacion):
    cobro = db.query(CobroServicio).filter(
        CobroServicio.id_incidente == incidente.codigo
    ).first()

    if cobro:
        return cobro

    cobro = CobroServicio(
        id_incidente=incidente.codigo,
        id_asignacion=asignacion.id,
        estado_pago="PENDIENTE",
        subtotal=Decimal("0"),
        descuento=Decimal("0"),
        total=Decimal("0"),
        fecha_generacion=datetime.now()
    )
    db.add(cobro)
    db.flush()
    return cobro


def serializar_concepto(concepto: ConceptoCobro):
    return {
        "id": concepto.id,
        "codigo": concepto.codigo,
        "nombre": concepto.nombre,
        "tipo": concepto.tipo,
        "descripcion": concepto.descripcion,
        "precio_unitario": decimal_to_float(concepto.precio_unitario),
        "activo": concepto.activo,
        "id_taller": concepto.id_taller
    }


def serializar_detalle(detalle: DetalleCobro):
    return {
        "id": detalle.id,
        "id_concepto": detalle.id_concepto,
        "descripcion": detalle.descripcion,
        "tipo": detalle.tipo,
        "cantidad": decimal_to_float(detalle.cantidad),
        "precio_unitario": decimal_to_float(detalle.precio_unitario),
        "subtotal": decimal_to_float(detalle.subtotal),
        "observacion": detalle.observacion
    }


def serializar_cobro(db: Session, cobro: CobroServicio):
    detalles = db.query(DetalleCobro).filter(
        DetalleCobro.id_cobro == cobro.id
    ).order_by(DetalleCobro.id.asc()).all()

    return {
        "id_cobro": cobro.id,
        "id_incidente": cobro.id_incidente,
        "id_asignacion": cobro.id_asignacion,
        "estado_pago": cobro.estado_pago,
        "subtotal": decimal_to_float(cobro.subtotal),
        "descuento": decimal_to_float(cobro.descuento),
        "total": decimal_to_float(cobro.total),
        "fecha_generacion": cobro.fecha_generacion,
        "fecha_aceptacion": cobro.fecha_aceptacion,
        "fecha_pago": cobro.fecha_pago,
        "fecha_comprobante": cobro.fecha_comprobante,
        "conceptos": [serializar_detalle(detalle) for detalle in detalles]
    }


def generar_numero_comprobante(cobro: CobroServicio) -> str:
    return f"COMP-{datetime.now().strftime('%Y%m%d')}-{cobro.id:06d}"


def generar_comprobante(db: Session, cobro: CobroServicio):
    comprobante = db.query(ComprobantePago).filter(
        ComprobantePago.id_cobro == cobro.id
    ).first()
    if comprobante:
        return comprobante

    resumen = serializar_cobro(db, cobro)
    comprobante = ComprobantePago(
        id_cobro=cobro.id,
        numero_comprobante=generar_numero_comprobante(cobro),
        fecha_emision=datetime.now(),
        total=cobro.total,
        contenido_json=json.dumps(resumen, default=str)
    )
    db.add(comprobante)

    cobro.estado_pago = ESTADO_COMPROBANTE
    cobro.fecha_comprobante = comprobante.fecha_emision
    db.flush()
    return comprobante


def serializar_comprobante(comprobante: ComprobantePago):
    return {
        "id_comprobante": comprobante.id,
        "id_cobro": comprobante.id_cobro,
        "numero_comprobante": comprobante.numero_comprobante,
        "fecha_emision": comprobante.fecha_emision,
        "total": decimal_to_float(comprobante.total),
        "detalle": json.loads(comprobante.contenido_json)
    }


@router.get("/conceptos-cobro")
def listar_conceptos_cobro(db: Session = Depends(get_db)):
    conceptos = db.query(ConceptoCobro).filter(
        ConceptoCobro.activo == True
    ).order_by(ConceptoCobro.id.asc()).all()
    return [serializar_concepto(concepto) for concepto in conceptos]


@router.post("/incidentes/{id_incidente}/conceptos-cobro")
def registrar_conceptos_cobro(
    id_incidente: int,
    datos: RegistrarConceptosRequest,
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    if not datos.conceptos:
        raise HTTPException(status_code=400, detail="Debe registrar al menos un concepto")

    incidente, asignacion = obtener_incidente_y_asignacion(db, id_incidente)
    tecnico = validar_tecnico_asignado(db, token, asignacion)

    cobro = obtener_o_crear_cobro(db, incidente, asignacion)
    if cobro.estado_pago in [ESTADO_PAGADO, ESTADO_COMPROBANTE]:
        raise HTTPException(status_code=400, detail="El pago ya fue registrado")

    db.query(DetalleCobro).filter(DetalleCobro.id_cobro == cobro.id).delete()

    subtotal = Decimal("0")
    for item in datos.conceptos:
        if item.cantidad <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")

        concepto = db.query(ConceptoCobro).filter(
            ConceptoCobro.id == item.id_concepto,
            ConceptoCobro.activo == True
        ).first()
        if not concepto:
            raise HTTPException(status_code=404, detail=f"Concepto {item.id_concepto} no encontrado")

        detalle_subtotal = Decimal(concepto.precio_unitario) * item.cantidad
        subtotal += detalle_subtotal

        db.add(DetalleCobro(
            id_cobro=cobro.id,
            id_concepto=concepto.id,
            descripcion=concepto.nombre,
            tipo=concepto.tipo,
            cantidad=item.cantidad,
            precio_unitario=concepto.precio_unitario,
            subtotal=detalle_subtotal,
            observacion=item.observacion
        ))

    descuento = datos.descuento or Decimal("0")
    if descuento < 0:
        raise HTTPException(status_code=400, detail="El descuento no puede ser negativo")

    total = subtotal - descuento
    if total < 0:
        total = Decimal("0")

    cobro.subtotal = subtotal
    cobro.descuento = descuento
    cobro.total = total
    cobro.estado_pago = ESTADO_MONTO_GENERADO
    cobro.fecha_generacion = datetime.now()

    registrar_bitacora(
        db=db,
        codigo_usuario=None,
        codigo_tecnico=tecnico.codigo,
        id_taller=asignacion.id_taller,
        accion="GENERAR_MONTO_COBRO",
        modulo="PAGOS",
        descripcion=f"El tecnico {tecnico.codigo} registro conceptos de cobro para incidente {id_incidente}",
        ip_address=request.client.host if request.client else None
    )

    db.commit()
    db.refresh(cobro)
    return serializar_cobro(db, cobro)


@router.get("/incidentes/{id_incidente}/resumen")
def obtener_resumen_pago(
    id_incidente: int,
    token: str,
    db: Session = Depends(get_db)
):
    incidente, asignacion = obtener_incidente_y_asignacion(db, id_incidente)
    validar_consulta_pago(db, token, incidente, asignacion)

    cobro = db.query(CobroServicio).filter(
        CobroServicio.id_incidente == id_incidente
    ).first()
    if not cobro:
        raise HTTPException(status_code=404, detail="Aun no se genero monto de cobro")

    return serializar_cobro(db, cobro)


@router.put("/incidentes/{id_incidente}/aceptar")
def aceptar_monto_cliente(
    id_incidente: int,
    token: str,
    db: Session = Depends(get_db)
):
    incidente, _ = obtener_incidente_y_asignacion(db, id_incidente)
    validar_cliente_incidente(token, incidente)

    cobro = db.query(CobroServicio).filter(
        CobroServicio.id_incidente == id_incidente
    ).first()
    if not cobro:
        raise HTTPException(status_code=404, detail="Aun no se genero monto de cobro")

    if cobro.estado_pago != ESTADO_MONTO_GENERADO:
        raise HTTPException(status_code=400, detail="El monto no esta disponible para aceptacion")

    cobro.estado_pago = ESTADO_ACEPTADO
    cobro.fecha_aceptacion = datetime.now()
    db.commit()
    db.refresh(cobro)
    return serializar_cobro(db, cobro)


@router.post("/incidentes/{id_incidente}/pagar")
def registrar_pago_cliente(
    id_incidente: int,
    datos: RegistrarPagoRequest,
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    incidente, asignacion = obtener_incidente_y_asignacion(db, id_incidente)
    validar_cliente_incidente(token, incidente)

    cobro = db.query(CobroServicio).filter(
        CobroServicio.id_incidente == id_incidente
    ).first()
    if not cobro:
        raise HTTPException(status_code=404, detail="Aun no se genero monto de cobro")

    if cobro.estado_pago not in [ESTADO_ACEPTADO, ESTADO_MONTO_GENERADO]:
        raise HTTPException(status_code=400, detail="El pago no esta disponible")

    pago = db.query(PagoServicio).filter(PagoServicio.id_cobro == cobro.id).first()
    if pago:
        raise HTTPException(status_code=400, detail="El pago ya fue registrado")

    ahora = datetime.now()
    pago = PagoServicio(
        id_cobro=cobro.id,
        metodo_pago=datos.metodo_pago,
        referencia_pago=datos.referencia_pago,
        monto_pagado=cobro.total,
        estado_pago=ESTADO_PAGADO,
        fecha_pago=ahora
    )
    db.add(pago)

    cobro.estado_pago = ESTADO_PAGADO
    cobro.fecha_pago = ahora

    registrar_bitacora(
        db=db,
        codigo_usuario=incidente.codigo_usuario,
        codigo_tecnico=None,
        id_taller=asignacion.id_taller,
        accion="REGISTRAR_PAGO",
        modulo="PAGOS",
        descripcion=f"Cliente registro pago del incidente {id_incidente}",
        ip_address=request.client.host if request.client else None
    )

    comprobante = generar_comprobante(db, cobro)
    db.commit()
    db.refresh(pago)
    db.refresh(comprobante)

    return {
        "mensaje": "Pago registrado y comprobante generado",
        "pago": {
            "id_pago": pago.id,
            "metodo_pago": pago.metodo_pago,
            "referencia_pago": pago.referencia_pago,
            "monto_pagado": decimal_to_float(pago.monto_pagado),
            "estado_pago": pago.estado_pago,
            "fecha_pago": pago.fecha_pago
        },
        "comprobante": serializar_comprobante(comprobante)
    }


@router.get("/incidentes/{id_incidente}/comprobante")
def obtener_comprobante_pago(
    id_incidente: int,
    token: str,
    db: Session = Depends(get_db)
):
    incidente, asignacion = obtener_incidente_y_asignacion(db, id_incidente)
    validar_consulta_pago(db, token, incidente, asignacion)

    cobro = db.query(CobroServicio).filter(
        CobroServicio.id_incidente == id_incidente
    ).first()
    if not cobro:
        raise HTTPException(status_code=404, detail="No existe cobro para este incidente")

    comprobante = db.query(ComprobantePago).filter(
        ComprobantePago.id_cobro == cobro.id
    ).first()
    if not comprobante:
        raise HTTPException(status_code=404, detail="Aun no se genero comprobante")

    return serializar_comprobante(comprobante)
