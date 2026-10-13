"""Prod RC: validações estáticas e readiness sem redes ou dados reais."""
import importlib.util
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

from app import main, runtime_checks


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_preflight", ROOT / "ops" / "preflight_production.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def synthetic_config():
    owner="A"*48
    runtime="B"*48
    return {
        "HI_PUBLIC_HOST":"horarios.escolas-teste.org",
        "HI_POSTGRES_OWNER_PASSWORD":owner,
        "HI_POSTGRES_RUNTIME_PASSWORD":runtime,
        "HI_DB_OWNER_URL":f"postgresql+psycopg://horario_owner:{owner}@db:5432/horario",
        "HI_DB_RUNTIME_URL":f"postgresql+psycopg://horario_runtime:{runtime}@db:5432/horario",
        "HI_SESSION_SECRET":"C"*64,
        "HI_REDIS_PASSWORD":"D"*48,
        "HI_AUTH_REDIS_URL":"redis://:"+"D"*48+"@redis:6379/0",
        "HI_SMTP_HOST":"smtp.escolas-teste.org",
        "HI_SMTP_PORT":"587",
        "HI_SMTP_USER":"email-user",
        "HI_SMTP_PASSWORD":"mail-secret",
        "HI_SMTP_FROM":"convites@escolas-teste.org",
    }


def test_offline_preflight_accepts_complete_synthetic_configuration():
    assert preflight.validate_config(synthetic_config())==[]


@pytest.mark.parametrize("mutations", [
    {"HI_PUBLIC_HOST":"localhost"},
    {"HI_PUBLIC_HOST":"horarios.example.org"},
    {"HI_SESSION_SECRET":"short"},
    {"HI_SMTP_HOST":""},
    {"HI_SMTP_FROM":"invalid"},
    {"HI_SMTP_PORT":"0"},
    {"HI_DB_RUNTIME_URL":"postgresql+psycopg://postgres:xxx@db:5432/horario"},
])
def test_preflight_fail_closed(mutations):
    config=synthetic_config()
    config.update(mutations)
    assert preflight.validate_config(config)


def test_preflight_rejects_reusing_owner_password():
    config=synthetic_config()
    config["HI_POSTGRES_RUNTIME_PASSWORD"]=config["HI_POSTGRES_OWNER_PASSWORD"]
    assert preflight.validate_config(config)


def test_preflight_rejects_reused_config_lines(tmp_path):
    file=tmp_path/"config.env"
    file.write_text("HI_PUBLIC_HOST=a.org\nHI_PUBLIC_HOST=b.org\n",encoding="utf-8")
    with pytest.raises(ValueError,match="duplicada"):
        preflight.load_simple_env(file)


def test_readiness_success_when_rls_enforced(monkeypatch):
    monkeypatch.setattr(runtime_checks,"verify_database_isolation",
                        lambda:{"engine":"postgresql","rls":"enforced"})
    assert main.ready()=={"status":"ready"}


def test_readiness_returns_503_without_exposing_internal_exception(monkeypatch):
    def fail():
        raise ValueError("credential_example_secret_and_internals")
    monkeypatch.setattr(runtime_checks,"verify_database_isolation",fail)
    with pytest.raises(HTTPException) as error:
        main.ready()
    assert error.value.status_code==503
    assert "credential_example_secret" not in error.value.detail


def test_prod_readiness_rejects_no_rls(monkeypatch):
    monkeypatch.setattr(main.settings,"environment","production")
    monkeypatch.setattr(main,"check_auth_backend",lambda: None)
    monkeypatch.setattr(runtime_checks,"verify_database_isolation",
                        lambda:{"engine":"sqlite","rls":"not_available"})
    with pytest.raises(HTTPException) as error:
        main.ready()
    assert error.value.status_code==503


def test_production_readiness_rejects_redis_outage(monkeypatch):
    monkeypatch.setattr(main.settings,"environment","production")
    monkeypatch.setattr(runtime_checks,"verify_database_isolation",
                        lambda:{"engine":"postgresql","rls":"enforced"})
    def unavailable():
        raise RuntimeError("internal_auth_cache_secret")
    monkeypatch.setattr(main,"check_auth_backend",unavailable)
    with pytest.raises(HTTPException) as error:
        main.ready()
    assert error.value.status_code==503
    assert "secret" not in error.value.detail
