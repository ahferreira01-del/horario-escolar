import argparse
import sys
from sqlalchemy import text, select
from .database import engine, Base, SessionLocal, bind_context
from .models import User, Tenant, Role
from .security import hash_password, ROLE_PERMISSIONS


RLS_TABLES = ["schools", "roles", "memberships", "invitations", "teachers", "teacher_schools", "availabilities", "availability_requests", "audit_logs", "academic_years", "subjects", "school_classes", "class_periods", "teaching_assignments", "teacher_limits", "teacher_weekly_limits", "school_resources", "resource_availabilities", "grade_proposals", "school_travel_times", "published_grades", "published_lessons", "published_classes"]


def init_db():
    if engine.dialect.name == "postgresql":
        raise SystemExit("init-db desativado no PostgreSQL: use 'alembic upgrade head' como OWNER. "
                         "Nunca altere tabelas automaticamente no startup da API.")
    Base.metadata.create_all(engine)

    print("Development SQLite schema initialized (NO RLS); production requires Alembic and PostgreSQL")


def bootstrap_platform(email, name, password):
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email.lower())):
            raise SystemExit("Email already exists; refusing to overwrite account")
        db.add(User(email=email.lower(), name=name, password_hash=hash_password(password), is_platform_admin=True))
        db.commit()
    print(f"Platform admin created: {email.lower()}")


def sync_default_role_permissions():
    """Add new planning privileges only to unchanged system roles, never custom roles.

    Requires explicit admin execution and must not silently extend manually edited grants.
    """
    updated=0
    with SessionLocal() as db:
        ids=[row[0] for row in db.execute(select(Tenant.id)).all()]
        for tid in ids:
            bind_context(db, "", tid)
            rows=db.scalars(select(Role).where(Role.tenant_id==tid,Role.is_system.is_(True))).all()
            for role in rows:
                new=set(ROLE_PERMISSIONS.get(role.code,[]))
                if not new:continue
                # Safe additive migration limited to named planning and proposal privileges.
                delta=new.intersection({"planning.read","planning.write","planning.preview", "grades.read", "grades.create", "grades.submit", "grades.approve", "grades.approve_partial"})-set(role.permissions)
                if delta:
                    role.permissions=sorted(set(role.permissions)|delta);updated+=1
            db.commit()
    print(f"Updated {updated} standard role(s) with Fase 2 planning permissions. Custom roles unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("init-db")
    commands.add_parser("sync-default-planning-permissions")
    b = commands.add_parser("bootstrap-platform")
    b.add_argument("--email", required=True)
    b.add_argument("--name", required=True)
    secret_source = b.add_mutually_exclusive_group(required=True)
    secret_source.add_argument("--password", help="Somente desenvolvimento: aparece na lista de processos.")
    secret_source.add_argument("--password-stdin", action="store_true",
                               help="Ler senha em linha única via stdin sem expor argv.")
    args = parser.parse_args()
    if args.cmd == "init-db": init_db()
    elif args.cmd == "sync-default-planning-permissions": sync_default_role_permissions()
    else:
        password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else args.password
        if not password:
            parser.error("Senha administrativa vazia.")
        bootstrap_platform(args.email, args.name, password)
