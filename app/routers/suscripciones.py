from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.seguridad import Usuario
from app.models.suscripciones import DominioTenant, PlanSuscripcion, SuscripcionTenant, Tenant
from app.models.talleres import Taller
from app.routers.tecnicos import get_current_usuario, get_taller_admin
from app.schemas.suscripciones import (
    CambiarEstadoSuscripcionRequest,
    CuotasResponse,
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


router = APIRouter(prefix="/suscripciones", tags=["Suscripciones y Tenants"])


def validar_admin(usuario: Usuario):
    if usuario.id_rol != 1:
        raise HTTPException(status_code=403, detail="Solo el administrador puede gestionar suscripciones")


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
        "plan": serializar_plan(plan)
    }


@router.get("/plan-estandar")
def obtener_plan_unico(db: Session = Depends(get_db)):
    plan = obtener_plan_estandar(db)
    return serializar_plan(plan)


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


@router.get("/tenants")
def listar_tenants(
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db)
):
    validar_admin(usuario)
    tenants = db.query(Tenant).order_by(Tenant.fecha_creacion.desc()).all()
    return [serializar_tenant(db, tenant) for tenant in tenants]


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


@router.get("/resolver-dominio")
def resolver_dominio(
    dominio: str,
    db: Session = Depends(get_db)
):
    tenant = obtener_tenant_por_dominio(db, dominio)
    if not tenant:
        raise HTTPException(status_code=404, detail="Dominio no registrado")

    return serializar_tenant(db, tenant)


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
