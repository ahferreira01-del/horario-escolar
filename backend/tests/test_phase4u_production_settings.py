"""Production boot gates are pure; run without actual DB/network/SMTP."""
from dataclasses import replace

import pytest

from app.config import Settings, validate_production_configuration


def cfg(**overrides):
    settings={
        "environment":"production",
        "database_url":"postgresql+psycopg://horario_runtime:secure-runtime@db:5432/horario",
        "session_secret":"secure_random_value_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "public_app_url":"https://horarios.example.org",
        "cookie_secure":True,
        "session_max_minutes":120,
        "smtp_host":"smtp.example.org",
        "smtp_port":587,
        "smtp_from":"nao-responder@example.org",
        "smtp_user":"smtp-user",
        "smtp_password":"smtp-secret",
    }
    settings.update(overrides)
    return Settings(_env_file=None,**settings)


def test_production_valid_configuration():
    assert validate_production_configuration(cfg()) is None


@pytest.mark.parametrize("bad_url", [
    "sqlite:///./local-dev.db",
    "postgresql+psycopg://postgres:secret@db:5432/horario",
    "postgresql+psycopg://horario_owner:secret@db:5432/horario",
    "postgresql+psycopg://root:secret@db:5432/horario",
    "postgresql+psycopg://horario_runtime@db:5432/horario",
    "postgresql+psycopg://horario_runtime:secret@db:5432/",
])
def test_production_rejects_database_ownership_and_missing_password(bad_url):
    with pytest.raises(RuntimeError,match="PostgreSQL|runtime"):
        validate_production_configuration(cfg(database_url=bad_url))


@pytest.mark.parametrize("bad_url",[
    "http://horarios.example.org",
    "https://localhost",
    "https://127.0.0.1",
    "https://admin:secret@horarios.example.org",
    "https://horarios.example.org:8080",
    "https://horarios.example.org/?token=abc",
])
def test_production_requires_public_https(bad_url):
    with pytest.raises(RuntimeError,match="HTTPS"):
        validate_production_configuration(cfg(public_app_url=bad_url))


@pytest.mark.parametrize("secret", [
    "short",
    "DEV_ONLY_CHANGE_ME_BEFORE_PRODUCTION_0000000000000000",
    "SUBSTITUA-POR-UMA-SENHA-FORTE-ALEATORIA-12345",
])
def test_production_rejects_default_and_placeholder_secrets(secret):
    with pytest.raises(RuntimeError,match="SESSION_SECRET"):
        validate_production_configuration(cfg(session_secret=secret))


def test_production_requires_secure_cookies():
    with pytest.raises(RuntimeError,match="COOKIE_SECURE"):
        validate_production_configuration(cfg(cookie_secure=False))


@pytest.mark.parametrize("overrides",[
    {"smtp_host":""},
    {"smtp_from":""},
    {"smtp_port":0},
    {"smtp_user":"mail-login","smtp_password":""},
])
def test_production_refuses_incomplete_smtp(overrides):
    with pytest.raises(RuntimeError,match="SMTP"):
        validate_production_configuration(cfg(user_provisioning_mode="email", **overrides))


def test_production_manual_provisioning_does_not_require_smtp():
    assert validate_production_configuration(cfg(
        user_provisioning_mode="manual", smtp_host="", smtp_from="",
        smtp_user="", smtp_password="",
    )) is None


@pytest.mark.parametrize("minutes",[0,4,1441])
def test_production_rejects_excess_session_duration(minutes):
    with pytest.raises(RuntimeError,match="SESSION_MAX_MINUTES"):
        validate_production_configuration(cfg(session_max_minutes=minutes))


def test_development_does_not_require_smtp_or_https():
    assert validate_production_configuration(Settings(
        _env_file=None,environment="development",
        database_url="sqlite:///./local-dev.db",
        public_app_url="http://localhost:3000",cookie_secure=False,
        smtp_host="",smtp_from=""
    )) is None


def test_production_does_not_require_external_redis_configuration():
    assert validate_production_configuration(cfg()) is None
    assert not hasattr(cfg(), "auth_rate_limit_redis_url")
