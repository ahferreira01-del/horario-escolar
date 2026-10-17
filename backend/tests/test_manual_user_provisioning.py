"""Manual account provisioning and its authentication boundaries.

SQLite here exercises API behavior only; PostgreSQL/RLS remain covered by the
dedicated disposable-PostgreSQL integration suite and CI.
"""
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
from datetime import timedelta, timezone, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, main as main_module
from app.config import settings
from app.database import Base
from app.main import app
from app.models import AuditLog, Membership, Role, User
from app.security import hash_password, verify_password


@pytest.fixture
def manual_context(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "user_provisioning_mode", "manual")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from", "")

    def unexpected_email(*_args, **_kwargs):
        pytest.fail("manual provisioning attempted to send email")

    monkeypatch.setattr(main_module, "send_invitation", unexpected_email)
    with session_factory() as db:
        db.add(User(
            email="root@example.com", name="Root",
            password_hash=hash_password("Senha-muito-forte-123"),
            is_platform_admin=True,
        ))
        db.commit()
    client = TestClient(app)
    yield client, session_factory
    client.close()
    engine.dispose()


def sign_in(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return response, ({"X-CSRF-Token": response.json()["csrf"]} if response.status_code == 200 else {})


def create_manual_tenant(client, headers, name, admin_email):
    return client.post("/api/platform/tenants", headers=headers, json={
        "name": name,
        "first_admin_email": admin_email,
        "first_admin_name": "Administrador de teste",
    })


def complete_first_password_change(email, temporary_password, new_password):
    client = TestClient(app)
    login_response, headers = sign_in(client, email, temporary_password)
    assert login_response.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    old_session = client.cookies.get("hi_session")
    changed = client.post("/api/auth/change-password", headers=headers, json={
        "new_password": new_password, "confirm_password": new_password,
    })
    assert changed.status_code == 200
    assert client.cookies.get("hi_session") != old_session
    assert client.get("/api/auth/me").json()["must_change_password"] is False
    return client, {"X-CSRF-Token": changed.json()["csrf"]}


def create_school(client, tenant_id, headers, name):
    response = client.post(
        f"/api/tenants/{tenant_id}/schools",
        headers=headers,
        json={"name": name, "timezone": "America/Sao_Paulo"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_user(client, tenant_id, headers, school_id, email, role_code="teacher"):
    roles_response = client.get(f"/api/tenants/{tenant_id}/roles", headers=headers)
    assert roles_response.status_code == 200
    role_id = next(role["id"] for role in roles_response.json() if role["code"] == role_code)
    return client.post(f"/api/tenants/{tenant_id}/users", headers=headers, json={
        "name": email.split("@")[0],
        "email": email,
        "role_id": role_id,
        "school_id": school_id,
        "is_active": True,
    })


def test_manual_tenant_creation_and_existing_account_link_do_not_send_or_reset(
    manual_context,
):
    client, session_factory = manual_context
    root_login, root_headers = sign_in(client, "root@example.com", "Senha-muito-forte-123")
    assert root_login.status_code == 200
    first = create_manual_tenant(
        client, root_headers, "Organização Manual 1", "first-admin@example.org",
    )
    assert first.status_code == 201
    first_admin = first.json()["first_admin"]
    assert first_admin["created_account"] is True
    assert first_admin["temporary_password"]
    assert "admin_invitation_sent" not in first.json()
    assert "dev_invitation_url" not in first.json()
    with session_factory() as db:
        account = db.scalar(select(User).where(User.email == "first-admin@example.org"))
        saved_hash = account.password_hash
        assert account.must_change_password is True
        assert verify_password(first_admin["temporary_password"], saved_hash)

    second = create_manual_tenant(
        client, root_headers, "Organização Manual 2", "first-admin@example.org",
    )
    assert second.status_code == 201
    linked = second.json()["first_admin"]
    assert linked["created_account"] is False
    assert linked["temporary_password"] is None
    with session_factory() as db:
        account = db.scalar(select(User).where(User.email == "first-admin@example.org"))
        assert account.password_hash == saved_hash
        assert account.must_change_password is True
        assert account.session_version == 0
        audit_rows = db.scalars(select(AuditLog)).all()
        assert all(first_admin["temporary_password"] not in repr(row.details) for row in audit_rows)


def test_production_app_configuration_imports_without_smtp(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
        "HI_SMTP_HOST", "HI_SMTP_PORT", "HI_SMTP_USER", "HI_SMTP_PASSWORD",
        "HI_SMTP_FROM", "DATABASE_URL", "HI_MIGRATION_DATABASE_URL",
    ):
        env.pop(key, None)
    env.update({
        "PYTHONPATH": os.pathsep.join(
            path for path in (str(backend_dir), env.get("PYTHONPATH", "")) if path
        ),
        "ENVIRONMENT": "production",
        "HI_RUNTIME_DATABASE_URL": (
            "postgresql+psycopg://hi_runtime:synthetic-test-only@127.0.0.1:1/isolated"
        ),
        "SESSION_SECRET": "synthetic-test-only-session-secret-0123456789-abcdef",
        "COOKIE_SECURE": "true",
        "PUBLIC_APP_URL": "https://horario.example.test",
        "USER_PROVISIONING_MODE": "manual",
    })
    result = subprocess.run(
        [sys.executable, "-c", "import app.main; print('PRODUCTION_CONFIG_IMPORT_PASS')"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "PRODUCTION_CONFIG_IMPORT_PASS" in result.stdout


def test_user_temp_password_change_reset_deactivation_and_scope(manual_context):
    platform_client, session_factory = manual_context
    root_login, root_headers = sign_in(
        platform_client, "root@example.com", "Senha-muito-forte-123",
    )
    assert root_login.status_code == 200
    first_org = create_manual_tenant(
        platform_client, root_headers, "Organização de origem", "org-admin@example.org",
    ).json()
    tenant_a = first_org["id"]
    org_admin_client, org_admin_headers = complete_first_password_change(
        "org-admin@example.org", first_org["first_admin"]["temporary_password"],
        "Senha-Admin-Origem-987",
    )
    school_a = create_school(org_admin_client, tenant_a, org_admin_headers, "Unidade A")

    created = create_user(
        org_admin_client, tenant_a, org_admin_headers, school_a,
        "professor-compartilhado@example.org",
    )
    assert created.status_code == 201
    provision = created.json()
    temp_password = provision["temporary_password"]
    assert provision["created_account"] is True
    with session_factory() as db:
        temporary_account = db.scalar(select(User).where(
            User.email == "professor-compartilhado@example.org",
        ))
        temporary_account.temporary_password_expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        db.commit()
    expired_client = TestClient(app)
    assert expired_client.post("/api/auth/login", json={
        "email":"professor-compartilhado@example.org", "password":temp_password,
    }).status_code == 401
    with session_factory() as db:
        temporary_account = db.scalar(select(User).where(
            User.email == "professor-compartilhado@example.org",
        ))
        temporary_account.temporary_password_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        )
        db.commit()
    user_client, _user_headers = complete_first_password_change(
        "professor-compartilhado@example.org", temp_password,
        "Senha-Professor-Origem-654",
    )
    assert user_client.get(f"/api/tenants/{tenant_a}/schools").status_code == 200

    # A scoped admin reset revokes all sessions for that account and returns a new,
    # one-time secret. Merely linking the same account in another tenant does not.
    with session_factory() as db:
        target = db.scalar(select(User).where(
            User.email == "professor-compartilhado@example.org",
        ))
        original_hash = target.password_hash
        original_version = target.session_version
    second_org = create_manual_tenant(
        platform_client, root_headers, "Organização de destino", "second-admin@example.org",
    ).json()
    tenant_b = second_org["id"]
    second_admin_client, second_admin_headers = complete_first_password_change(
        "second-admin@example.org", second_org["first_admin"]["temporary_password"],
        "Senha-Admin-Destino-789",
    )
    school_b = create_school(second_admin_client, tenant_b, second_admin_headers, "Unidade B")
    linked = create_user(
        second_admin_client, tenant_b, second_admin_headers, school_b,
        "professor-compartilhado@example.org",
    )
    assert linked.status_code == 201
    assert linked.json()["created_account"] is False
    assert linked.json()["temporary_password"] is None
    with session_factory() as db:
        target = db.scalar(select(User).where(
            User.email == "professor-compartilhado@example.org",
        ))
        assert target.password_hash == original_hash
        assert target.session_version == original_version
        assert target.must_change_password is False

    # The second-tenant administrator cannot inspect or mutate the first tenant.
    assert second_admin_client.get(f"/api/tenants/{tenant_a}/users").status_code == 403
    denied_cross_tenant = second_admin_client.post(
        f"/api/tenants/{tenant_a}/users", headers=second_admin_headers, json={
            "name":"Bloqueado", "email":"cross-tenant-denied@example.org",
            "role_id":"role-not-visible", "school_id":school_a, "is_active":True,
        },
    )
    assert denied_cross_tenant.status_code == 403

    # A school administrator can see and manage only its own school's memberships.
    school_c = create_school(second_admin_client, tenant_b, second_admin_headers, "Unidade C")
    assert create_user(
        second_admin_client, tenant_b, second_admin_headers, school_c,
        "unidade-c@example.org",
    ).status_code == 201
    scoped_admin = create_user(
        second_admin_client, tenant_b, second_admin_headers, school_b,
        "school-admin@example.org", role_code="school_admin",
    )
    assert scoped_admin.status_code == 201
    scoped_client, scoped_headers = complete_first_password_change(
        "school-admin@example.org", scoped_admin.json()["temporary_password"],
        "Senha-Admin-Escolar-567",
    )
    visible = scoped_client.get(f"/api/tenants/{tenant_b}/users")
    assert visible.status_code == 200
    visible_school_ids = {row["school_id"] for row in visible.json()}
    assert visible_school_ids == {school_b}
    cross_school = create_user(
        scoped_client, tenant_b, scoped_headers, school_c,
        "cross-school-denied@example.org",
    )
    assert cross_school.status_code == 403

    # Membership deactivation removes only that organization's access when the
    # account remains linked to another active organization.
    suspended = second_admin_client.patch(
        f"/api/tenants/{tenant_b}/users/{provision['user_id']}",
        headers=second_admin_headers, json={"is_active":False},
    )
    assert suspended.status_code == 200
    assert user_client.get(f"/api/tenants/{tenant_a}/schools").status_code == 200
    assert user_client.get(f"/api/tenants/{tenant_b}/schools").status_code == 403
    restored = second_admin_client.patch(
        f"/api/tenants/{tenant_b}/users/{provision['user_id']}",
        headers=second_admin_headers, json={"is_active":True},
    )
    assert restored.status_code == 200

    # A direct API request cannot bypass the forced-change wall.
    pending_client = TestClient(app)
    pending_login, pending_headers = sign_in(
        pending_client, "professor-compartilhado@example.org",
        "Senha-Professor-Origem-654",
    )
    assert pending_login.status_code == 200
    reset = second_admin_client.post(
        f"/api/tenants/{tenant_b}/users/{provision['user_id']}/reset-password",
        headers=second_admin_headers, json={},
    )
    assert reset.status_code == 200
    assert pending_client.get(f"/api/tenants/{tenant_a}/schools").status_code == 401
    reset_password = reset.json()["temporary_password"]
    pending_login, pending_headers = sign_in(
        pending_client, "professor-compartilhado@example.org", reset_password,
    )
    assert pending_login.status_code == 200
    assert pending_client.get(f"/api/tenants/{tenant_a}/schools").status_code == 423
    mismatch = pending_client.post("/api/auth/change-password", headers=pending_headers, json={
        "new_password":"Senha-Nova-Compartilhada-123",
        "confirm_password":"Senha-divergente-Compartilhada-321",
    })
    assert mismatch.status_code == 422

    deactivated = second_admin_client.patch(
        f"/api/tenants/{tenant_b}/users/{provision['user_id']}",
        headers=second_admin_headers, json={"is_active":False},
    )
    assert deactivated.status_code == 200
    deactivated_a = org_admin_client.patch(
        f"/api/tenants/{tenant_a}/users/{provision['user_id']}",
        headers=org_admin_headers, json={"is_active":False},
    )
    assert deactivated_a.status_code == 200
    no_membership_client = TestClient(app)
    assert no_membership_client.post("/api/auth/login", json={
        "email":"professor-compartilhado@example.org", "password":reset_password,
    }).status_code == 401
    reactivated_a = org_admin_client.patch(
        f"/api/tenants/{tenant_a}/users/{provision['user_id']}",
        headers=org_admin_headers, json={"is_active":True},
    )
    assert reactivated_a.status_code == 200
    assert no_membership_client.post("/api/auth/login", json={
        "email":"professor-compartilhado@example.org", "password":reset_password,
    }).status_code == 200
    inactive_school_user = second_admin_client.get(
        f"/api/tenants/{tenant_b}/users", headers=second_admin_headers,
    )
    assert inactive_school_user.status_code == 200
    with session_factory() as db:
        target = db.scalar(select(User).where(
            User.email == "professor-compartilhado@example.org",
        ))
        assert verify_password(reset_password, target.password_hash)
        assert target.must_change_password is True
        audit_rows = db.scalars(select(AuditLog)).all()
        assert all(temp_password not in repr(row.details) for row in audit_rows)
        assert all(reset_password not in repr(row.details) for row in audit_rows)
