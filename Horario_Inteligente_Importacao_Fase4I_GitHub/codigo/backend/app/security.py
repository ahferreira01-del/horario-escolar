from datetime import datetime, timedelta, timezone
import secrets, hashlib
import jwt
from argon2 import PasswordHasher
from fastapi import HTTPException, status, Request, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db, bind_context
from .models import User, Membership, Role, Tenant

ph = PasswordHasher()
ALGORITHM = "HS256"
COOKIE_NAME = "hi_session"

ROLE_PERMISSIONS = {
    "org_admin": ["schools.read", "schools.create", "schools.update", "users.invite", "roles.read", "roles.manage", "teachers.read", "teachers.create", "teachers.availability", "teachers.requests.read", "audit.read", "teachers.self", "teachers.requests.create", "planning.read", "planning.write", "planning.preview", "grades.read", "grades.create", "grades.submit", "grades.approve", "grades.approve_partial", "grades.publish", "grades.publish_partial"],
    "school_admin": ["schools.read", "users.invite", "roles.read", "teachers.read", "teachers.create", "teachers.requests.read", "teachers.self", "teachers.requests.create", "planning.read", "planning.write", "planning.preview", "grades.read", "grades.create", "grades.submit", "grades.approve", "grades.publish"],
    "coordinator": ["schools.read", "teachers.read", "teachers.create", "teachers.requests.read", "planning.read", "planning.write", "planning.preview", "grades.read", "grades.create", "grades.submit"],
    "teacher": ["schools.read", "teachers.self", "teachers.requests.create"],
    "viewer": ["schools.read"],
}
KNOWN_PERMISSIONS = set(p for ps in ROLE_PERMISSIONS.values() for p in ps)


def hash_password(raw: str) -> str:
    if len(raw) < 12 or len(raw) > 256:
        raise HTTPException(422, "A senha deve ter entre 12 e 256 caracteres.")
    return ph.hash(raw)


def verify_password(raw: str, digest: str) -> bool:
    try:
        return ph.verify(digest, raw)
    except Exception:
        return False


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_invitation_token() -> str:
    return secrets.token_urlsafe(36)


def make_session(user: User):
    now = datetime.now(timezone.utc)
    payload = {"sub": user.id, "iat": now, "exp": now + timedelta(minutes=settings.session_max_minutes), "csrf": secrets.token_urlsafe(24), "type": "session"}
    return jwt.encode(payload, settings.session_secret, algorithm=ALGORITHM), payload["csrf"]


def set_auth_cookie(response, token: str):
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_max_minutes * 60, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Entre com sua conta.")
    try:
        payload = jwt.decode(cookie, settings.session_secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "type", "csrf"]})
        if payload["type"] != "session":
            raise ValueError("invalid type")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada.")
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Conta inativa.")
    request.state.session_claims = payload
    bind_context(db, user.id)
    return user


def require_csrf(request: Request):
    claims = getattr(request.state, "session_claims", None)
    if not claims or not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), claims["csrf"]):
        raise HTTPException(403, "Token CSRF ausente ou inválido.")


def memberships_for(db: Session, user: User, tenant_id: str):
    bind_context(db, user.id, tenant_id)
    return db.execute(select(Membership, Role).join(Role, Membership.role_id == Role.id).where(Membership.user_id == user.id, Membership.tenant_id == tenant_id, Membership.is_active == True, Role.tenant_id == tenant_id)).all()


def permitted(db: Session, user: User, tenant_id: str, permission: str, school_id: str | None = None):
    memberships = memberships_for(db, user, tenant_id)
    for member, role in memberships:
        if permission not in role.permissions:
            continue
        if member.school_id is None or (school_id is not None and member.school_id == school_id):
            return True
    return False


def authorize(db: Session, user: User, tenant_id: str, permission: str, school_id: str | None = None, write: bool = False):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Organização não encontrada.")
    if tenant.status == "suspended":
        if tenant.suspension_mode == "blocked" or write:
            raise HTTPException(423, "Organização suspensa.")
    elif tenant.status != "active":
        raise HTTPException(423, "Organização não ativa.")
    if school_id is None and not write:
        allowed = any(permission in role.permissions for _membership, role in memberships_for(db, user, tenant_id))
    else:
        allowed = permitted(db, user, tenant_id, permission, school_id)
    if not allowed:
        raise HTTPException(403, "Sem permissão para esta organização ou unidade.")
    return tenant


def role_can_delegate(db, actor: User, tenant_id: str, role: Role, school_id: str | None):
    if role.tenant_id != tenant_id:
        raise HTTPException(400, "Perfil pertence a outra organização.")
    if role.code == "org_admin":
        raise HTTPException(403, "Somente a plataforma pode designar administrador da organização.")
    if "users.invite" not in role.permissions and not permitted(db, actor, tenant_id, "users.invite", school_id):
        raise HTTPException(403, "Sem permissão de convite.")
    for permission in role.permissions:
        if not permitted(db, actor, tenant_id, permission, school_id):
            raise HTTPException(403, f"Não é permitido delegar: {permission}.")
