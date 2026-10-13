from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./local-dev.db"
    session_secret: str = "DEV_ONLY_CHANGE_ME_BEFORE_PRODUCTION_0000000000000000"
    environment: str = "development"
    public_app_url: str = "http://localhost:3000"
    session_max_minutes: int = 120
    cookie_secure: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


settings = Settings()
if settings.environment == "production":
    if settings.database_url.startswith("sqlite"):
        raise RuntimeError("Production requires PostgreSQL")
    if len(settings.session_secret) < 40 or "DEV_ONLY" in settings.session_secret:
        raise RuntimeError("Set a strong SESSION_SECRET for production")
    if not settings.cookie_secure:
        raise RuntimeError("COOKIE_SECURE must be true in production")
