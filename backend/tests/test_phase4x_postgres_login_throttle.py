"""Real PostgreSQL integration tests; CI requires these tests to execute, not skip."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
import psycopg
from psycopg import sql

from app import login_throttle
from app.config import settings
from app.models import AuthLoginLimit


@pytest.fixture(scope="module")
def runtime_sessions():
    url = os.environ.get("HI_TEST_PG_RUNTIME_URL")
    if not url:
        if os.environ.get("HI_REQUIRE_POSTGRES_AUTH_THROTTLE") == "1":
            pytest.fail("CI requires a real disposable PostgreSQL runtime URL.")
        pytest.skip("Requires the disposable PostgreSQL auth-throttle gate.")
    engine = create_engine(url, pool_size=20, max_overflow=0, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
        connection.execute(select(AuthLoginLimit.identity_hash).limit(0))
        rls = connection.exec_driver_sql(
            "SELECT relrowsecurity AND relforcerowsecurity "
            "FROM pg_class WHERE oid='public.auth_login_limits'::regclass"
        ).scalar_one()
        policy = connection.exec_driver_sql(
            "SELECT count(*) FROM pg_policies "
            "WHERE schemaname='public' AND tablename='auth_login_limits' "
            "AND policyname='auth_login_limits_runtime' "
            "AND roles @> ARRAY['horario_runtime']::name[]"
        ).scalar_one()
        assert rls is True and policy == 1
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture(autouse=True)
def production_mode(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "session_secret", "synthetic-ci-session-secret-only")


def test_postgres_counter_is_atomic_shared_and_persisted(runtime_sessions):
    email = f"parallel-{uuid.uuid4().hex}@example.invalid"
    with ThreadPoolExecutor(max_workers=16) as pool:
        def attempt(_):
            with runtime_sessions() as db:
                try:
                    login_throttle.check_login_attempt(email, db)
                    return "allowed"
                except HTTPException as error:
                    assert error.status_code == 429
                    return "limited"

        outcomes = list(pool.map(attempt, range(20)))

    assert outcomes.count("allowed") == login_throttle.MAX_ATTEMPTS
    assert outcomes.count("limited") == 20 - login_throttle.MAX_ATTEMPTS

    # A fresh engine/session observes the shared committed count, as a new
    # Autoscale instance would after a process restart.
    engine = create_engine(os.environ["HI_TEST_PG_RUNTIME_URL"], pool_pre_ping=True)
    try:
        with sessionmaker(bind=engine)() as db:
            row = db.execute(
                select(AuthLoginLimit).where(
                    AuthLoginLimit.identity_hash == login_throttle._identity_key(email)
                )
            ).scalar_one()
            assert row.attempts == 20
            assert email not in row.identity_hash
    finally:
        engine.dispose()

    with runtime_sessions() as db:
        login_throttle.clear_successful_login(email, db)


def test_expiry_and_success_reset_are_persisted(runtime_sessions):
    email = f"expiry-{uuid.uuid4().hex}@example.invalid"
    key = login_throttle._identity_key(email)
    with runtime_sessions() as db:
        login_throttle.check_login_attempt(email, db)
        db.execute(
            update(AuthLoginLimit)
            .where(AuthLoginLimit.identity_hash == key)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        db.commit()
        login_throttle.check_login_attempt(email, db)
        row = db.execute(
            select(AuthLoginLimit).where(AuthLoginLimit.identity_hash == key)
        ).scalar_one()
        assert row.attempts == 1
        assert row.expires_at > datetime.now(timezone.utc)
        login_throttle.clear_successful_login(email, db)
        assert db.execute(
            select(AuthLoginLimit.identity_hash).where(
                AuthLoginLimit.identity_hash == key
            )
        ).first() is None


def test_unavailable_postgres_fails_closed(monkeypatch):
    unreachable = create_engine(
        "postgresql+psycopg://synthetic:synthetic@127.0.0.1:1/unavailable",
        connect_args={"connect_timeout": 1},
        pool_pre_ping=True,
    )
    try:
        with sessionmaker(bind=unreachable)() as db:
            with pytest.raises(HTTPException) as error:
                login_throttle.check_login_attempt(
                    f"unavailable-{uuid.uuid4().hex}@example.invalid", db
                )
            assert error.value.status_code == 503
            assert "synthetic" not in error.value.detail
    finally:
        unreachable.dispose()


def test_postgres_backup_restore_preserves_rls_and_acl(tmp_path: Path):
    """Restore a synthetic archive into a disposable DB; never reads business rows."""
    owner_url = os.environ.get("HI_TEST_PG_OWNER_URL")
    if not owner_url:
        if os.environ.get("HI_REQUIRE_BACKUP_RESTORE_TEST") == "1":
            pytest.fail("CI requires a disposable PostgreSQL backup/restore test URL.")
        pytest.skip("Requires the disposable PostgreSQL backup/restore gate.")
    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        if os.environ.get("HI_REQUIRE_BACKUP_RESTORE_TEST") == "1":
            pytest.fail("CI requires pg_dump and pg_restore.")
        pytest.skip("PostgreSQL client tools are unavailable.")

    parsed = make_url(owner_url)
    assert parsed.host in {"localhost", "127.0.0.1", "::1"}
    assert parsed.port == 5432 and parsed.database == "horario"
    assert parsed.username == "postgres"
    assert parsed.password == "test_owner_password"
    conninfo = owner_url.replace("postgresql+psycopg://", "postgresql://", 1)
    scratch_name = "hi_restore_" + uuid.uuid4().hex[:16]
    archive = tmp_path / "synthetic.pgdump"
    pg_env = {**os.environ, "PGPASSWORD": parsed.password or ""}

    with psycopg.connect(conninfo, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch_name))
        )
    try:
        subprocess.run(
            [
                "pg_dump", "--format=custom", "--no-owner",
                "--host", parsed.host or "127.0.0.1",
                "--port", str(parsed.port),
                "--username", parsed.username or "postgres",
                "--dbname", parsed.database or "horario",
                "--file", str(archive),
            ],
            env=pg_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        subprocess.run(
            [
                "pg_restore", "--exit-on-error", "--no-owner",
                "--host", parsed.host or "127.0.0.1",
                "--port", str(parsed.port),
                "--username", parsed.username or "postgres",
                "--dbname", scratch_name,
                str(archive),
            ],
            env=pg_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        restored_url = parsed.set(database=scratch_name).render_as_string(
            hide_password=False
        ).replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(restored_url) as connection:
            values = connection.execute(
                """
                SELECT
                  (SELECT relrowsecurity AND relforcerowsecurity
                     FROM pg_class WHERE oid='public.auth_login_limits'::regclass),
                  has_table_privilege('horario_runtime','public.auth_login_limits','SELECT'),
                  has_table_privilege('horario_runtime','public.auth_login_limits','DELETE'),
                  has_table_privilege('horario_runtime','public.memberships','UPDATE'),
                  has_table_privilege('horario_runtime','public.published_grades','INSERT'),
                  NOT has_table_privilege('horario_runtime','public.published_grades','UPDATE'),
                  NOT has_table_privilege('horario_runtime','public.published_grades','DELETE')
                """
            ).fetchone()
        assert values == (True, True, True, True, True, True, True)
    finally:
        with psycopg.connect(conninfo, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_name)
                )
            )
