"""Configuração fail-closed do backend; implantação pública exige HTTPS e RLS."""
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


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


def validate_production_configuration(cfg: Settings) -> None:
    """Bloqueia inicialização insegura; não altera banco ou credenciais."""
    if cfg.environment != "production":
        return
    try:
        url = make_url(cfg.database_url)
    except Exception as exc:
        raise RuntimeError("DATABASE_URL de produção inválida.") from exc
    if (url.get_backend_name() != "postgresql"
            or not url.username or not url.password or not url.database):
        raise RuntimeError("Produção exige PostgreSQL com credenciais de runtime.")
    if url.username.lower() in {"postgres", "horario_owner", "root"}:
        raise RuntimeError("Não usar conta PostgreSQL owner/superuser no runtime.")
    secret = cfg.session_secret
    if (len(secret) < 40 or any(tag in secret.upper() for tag in
        ("DEV_ONLY", "CHANGE_ME", "SUBSTITUA", "PASSWORD", "EXAMPLE"))):
        raise RuntimeError("SESSION_SECRET de produção deve ser aleatório e forte.")
    if not cfg.cookie_secure:
        raise RuntimeError("COOKIE_SECURE deve ser true em produção.")
    public = urlsplit(cfg.public_app_url)
    if (public.scheme != "https" or not public.hostname
            or public.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
            or public.username or public.password or public.query
            or public.fragment or public.port not in (None, 443)):
        raise RuntimeError("PUBLIC_APP_URL de produção deve usar HTTPS público.")
    if not 5 <= cfg.session_max_minutes <= 1440:
        raise RuntimeError("SESSION_MAX_MINUTES fora de limites seguros (5–1440).")
    if (not cfg.smtp_host.strip() or not cfg.smtp_from.strip()
            or not 1 <= cfg.smtp_port <= 65535
            or (cfg.smtp_user and not cfg.smtp_password)):
        raise RuntimeError("SMTP deve estar configurado para convites em produção.")


settings = Settings()
validate_production_configuration(settings)
