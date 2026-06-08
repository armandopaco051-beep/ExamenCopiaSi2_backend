from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    app_name: str = "Taller_vehicular"
    debug: bool = True
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_currency: str = "bob"
    stripe_success_url: str = "http://localhost:4200/suscripciones/success?session_id={CHECKOUT_SESSION_ID}"
    stripe_cancel_url: str = "http://localhost:4200/suscripciones/cancel"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

settings = Settings()
