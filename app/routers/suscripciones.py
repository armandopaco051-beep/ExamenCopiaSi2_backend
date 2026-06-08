import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.seguridad import Usuario
from app.models.suscripciones import (
    ComprobanteSuscripcion,
    DominioTenant,
    PagoSuscripcion,
    PlanSuscripcion,
    SuscripcionTenant,
    Tenant,
)
from app.models.talleres import Taller
from app.routers.tecnicos import get_current_usuario, get_taller_admin
from app.schemas.suscripciones import (
    CambiarEstadoSuscripcionRequest,
    CambiarPlanTenantRequest,
    CheckoutSuscripcionResponse,
    ComprobanteSuscripcionResponse,
    CrearCheckoutSuscripcionRequest,
    CuotasResponse,
    PagoSuscripcionResponse,
    PlanSuscripcionCreate,
    PlanSuscripcionResponse,
    PlanSuscripcionUpdate,
    RenovarSuscripcionRequest,
    TenantCreate,
    TenantResponse,
)
from app.services.suscripciones_service import (
    calcular_cuotas_tenant,
    obtener_dominio_principal,
    obtener_plan_estandar,
    obtener_suscripcion_actual,
    obtener_tenant_por_dominio,
    obtener_tenant_por_taller,
)
from app.services.stripe_service import construir_evento_webhook, crear_checkout_session_suscripcion, obtener_stripe


router = APIRouter(prefix="/suscripciones", tags=["Suscripciones y Tenants"])


# Valida que el usuario sea administrador de la plataforma
# Caso de uso: Control de acceso para gestión de suscripciones
def validar_admin(usuario: Usuario):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede gestionar suscripciones")


# Serializa un plan de suscripción a formato JSON
# Caso de uso: Normalización de datos de planes
def serializar_plan(plan: PlanSuscripcion | None):
    if not plan:
        return None

    return {
        "id": plan.id,
        "nombre": plan.nombre,
        "duracion_dias": plan.duracion_dias,
        "precio": plan.precio,
        "dominio_incluido": plan.dominio_incluido,
        "dominio_personalizado": plan.dominio_personalizado,
        "estado": plan.estado,
        "limite_talleres": plan.limite_talleres,
        "limite_tecnicos": plan.limite_tecnicos,
        "limite_usuarios": plan.limite_usuarios,
        "limite_incidentes_mensuales": plan.limite_incidentes_mensuales,
        "limite_notificaciones_push": plan.limite_notificaciones_push,
        "limite_almacenamiento_gb": plan.limite_almacenamiento_gb,
        "stripe_product_id": plan.stripe_product_id,
        "stripe_price_id": plan.stripe_price_id,
    }


# Serializa un tenant con su dominio, suscripción y plan
# Caso de uso: Normalización de datos de tenants
def serializar_pago_suscripcion(pago: PagoSuscripcion):
    return {
        "id": pago.id,
        "id_tenant": pago.id_tenant,
        "id_suscripcion": pago.id_suscripcion,
        "id_plan": pago.id_plan,
        "proveedor": pago.proveedor,
        "stripe_invoice_id": pago.stripe_invoice_id,
        "stripe_payment_intent_id": pago.stripe_payment_intent_id,
        "stripe_checkout_session_id": pago.stripe_checkout_session_id,
        "stripe_subscription_id": pago.stripe_subscription_id,
        "monto": pago.monto,
        "moneda": pago.moneda,
        "estado": pago.estado,
        "periodo_inicio": pago.periodo_inicio,
        "periodo_fin": pago.periodo_fin,
        "hosted_invoice_url": pago.hosted_invoice_url,
        "invoice_pdf": pago.invoice_pdf,
        "fecha_pago": pago.fecha_pago,
    }


def serializar_comprobante_suscripcion(comprobante: ComprobanteSuscripcion):
    return {
        "id": comprobante.id,
        "id_pago": comprobante.id_pago,
        "numero_comprobante": comprobante.numero_comprobante,
        "fecha_emision": comprobante.fecha_emision,
        "total": comprobante.total,
        "moneda": comprobante.moneda,
        "detalle": json.loads(comprobante.contenido_json),
    }


