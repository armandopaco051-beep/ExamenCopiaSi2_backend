from decimal import Decimal

from fastapi import HTTPException, Request

from app.config import settings

try:
    import stripe
except ImportError:  # pragma: no cover - depende de requirements en runtime
    stripe = None


def obtener_stripe():
    if stripe is None:
        raise HTTPException(
            status_code=500,
            detail="La dependencia stripe no esta instalada. Ejecuta pip install -r requirements.txt"
        )
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY no esta configurado")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def monto_centavos(monto: Decimal) -> int:
    return int((Decimal(monto) * 100).quantize(Decimal("1")))


def crear_checkout_session_suscripcion(
    *,
    tenant_id: int,
    suscripcion_id: int,
    plan_nombre: str,
    plan_precio: Decimal,
    plan_stripe_price_id: str | None,
    email_cliente: str | None,
    success_url: str,
    cancel_url: str,
):
    stripe_sdk = obtener_stripe()
    if not plan_stripe_price_id and plan_precio <= 0:
        raise HTTPException(
            status_code=400,
            detail="El plan gratuito no requiere pasarela de pago o debe configurar stripe_price_id"
        )

    if plan_stripe_price_id:
        line_items = [{"price": plan_stripe_price_id, "quantity": 1}]
    else:
        line_items = [{
            "price_data": {
                "currency": settings.stripe_currency.lower(),
                "product_data": {"name": plan_nombre},
                "unit_amount": monto_centavos(plan_precio),
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }]

    return stripe_sdk.checkout.Session.create(
        mode="subscription",
        customer_email=email_cliente,
        client_reference_id=str(tenant_id),
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=line_items,
        metadata={
            "id_tenant": str(tenant_id),
            "id_suscripcion": str(suscripcion_id),
        },
        subscription_data={
            "metadata": {
                "id_tenant": str(tenant_id),
                "id_suscripcion": str(suscripcion_id),
            }
        },
    )


async def construir_evento_webhook(request: Request):
    stripe_sdk = obtener_stripe()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET no esta configurado")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        return stripe_sdk.Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload Stripe invalido")
    except stripe_sdk.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma Stripe invalida")
