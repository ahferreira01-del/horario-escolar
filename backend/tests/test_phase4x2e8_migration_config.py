"""Verify migration credentials are isolated from API runtime configuration."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_URL = "postgresql+psycopg://postgres:test_owner_password@127.0.0.1:5432/horario"


def _production_env():
    env = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "HI_RUNTIME_DATABASE_URL",
        "SESSION_SECRET",
        "COOKIE_SECURE",
        "PUBLIC_APP_URL",
    ):
        env.pop(name, None)
    env["ENVIRONMENT"] = "production"
    env["HI_MIGRATION_DATABASE_URL"] = MIGRATION_URL
    return env


def test_production_alembic_uses_migration_url_without_runtime_url():
    if os.environ.get("HI_REQUIRE_TEST_POSTGRES") != "1":
        pytest.skip("Exige PostgreSQL descartável do gate de integração.")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=_production_env(),
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "HI_RUNTIME_DATABASE_URL" not in result.stdout + result.stderr


def test_api_configuration_still_rejects_missing_runtime_url():
    env = _production_env()
    env.pop("HI_MIGRATION_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "HI_RUNTIME_DATABASE_URL is required in production" in result.stderr