def serializar_tenant(db: Session, tenant: Tenant):
    dominio = obtener_dominio_principal(db, tenant.id)
    suscripcion = obtener_suscripcion_actual(db, tenant.id)
    plan = None
    if suscripcion:
        plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()

    return {
        "id": tenant.id,
        "nombre": tenant.nombre,
        "slug": tenant.slug,
        "id_taller": tenant.id_taller,
        "estado": tenant.estado,
        "fecha_creacion": tenant.fecha_creacion,
        "dominio": dominio.dominio if dominio else None,
        "estado_dominio": dominio.estado if dominio else None,
        "id_suscripcion": suscripcion.id if suscripcion else None,
        "estado_suscripcion": suscripcion.estado if suscripcion else None,
        "fecha_inicio": suscripcion.fecha_inicio if suscripcion else None,
        "fecha_vencimiento": suscripcion.fecha_vencimiento if suscripcion else None,
        "stripe_customer_id": suscripcion.stripe_customer_id if suscripcion else None,
        "stripe_subscription_id": suscripcion.stripe_subscription_id if suscripcion else None,
        "plan": serializar_plan(plan)
    }


def obtener_tenant_autorizado(id_tenant: int, usuario: Usuario, db: Session):
    tenant = db.query(Tenant).filter(Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    if usuario.id_rol == 1:
        return tenant

    if usuario.id_rol == 2:
        taller = get_taller_admin(usuario, db)
        if taller.codigo == tenant.id_taller:
            return tenant

    raise HTTPException(status_code=403, detail="No autorizado para este tenant")


def obtener_email_admin_taller(db: Session, tenant: Tenant):
    taller = db.query(Taller).filter(Taller.codigo == tenant.id_taller).first()
    if not taller or not taller.usuario_id:
        return None
    usuario = db.query(Usuario).filter(Usuario.codigo == taller.usuario_id).first()
    return usuario.email if usuario else None


def activar_suscripcion_por_pago(
    db: Session,
    suscripcion: SuscripcionTenant,
    checkout_session_id: str | None,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
):
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    hoy = date.today()
    fecha_vencimiento = hoy + timedelta(days=plan.duracion_dias if plan else 30)

    if stripe_subscription_id:
        try:
            stripe_sdk = obtener_stripe()
            stripe_subscription = stripe_sdk.Subscription.retrieve(stripe_subscription_id)
            current_period_end = stripe_subscription.get("current_period_end")
            if current_period_end:
                fecha_vencimiento = datetime.fromtimestamp(current_period_end).date()
        except Exception:
            pass

    suscripcion.estado = "ACTIVA"
    suscripcion.fecha_inicio = hoy
    suscripcion.fecha_vencimiento = fecha_vencimiento
    suscripcion.stripe_checkout_session_id = checkout_session_id or suscripcion.stripe_checkout_session_id
    suscripcion.stripe_customer_id = stripe_customer_id or suscripcion.stripe_customer_id
    suscripcion.stripe_subscription_id = stripe_subscription_id or suscripcion.stripe_subscription_id
    suscripcion.fecha_ultimo_pago = datetime.now()

    tenant = db.query(Tenant).filter(Tenant.id == suscripcion.id_tenant).first()
    if tenant:
        tenant.estado = "ACTIVO"

    return tenant


def generar_numero_comprobante_suscripcion(pago: PagoSuscripcion):
    return f"SUB-{datetime.now().strftime('%Y%m%d')}-{pago.id:06d}"


def obtener_o_crear_comprobante_suscripcion(db: Session, pago: PagoSuscripcion):
    comprobante = db.query(ComprobanteSuscripcion).filter(
        ComprobanteSuscripcion.id_pago == pago.id
    ).first()
    if comprobante:
        return comprobante

    detalle = serializar_pago_suscripcion(pago)
    comprobante = ComprobanteSuscripcion(
        id_pago=pago.id,
        numero_comprobante=generar_numero_comprobante_suscripcion(pago),
        fecha_emision=datetime.now(),
        total=pago.monto,
        moneda=pago.moneda,
        contenido_json=json.dumps(detalle, default=str)
    )
    db.add(comprobante)
    db.flush()
    return comprobante


def registrar_pago_suscripcion_desde_invoice(
    db: Session,
    suscripcion: SuscripcionTenant,
    invoice: dict,
):
    stripe_invoice_id = invoice.get("id")
    if stripe_invoice_id:
        pago_existente = db.query(PagoSuscripcion).filter(
            PagoSuscripcion.stripe_invoice_id == stripe_invoice_id
        ).first()
        if pago_existente:
            obtener_o_crear_comprobante_suscripcion(db, pago_existente)
            return pago_existente

    period_start = invoice.get("period_start")
    period_end = invoice.get("period_end")
    amount_paid = invoice.get("amount_paid") or 0

    pago = PagoSuscripcion(
        id_tenant=suscripcion.id_tenant,
        id_suscripcion=suscripcion.id,
        id_plan=suscripcion.id_plan,
        proveedor="STRIPE",
        stripe_invoice_id=stripe_invoice_id,
        stripe_payment_intent_id=invoice.get("payment_intent"),
        stripe_checkout_session_id=suscripcion.stripe_checkout_session_id,
        stripe_subscription_id=invoice.get("subscription") or suscripcion.stripe_subscription_id,
        monto=amount_paid / 100,
        moneda=(invoice.get("currency") or settings.stripe_currency).upper(),
        estado="PAGADO",
        periodo_inicio=datetime.fromtimestamp(period_start).date() if period_start else None,
        periodo_fin=datetime.fromtimestamp(period_end).date() if period_end else None,
        hosted_invoice_url=invoice.get("hosted_invoice_url"),
        invoice_pdf=invoice.get("invoice_pdf"),
        fecha_pago=datetime.now(),
    )
    db.add(pago)
    db.flush()
    obtener_or_crear = obtener_o_crear_comprobante_suscripcion
    obtener_or_crear(db, pago)
    return pago


# Obtiene el plan de suscripción estándar del sistema
# Caso de uso: Consulta de plan estándar
@router.get("/plan-estandar")
def obtener_plan_unico(db: Session = Depends(get_db)):
    if datos.id_plan:
        plan = db.query(PlanSuscripcion).filter(
            PlanSuscripcion.id == datos.id_plan,
            PlanSuscripcion.estado == "ACTIVO"
        ).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan no encontrado o inactivo")
    else:
        plan = obtener_plan_estandar(db)
    return serializar_plan(plan)


@router.get("/planes", response_model=list[PlanSuscripcionResponse])
def listar_planes(
    incluir_inactivos: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(PlanSuscripcion)
    if not incluir_inactivos:
        query = query.filter(PlanSuscripcion.estado == "ACTIVO")
    return [serializar_plan(plan) for plan in query.order_by(PlanSuscripcion.precio.asc()).all()]


@router.post("/planes", response_model=PlanSuscripcionResponse, status_code=201)
def crear_plan(
    datos: PlanSuscripcionCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    if db.query(PlanSuscripcion).filter(PlanSuscripcion.nombre == datos.nombre.strip()).first():
        raise HTTPException(status_code=400, detail="Ya existe un plan con ese nombre")

    plan = PlanSuscripcion(**datos.model_dump())
    plan.nombre = plan.nombre.strip()
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return serializar_plan(plan)


@router.put("/planes/{id_plan}", response_model=PlanSuscripcionResponse)
def actualizar_plan(
    id_plan: int,
    datos: PlanSuscripcionUpdate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == id_plan).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"]:
        cambios["nombre"] = cambios["nombre"].strip()
        existe = db.query(PlanSuscripcion).filter(
            PlanSuscripcion.nombre == cambios["nombre"],
            PlanSuscripcion.id != id_plan
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un plan con ese nombre")

    for campo, valor in cambios.items():
        setattr(plan, campo, valor)

    db.commit()
    db.refresh(plan)
    return serializar_plan(plan)


@router.get("/planes/{id_plan}", response_model=PlanSuscripcionResponse)
def obtener_plan(
    id_plan: int,
    db: Session = Depends(get_db)
):
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == id_plan).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    return serializar_plan(plan)


# Crea un nuevo tenant con dominio y suscripción para un taller
# Caso de uso: Aprovisionamiento de tenant por administrador
@router.post("/tenants", response_model=TenantResponse, status_code=201)
def aprovisionar_tenant(
    datos: TenantCreate,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)

    slug = datos.slug.strip().lower()
    dominio = datos.dominio.strip().lower()

    taller = db.query(Taller).filter(Taller.codigo == datos.id_taller).first()
    if not taller:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    if db.query(Tenant).filter(Tenant.slug == slug).first():
        raise HTTPException(status_code=400, detail="Slug ya registrado")

    if obtener_tenant_por_taller(db, datos.id_taller):
        raise HTTPException(status_code=400, detail="El taller ya tiene tenant")

    if db.query(DominioTenant).filter(DominioTenant.dominio == dominio).first():
        raise HTTPException(status_code=400, detail="Dominio ya registrado")

    plan = obtener_plan_estandar(db)
    hoy = date.today()

    tenant = Tenant(
        nombre=datos.nombre.strip(),
        slug=slug,
        id_taller=datos.id_taller,
        estado="ACTIVO"
    )
    db.add(tenant)
    db.flush()

    db.add(DominioTenant(
        id_tenant=tenant.id,
        dominio=dominio,
        tipo=datos.tipo_dominio,
        estado="ACTIVO"
    ))

    db.add(SuscripcionTenant(
        id_tenant=tenant.id,
        id_plan=plan.id,
        fecha_inicio=hoy,
        fecha_vencimiento=hoy + timedelta(days=plan.duracion_dias),
        estado="ACTIVA"
    ))

    db.commit()
    db.refresh(tenant)
    return serializar_tenant(db, tenant)


# Lista todos los tenants del sistema
# Caso de uso: Consulta de tenants por administrador
@router.get("/tenants")
def listar_tenants(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenants = db.query(Tenant).order_by(Tenant.fecha_creacion.desc()).all()
    return [serializar_tenant(db, tenant) for tenant in tenants]


# Obtiene un tenant específico por su ID
# Caso de uso: Consulta de tenant por ID
@router.get("/tenants/{id_tenant}", response_model=TenantResponse)
def obtener_tenant(
    id_tenant: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenant = db.query(Tenant).filter(Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return serializar_tenant(db, tenant)


# Resuelve un dominio para obtener el tenant asociado
# Caso de uso: Resolución de dominio para multi-tenancy
@router.get("/resolver-dominio")
def resolver_dominio(
    dominio: str,
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_por_dominio(db, dominio)
    if not tenant:
        raise HTTPException(status_code=404, detail="Dominio no registrado")

    return serializar_tenant(db, tenant)


# Obtiene el plan y tenant del taller del usuario admin_taller
# Caso de uso: Consulta de plan propio por admin_taller
@router.get("/mi-plan", response_model=TenantResponse)
def obtener_mi_plan(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede consultar su plan")

    taller = get_taller_admin(usuario, db)
    tenant = obtener_tenant_por_taller(db, taller.codigo)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tu taller no tiene tenant aprovisionado")

    return serializar_tenant(db, tenant)


# Obtiene las cuotas de uso del tenant del taller del usuario
# Caso de uso: Consulta de cuotas de uso por admin_taller
@router.get("/mi-plan/cuotas", response_model=CuotasResponse)
def obtener_mis_cuotas(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    if usuario.id_rol != 2:
        raise HTTPException(status_code=403, detail="Solo el admin_taller puede consultar sus cuotas")

    taller = get_taller_admin(usuario, db)
    tenant = obtener_tenant_por_taller(db, taller.codigo)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tu taller no tiene tenant aprovisionado")

    return calcular_cuotas_tenant(db, tenant)


@router.put("/tenants/{id_tenant}/plan", response_model=TenantResponse)
def cambiar_plan_tenant(
    id_tenant: int,
    datos: CambiarPlanTenantRequest,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_autorizado(id_tenant, usuario, db)
    plan = db.query(PlanSuscripcion).filter(
        PlanSuscripcion.id == datos.id_plan,
        PlanSuscripcion.estado == "ACTIVO"
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado o inactivo")

    actual = obtener_suscripcion_actual(db, tenant.id)
    if actual and actual.estado == "PENDIENTE_PAGO" and actual.id_plan == plan.id:
        return serializar_tenant(db, tenant)

    hoy = date.today()
    nueva = SuscripcionTenant(
        id_tenant=tenant.id,
        id_plan=plan.id,
        fecha_inicio=hoy,
        fecha_vencimiento=hoy,
        estado="PENDIENTE_PAGO" if plan.precio > 0 or plan.stripe_price_id else "ACTIVA"
    )
    if nueva.estado == "ACTIVA":
        nueva.fecha_vencimiento = hoy + timedelta(days=plan.duracion_dias)
        tenant.estado = "ACTIVO"
    else:
        tenant.estado = "PENDIENTE_PAGO"

    db.add(nueva)
    db.commit()
    db.refresh(tenant)
    return serializar_tenant(db, tenant)


@router.post("/tenants/{id_tenant}/checkout", response_model=CheckoutSuscripcionResponse)
def crear_checkout_suscripcion(
    id_tenant: int,
    datos: CrearCheckoutSuscripcionRequest = CrearCheckoutSuscripcionRequest(),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_autorizado(id_tenant, usuario, db)
    suscripcion = obtener_suscripcion_actual(db, tenant.id)
    if not suscripcion:
        raise HTTPException(status_code=404, detail="Suscripcion no encontrada")

    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    session = crear_checkout_session_suscripcion(
        tenant_id=tenant.id,
        suscripcion_id=suscripcion.id,
        plan_nombre=plan.nombre,
        plan_precio=plan.precio,
        plan_stripe_price_id=plan.stripe_price_id,
        email_cliente=obtener_email_admin_taller(db, tenant),
        success_url=datos.success_url or settings.stripe_success_url,
        cancel_url=datos.cancel_url or settings.stripe_cancel_url,
    )

    suscripcion.estado = "PENDIENTE_PAGO"
    suscripcion.stripe_checkout_session_id = session.id
    db.commit()
    db.refresh(suscripcion)

    return {
        "checkout_session_id": session.id,
        "checkout_url": session.url,
        "id_tenant": tenant.id,
        "id_suscripcion": suscripcion.id,
        "estado_suscripcion": suscripcion.estado,
    }


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    event = await construir_evento_webhook(request)
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        id_suscripcion = metadata.get("id_suscripcion")
        if id_suscripcion:
            suscripcion = db.query(SuscripcionTenant).filter(
                SuscripcionTenant.id == int(id_suscripcion)
            ).first()
            if suscripcion:
                activar_suscripcion_por_pago(
                    db,
                    suscripcion,
                    checkout_session_id=data_object.get("id"),
                    stripe_customer_id=data_object.get("customer"),
                    stripe_subscription_id=data_object.get("subscription"),
                )
                if data_object.get("invoice"):
                    try:
                        stripe_sdk = obtener_stripe()
                        invoice = stripe_sdk.Invoice.retrieve(data_object.get("invoice"))
                        registrar_pago_suscripcion_desde_invoice(db, suscripcion, invoice)
                    except Exception:
                        pass
                db.commit()

    elif event_type == "invoice.payment_succeeded":
        stripe_subscription_id = data_object.get("subscription")
        if stripe_subscription_id:
            suscripcion = db.query(SuscripcionTenant).filter(
                SuscripcionTenant.stripe_subscription_id == stripe_subscription_id
            ).first()
            if suscripcion:
                activar_suscripcion_por_pago(
                    db,
                    suscripcion,
                    checkout_session_id=None,
                    stripe_customer_id=data_object.get("customer"),
                    stripe_subscription_id=stripe_subscription_id,
                )
                registrar_pago_suscripcion_desde_invoice(db, suscripcion, data_object)
                db.commit()

    elif event_type in ["invoice.payment_failed", "customer.subscription.deleted"]:
        stripe_subscription_id = data_object.get("subscription") or data_object.get("id")
        suscripcion = db.query(SuscripcionTenant).filter(
            SuscripcionTenant.stripe_subscription_id == stripe_subscription_id
        ).first()
        if suscripcion:
            suscripcion.estado = "SUSPENDIDA" if event_type == "invoice.payment_failed" else "CANCELADA"
            tenant = db.query(Tenant).filter(Tenant.id == suscripcion.id_tenant).first()
            if tenant:
                tenant.estado = suscripcion.estado
            db.commit()

    return {"received": True}


@router.get("/tenants/{id_tenant}/pagos", response_model=list[PagoSuscripcionResponse])
def listar_pagos_suscripcion(
    id_tenant: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_autorizado(id_tenant, usuario, db)
    pagos = db.query(PagoSuscripcion).filter(
        PagoSuscripcion.id_tenant == tenant.id
    ).order_by(PagoSuscripcion.fecha_pago.desc()).all()
    return [serializar_pago_suscripcion(pago) for pago in pagos]


@router.get("/tenants/{id_tenant}/comprobantes", response_model=list[ComprobanteSuscripcionResponse])
def listar_comprobantes_suscripcion(
    id_tenant: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_autorizado(id_tenant, usuario, db)
    comprobantes = (
        db.query(ComprobanteSuscripcion)
        .join(PagoSuscripcion, PagoSuscripcion.id == ComprobanteSuscripcion.id_pago)
        .filter(PagoSuscripcion.id_tenant == tenant.id)
        .order_by(ComprobanteSuscripcion.fecha_emision.desc())
        .all()
    )
    return [serializar_comprobante_suscripcion(comprobante) for comprobante in comprobantes]


@router.get("/comprobantes/{id_comprobante}", response_model=ComprobanteSuscripcionResponse)
def obtener_comprobante_suscripcion(
    id_comprobante: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    comprobante = db.query(ComprobanteSuscripcion).filter(
        ComprobanteSuscripcion.id == id_comprobante
    ).first()
    if not comprobante:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    pago = db.query(PagoSuscripcion).filter(PagoSuscripcion.id == comprobante.id_pago).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    obtener_tenant_autorizado(pago.id_tenant, usuario, db)
    return serializar_comprobante_suscripcion(comprobante)


# Obtiene las cuotas de uso de un tenant específico
# Caso de uso: Consulta de cuotas de uso por administrador
@router.get("/tenants/{id_tenant}/cuotas", response_model=CuotasResponse)
def obtener_cuotas_tenant(
    id_tenant: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenant = db.query(Tenant).filter(Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return calcular_cuotas_tenant(db, tenant)


# Renueva la suscripción de un tenant extendiendo su fecha de vencimiento
# Caso de uso: Renovación de suscripción por administrador
@router.put("/tenants/{id_tenant}/renovar", response_model=TenantResponse)
def renovar_suscripcion(
    id_tenant: int,
    datos: RenovarSuscripcionRequest = RenovarSuscripcionRequest(),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenant = db.query(Tenant).filter(Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    suscripcion = obtener_suscripcion_actual(db, id_tenant)
    if not suscripcion:
        raise HTTPException(status_code=404, detail="Suscripcion no encontrada")

    inicio = max(date.today(), suscripcion.fecha_vencimiento)
    suscripcion.fecha_inicio = inicio
    suscripcion.fecha_vencimiento = inicio + timedelta(days=datos.duracion_dias)
    suscripcion.estado = "ACTIVA"
    tenant.estado = "ACTIVO"

    db.commit()
    db.refresh(tenant)
    return serializar_tenant(db, tenant)


# Cambia el estado de la suscripción de un tenant (activar, suspender, cancelar)
# Caso de uso: Gestión de estado de suscripción por administrador
@router.put("/tenants/{id_tenant}/estado", response_model=TenantResponse)
def cambiar_estado_suscripcion(
    id_tenant: int,
    datos: CambiarEstadoSuscripcionRequest,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenant = db.query(Tenant).filter(Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    suscripcion = obtener_suscripcion_actual(db, id_tenant)
    if not suscripcion:
        raise HTTPException(status_code=404, detail="Suscripcion no encontrada")

    suscripcion.estado = datos.estado
    if datos.estado in ["SUSPENDIDA", "CANCELADA", "VENCIDA"]:
        tenant.estado = datos.estado
    elif datos.estado == "ACTIVA":
        tenant.estado = "ACTIVO"

    db.commit()
    db.refresh(tenant)
    return serializar_tenant(db, tenant)
