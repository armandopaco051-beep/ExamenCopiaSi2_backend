from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.notificaciones import Notificacion
from app.models.operaciones import Asignacion
from app.models.suscripciones import DominioTenant, PlanSuscripcion, SuscripcionTenant, Tenant
from app.models.talleres import Taller, Tecnico


PLAN_ESTANDAR = "Plan Estandar"


def periodo_actual() -> str:
    return date.today().strftime("%Y-%m")


def obtener_plan_estandar(db: Session) -> PlanSuscripcion:
    plan = db.query(PlanSuscripcion).filter(
        PlanSuscripcion.nombre == PLAN_ESTANDAR,
        PlanSuscripcion.estado == "ACTIVO"
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan Estandar no configurado")
    return plan


def normalizar_slug(valor: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", valor.strip().lower())
    return slug.strip("-") or "taller"


def generar_slug_unico_taller(db: Session, taller: Taller) -> str:
    base = f"{normalizar_slug(taller.nombre or 'taller')}-{taller.codigo}"
    slug = base
    contador = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        contador += 1
        slug = f"{base}-{contador}"
    return slug


def aprovisionar_tenant_gratis_taller(db: Session, taller: Taller) -> Tenant:
    plan = obtener_plan_estandar(db)
    existente = obtener_tenant_por_taller(db, taller.codigo)
    if existente:
        dominio = db.query(DominioTenant).filter(DominioTenant.id_tenant == existente.id).first()
        if not dominio:
            slug = existente.slug or generar_slug_unico_taller(db, taller)
            db.add(DominioTenant(
                id_tenant=existente.id,
                dominio=f"{slug}.emergvial.com",
                tipo="SUBDOMINIO",
                estado="ACTIVO"
            ))

        suscripcion = db.query(SuscripcionTenant).filter(
            SuscripcionTenant.id_tenant == existente.id
        ).first()
        if not suscripcion:
            hoy = date.today()
            db.add(SuscripcionTenant(
                id_tenant=existente.id,
                id_plan=plan.id,
                fecha_inicio=hoy,
                fecha_vencimiento=hoy + timedelta(days=plan.duracion_dias),
                estado="ACTIVA"
            ))
            db.flush()
        return existente

    slug = generar_slug_unico_taller(db, taller)
    tenant = Tenant(
        nombre=taller.nombre or f"Taller {taller.codigo}",
        slug=slug,
        id_taller=taller.codigo,
        estado="ACTIVO" if taller.activo else "PENDIENTE"
    )
    db.add(tenant)
    db.flush()

    db.add(DominioTenant(
        id_tenant=tenant.id,
        dominio=f"{slug}.emergvial.com",
        tipo="SUBDOMINIO",
        estado="ACTIVO"
    ))

    hoy = date.today()
    db.add(SuscripcionTenant(
        id_tenant=tenant.id,
        id_plan=plan.id,
        fecha_inicio=hoy,
        fecha_vencimiento=hoy + timedelta(days=plan.duracion_dias),
        estado="ACTIVA"
    ))
    db.flush()
    return tenant


def obtener_tenant_por_taller(db: Session, id_taller: int) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.id_taller == id_taller).first()


def obtener_tenant_por_dominio(db: Session, dominio: str) -> Tenant | None:
    dominio_normalizado = dominio.strip().lower()
    return (
        db.query(Tenant)
        .join(DominioTenant, DominioTenant.id_tenant == Tenant.id)
        .filter(DominioTenant.dominio == dominio_normalizado)
        .first()
    )


def obtener_suscripcion_actual(db: Session, id_tenant: int) -> SuscripcionTenant | None:
    return db.query(SuscripcionTenant).filter(
        SuscripcionTenant.id_tenant == id_tenant
    ).order_by(SuscripcionTenant.fecha_inicio.desc()).first()


def obtener_dominio_principal(db: Session, id_tenant: int) -> DominioTenant | None:
    return db.query(DominioTenant).filter(
        DominioTenant.id_tenant == id_tenant
    ).order_by(DominioTenant.fecha_creacion.desc()).first()


def validar_suscripcion_activa_taller(db: Session, id_taller: int):
    tenant = obtener_tenant_por_taller(db, id_taller)
    if not tenant:
        raise HTTPException(status_code=403, detail="El taller no tiene tenant aprovisionado")

    suscripcion = obtener_suscripcion_actual(db, tenant.id)
    if not suscripcion:
        raise HTTPException(status_code=403, detail="El tenant no tiene suscripcion")

    if suscripcion.fecha_vencimiento < date.today():
        suscripcion.estado = "VENCIDA"
        db.flush()
        raise HTTPException(status_code=403, detail="La suscripcion del tenant esta vencida")

    if suscripcion.estado != "ACTIVA":
        raise HTTPException(status_code=403, detail=f"La suscripcion esta {suscripcion.estado}")

    return tenant, suscripcion


def validar_taller_operativo(db: Session, id_taller: int):
    tenant, suscripcion = validar_suscripcion_activa_taller(db, id_taller)
    cuotas = calcular_cuotas_tenant(db, tenant)
    if cuotas["excedidos"].get("talleres"):
        raise HTTPException(status_code=403, detail="El tenant excedio el limite de talleres de su plan")
    return tenant, suscripcion


def calcular_cuotas_tenant(db: Session, tenant: Tenant):
    suscripcion = obtener_suscripcion_actual(db, tenant.id)
    if not suscripcion:
        raise HTTPException(status_code=404, detail="Suscripcion no encontrada")

    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    periodo = periodo_actual()
    tecnicos_usados = db.query(Tecnico).filter(Tecnico.id_taller == tenant.id_taller).count()
    usuarios_usados = 1
    incidentes_usados = db.query(Asignacion).filter(
        Asignacion.id_taller == tenant.id_taller,
        func.to_char(Asignacion.fecha_asignacion, "YYYY-MM") == periodo
    ).count()

    taller = db.query(Taller).filter(Taller.codigo == tenant.id_taller).first()
    notificaciones_usadas = 0
    if taller:
        notificaciones_usadas = db.query(Notificacion).filter(
            Notificacion.id_usuario == taller.usuario_id,
            func.to_char(Notificacion.fecha_envio, "YYYY-MM") == periodo
        ).count()

    almacenamiento_usado_gb = 0.0

    limites = {
        "talleres": plan.limite_talleres,
        "tecnicos": plan.limite_tecnicos,
        "usuarios": plan.limite_usuarios,
        "incidentes_mensuales": plan.limite_incidentes_mensuales,
        "notificaciones_push": plan.limite_notificaciones_push,
        "almacenamiento_gb": float(plan.limite_almacenamiento_gb),
    }
    consumo = {
        "talleres": 1,
        "tecnicos": tecnicos_usados,
        "usuarios": usuarios_usados,
        "incidentes_mensuales": incidentes_usados,
        "notificaciones_push": notificaciones_usadas,
        "almacenamiento_gb": almacenamiento_usado_gb,
    }

    excedidos = {
        clave: consumo[clave] > limites[clave]
        for clave in limites
    }

    return {
        "id_tenant": tenant.id,
        "id_taller": tenant.id_taller,
        "periodo": periodo,
        "estado_suscripcion": suscripcion.estado,
        "fecha_vencimiento": suscripcion.fecha_vencimiento,
        "limites": limites,
        "consumo": consumo,
        "excedidos": excedidos,
    }


def validar_limite_tecnicos(db: Session, id_taller: int):
    tenant, suscripcion = validar_suscripcion_activa_taller(db, id_taller)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    total = db.query(Tecnico).filter(Tecnico.id_taller == id_taller).count()
    if plan and total >= plan.limite_tecnicos:
        raise HTTPException(
            status_code=403,
            detail=f"Has alcanzado el limite de tecnicos de tu plan ({plan.limite_tecnicos})"
        )
    return tenant, suscripcion


def validar_limite_incidentes_mensuales(db: Session, id_taller: int):
    tenant, suscripcion = validar_suscripcion_activa_taller(db, id_taller)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    total = db.query(Asignacion).filter(
        Asignacion.id_taller == id_taller,
        func.to_char(Asignacion.fecha_asignacion, "YYYY-MM") == periodo_actual()
    ).count()
    if plan and total >= plan.limite_incidentes_mensuales:
        raise HTTPException(
            status_code=403,
            detail=f"Has alcanzado el limite mensual de incidentes de tu plan ({plan.limite_incidentes_mensuales})"
        )
    return tenant, suscripcion


def validar_limite_notificaciones(db: Session, id_taller: int):
    tenant, suscripcion = validar_suscripcion_activa_taller(db, id_taller)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id == suscripcion.id_plan).first()
    taller = db.query(Taller).filter(Taller.codigo == id_taller).first()
    total = 0
    if taller:
        total = db.query(Notificacion).filter(
            Notificacion.id_usuario == taller.usuario_id,
            func.to_char(Notificacion.fecha_envio, "YYYY-MM") == periodo_actual()
        ).count()
    if plan and total >= plan.limite_notificaciones_push:
        raise HTTPException(
            status_code=403,
            detail=f"Has alcanzado el limite mensual de notificaciones de tu plan ({plan.limite_notificaciones_push})"
        )
    return tenant, suscripcion
