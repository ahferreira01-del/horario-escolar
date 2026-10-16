from datetime import datetime, timedelta, timezone
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db, bind_context
from .models import (Tenant, User, School, Role, Membership, Invitation, Teacher,
                     TeacherSchool, Availability, AvailabilityRequest, AuditLog, utcnow)
from .schemas import (Login, TenantCreate, SchoolCreate, InvitationCreate, InvitationAccept,
                      TeacherCreate, AvailabilityReplace, AvailabilityRequestCreate, RoleCreate,
                      UserProvisionCreate, UserMembershipUpdate, PasswordChange)
from .security import (current_user, require_csrf, make_session, set_auth_cookie, verify_password,
                       hash_password, dummy_password_hash, new_invitation_token,
                       new_temporary_password, token_hash, ROLE_PERMISSIONS,
                       KNOWN_PERMISSIONS, authorize, permitted, role_can_delegate)
from .emailer import send_invitation
from .login_throttle import check_login_attempt, clear_successful_login, check_auth_backend

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Em PostgreSQL, nenhuma requisição é aceita antes da checagem de RLS/role.
    from .runtime_checks import verify_database_isolation
    verify_database_isolation()
    yield


app = FastAPI(title="Horário Inteligente API — Fase 4I", version="0.4.9",
              docs_url="/api/docs" if settings.environment == "development" else None,
              lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


def logged(db, tenant_id, actor, action, model, obj_id, **details):
    db.add(AuditLog(tenant_id=tenant_id, actor_id=actor.id, action=action, object_type=model, object_id=obj_id, details=details))


def require_write(request: Request):
    require_csrf(request)


def iso(dt):
    return dt.isoformat() if dt else None


def local_minutes(v):
    h, m = map(int, v.split(":"))
    return h * 60 + m


def hhmm(v):
    return f"{v // 60:02d}:{v % 60:02d}"


def ensure_school(db, tenant_id, school_id):
    school = db.scalar(select(School).where(School.tenant_id == tenant_id, School.id == school_id, School.is_active == True))
    if not school:
        raise HTTPException(404, "Escola não encontrada neste escopo.")
    return school


def ensure_teacher(db, tenant_id, teacher_id):
    teacher = db.scalar(select(Teacher).where(Teacher.id == teacher_id, Teacher.tenant_id == tenant_id, Teacher.active == True))
    if not teacher:
        raise HTTPException(404, "Professor não encontrado neste escopo.")
    return teacher


def accessible_teacher(db, user, tenant_id, teacher_id, permission="teachers.read"):
    teacher = ensure_teacher(db, tenant_id, teacher_id)
    schools = db.scalars(select(TeacherSchool.school_id).where(TeacherSchool.tenant_id == tenant_id, TeacherSchool.teacher_id == teacher_id)).all()
    if not any(permitted(db, user, tenant_id, permission, school) for school in schools):
        raise HTTPException(403, "Sem acesso ao vínculo do professor.")
    return teacher, schools


def invite_record(db, tenant, email, role, school_id, actor, teacher_id=None):
    if school_id:
        ensure_school(db, tenant.id, school_id)
    token = new_invitation_token()
    record = Invitation(tenant_id=tenant.id, email=email.strip().lower(), role_id=role.id,
                        school_id=school_id, teacher_id=teacher_id, token_hash=token_hash(token),
                        expires_at=utcnow() + timedelta(hours=48), created_by=actor.id)
    db.add(record)
    db.flush()
    url = f"{settings.public_app_url.rstrip('/')}/convite?tenant={quote(tenant.id)}&token={quote(token)}"
    return record, token, url


def deliver_invitation(email, url):
    if settings.user_provisioning_mode.strip().lower() != "email":
        raise HTTPException(409, "Convites por e-mail estão desativados; use o cadastro administrativo.")
    if settings.environment != "development" and (not settings.smtp_host or not settings.smtp_from):
        raise HTTPException(503, "Envio de convites indisponível: SMTP não configurado.")
    try:
        sent = send_invitation(email, url)
    except Exception:
        raise HTTPException(503, "Não foi possível entregar o convite por e-mail.")
    return sent


@app.get("/api/release", include_in_schema=False)
def release_identity():
    """Identidade pública do build para auditar homologação vs implantação.

    HI_RELEASE_SHA deve ser configurado no provedor para o SHA real implantado;
    não assume que o código no GitHub corresponde ao Replit.
    """
    raw_sha = os.getenv("HI_RELEASE_SHA", "").strip().lower()
    verified_format = bool(re.fullmatch(r"[0-9a-f]{40}", raw_sha))
    return {
        "app": "horario-inteligente",
        "api_version": app.version,
        "release_sha": raw_sha if verified_format else None,
        "release_identified": verified_format,
    }


@app.get("/api/health")
def health():
    # Liveness: processo responde, mesmo que a conexão externa esteja instável.
    return {"status": "ok", "service": "horario-inteligente-api", "phase": "foundation"}


@app.get("/api/ready", include_in_schema=False)
def ready():
    """Readiness: exige conexão ao banco e contrato RLS seguro no PostgreSQL.

    Não vaza detalhes de schema, credenciais, políticas ou conexão externa.
    """
    from .runtime_checks import verify_database_isolation
    try:
        state = verify_database_isolation()
        if settings.environment == "production" and state.get("rls") != "enforced":
            raise RuntimeError("Contrato RLS não validado.")
        check_auth_backend()
    except Exception as exc:
        raise HTTPException(503, "Serviço temporariamente indisponível.") from exc
    return {"status": "ready"}


@app.post("/api/auth/login")
def login(data: Login, response: Response, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    # Limite distribuído funciona ANTES de consultar usuário ou fazer Argon2.
    check_login_attempt(normalized_email, db)
    user = db.scalar(select(User).where(User.email == normalized_email))
    password_digest = user.password_hash if user and user.is_active else dummy_password_hash()
    password_ok = verify_password(data.password, password_digest)
    if user and user.must_change_password:
        expires_at = user.temporary_password_expires_at
        if not expires_at:
            password_ok = False
        else:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= utcnow():
                password_ok = False
    if user and user.is_active and password_ok and not user.is_platform_admin:
        bind_context(db, user.id)
        has_active_membership = db.scalar(select(Membership.id).where(
            Membership.user_id == user.id, Membership.is_active == True,
        ).limit(1))
        if not has_active_membership:
            password_ok = False
    if not user or not user.is_active or not password_ok:
        raise HTTPException(401, "E-mail ou senha inválidos.")
    clear_successful_login(normalized_email, db)
    token, csrf = make_session(user)
    set_auth_cookie(response, token)
    return {"message": "Acesso autorizado.", "csrf": csrf}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db), request: Request = None):
    bind_context(db, user.id)
    members = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.is_active == True)).all()
    memberships = []
    for m in members:
        bind_context(db, user.id, m.tenant_id)
        r = db.scalar(select(Role).where(Role.id == m.role_id, Role.tenant_id == m.tenant_id))
        t = db.get(Tenant, m.tenant_id)
        s = db.scalar(select(School).where(School.id == m.school_id, School.tenant_id == m.tenant_id)) if m.school_id else None
        if r and t:
            memberships.append({"tenant_id": m.tenant_id, "tenant_name": t.name, "tenant_status": t.status,
                                "school_id": m.school_id, "school_name": s.name if s else None,
                                "role_code": r.code, "role_name": r.name, "permissions": r.permissions})
    return {"id": user.id, "name": user.name, "email": user.email,
            "is_platform_admin": user.is_platform_admin, "memberships": memberships,
            "csrf": request.state.session_claims["csrf"],
            "must_change_password": user.must_change_password,
            "temporary_password_expires_at": (
                user.temporary_password_expires_at.isoformat()
                if user.temporary_password_expires_at else None
            )}


@app.post("/api/auth/change-password")
def change_temporary_password(data: PasswordChange, request: Request, response: Response,
                              user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    if not user.must_change_password:
        raise HTTPException(409, "Esta conta não precisa concluir a troca de senha inicial.")
    if data.new_password != data.confirm_password:
        raise HTTPException(422, "As senhas não coincidem.")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.temporary_password_expires_at = None
    user.session_version += 1

    # Registra a alteração sem incluir senha ou hash no evento.
    bind_context(db, user.id)
    active_membership = db.scalar(
        select(Membership)
        .where(Membership.user_id == user.id, Membership.is_active == True)
        .order_by(Membership.tenant_id)
        .limit(1)
    )
    if active_membership:
        bind_context(db, user.id, active_membership.tenant_id)
        logged(db, active_membership.tenant_id, user, "user.password_changed",
               "user", user.id)
    db.commit()
    token, csrf = make_session(user)
    set_auth_cookie(response, token)
    return {"message": "Senha atualizada. A nova sessão foi protegida.", "csrf": csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user)):
    require_write(request)
    response.delete_cookie("hi_session", path="/")
    return {"message": "Sessão encerrada."}


@app.post("/api/auth/accept-invitation")
def accept_invitation(data: InvitationAccept, request: Request, response: Response, db: Session = Depends(get_db)):
    if len(data.token) < 30:
        raise HTTPException(400, "Convite inválido.")
    bind_context(db, "", data.tenant_id)
    record = db.scalar(select(Invitation).where(Invitation.tenant_id == data.tenant_id,
                     Invitation.token_hash == token_hash(data.token)).with_for_update())
    if not record or record.used_at:
        raise HTTPException(400, "Convite inválido ou já utilizado.")
    expiry = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    if expiry <= utcnow():
        raise HTTPException(400, "Convite expirado.")
    tenant = db.scalar(select(Tenant).where(Tenant.id == data.tenant_id).with_for_update())
    if not tenant or tenant.status != "active":
        raise HTTPException(423, "Organização indisponível.")
    user = db.scalar(select(User).where(User.email == record.email))
    if user:
        if not user.is_active:
            raise HTTPException(403, "Conta desativada.")
        # Existing accounts can only join a second organization using their existing active session.
        from .security import COOKIE_NAME
        cookie = request.cookies.get(COOKIE_NAME)
        import jwt
        authenticated = False
        if cookie:
            try:
                claims = jwt.decode(cookie, settings.session_secret, algorithms=["HS256"])
                authenticated = (
                    claims.get("sub") == user.id
                    and claims.get("type") == "session"
                    and claims.get("sv", 0) == user.session_version
                )
            except Exception:
                pass
        if not authenticated:
            raise HTTPException(409, "Esta conta já existe. Entre com ela e aceite o convite novamente.")
    else:
        if not data.password:
            raise HTTPException(422, "Defina uma senha para sua nova conta.")
        user = User(email=record.email, name=data.name.strip(), password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
    role = db.scalar(select(Role).where(Role.tenant_id == data.tenant_id, Role.id == record.role_id))
    if not role:
        raise HTTPException(409, "Perfil do convite foi removido.")
    exists = db.scalar(select(Membership).where(Membership.tenant_id == data.tenant_id, Membership.user_id == user.id,
                       Membership.school_id == record.school_id, Membership.role_id == role.id,
                       Membership.is_active == True))
    if not exists:
        is_known_user = db.scalar(select(Membership.id).where(Membership.tenant_id == data.tenant_id,
            Membership.user_id == user.id, Membership.is_active == True))
        if not is_known_user:
            active_users = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(
                Membership.tenant_id == data.tenant_id, Membership.is_active == True))
            if active_users >= tenant.max_users:
                raise HTTPException(409, "Limite de usuários ativos da organização atingido.")
        db.add(Membership(tenant_id=data.tenant_id, user_id=user.id, role_id=role.id, school_id=record.school_id))
    if record.teacher_id:
        teacher = db.scalar(select(Teacher).where(Teacher.id == record.teacher_id, Teacher.tenant_id == data.tenant_id).with_for_update())
        if not teacher or (teacher.user_id and teacher.user_id != user.id):
            raise HTTPException(409, "O cadastro do professor está vinculado a outra conta.")
        teacher.user_id = user.id
    record.used_at = utcnow()
    logged(db, data.tenant_id, user, "invitation.accepted", "membership", record.id, role=role.code)
    db.commit()
    session, csrf = make_session(user)
    set_auth_cookie(response, session)
    return {"message": "Convite aceito.", "csrf": csrf}


@app.get("/api/platform/tenants")
def platform_tenants(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_platform_admin:
        raise HTTPException(403, "Somente administração da plataforma.")
    return [{"id": t.id, "name": t.name, "status": t.status,
             "max_schools": t.max_schools, "max_teachers": t.max_teachers, "max_users": t.max_users}
            for t in db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()]


@app.post("/api/platform/tenants", status_code=201)
def create_tenant(data: TenantCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    if not user.is_platform_admin:
        raise HTTPException(403, "Somente administração da plataforma.")
    tenant = Tenant(name=data.name.strip(), status="active", max_schools=data.max_schools,
                    max_teachers=data.max_teachers, max_users=data.max_users)
    db.add(tenant)
    db.flush()
    bind_context(db, user.id, tenant.id)
    roles = {}
    for code, permissions in ROLE_PERMISSIONS.items():
        r = Role(tenant_id=tenant.id, code=code, name={"org_admin":"Administrador da organização", "school_admin":"Administrador escolar", "coordinator":"Coordenador", "teacher":"Professor", "viewer":"Consulta"}[code], permissions=permissions, is_system=True)
        db.add(r); roles[code] = r
    db.flush()
    normalized_email = data.first_admin_email.lower().strip()
    first_admin = {"email": normalized_email, "created_account": False,
                   "temporary_password": None, "temporary_password_expires_at": None}
    sent = None
    url = None
    if settings.user_provisioning_mode.strip().lower() == "email":
        inv, token, url = invite_record(db, tenant, normalized_email, roles["org_admin"], None, user)
        sent = deliver_invitation(inv.email, url)
    else:
        first_account = db.scalar(
            select(User).where(User.email == normalized_email).with_for_update()
        )
        if first_account and not first_account.is_active:
            raise HTTPException(409, "A conta do administrador está desativada.")
        if first_account:
            first_admin["email"] = first_account.email
        else:
            temporary_password = new_temporary_password()
            expires_at = utcnow() + timedelta(hours=24)
            first_account = User(
                email=normalized_email,
                name=data.first_admin_name.strip(),
                password_hash=hash_password(temporary_password),
                is_active=True,
                must_change_password=True,
                temporary_password_expires_at=expires_at,
            )
            db.add(first_account)
            db.flush()
            first_admin.update(
                created_account=True,
                temporary_password=temporary_password,
                temporary_password_expires_at=expires_at.isoformat(),
            )
        db.add(Membership(
            tenant_id=tenant.id, user_id=first_account.id,
            role_id=roles["org_admin"].id, school_id=None, is_active=True,
        ))
    logged(db, tenant.id, user, "tenant.created", "tenant", tenant.id, organization=data.name)
    db.commit()
    result = {"id": tenant.id, "name": tenant.name, "first_admin": first_admin}
    if settings.user_provisioning_mode.strip().lower() == "email":
        result["admin_invitation_sent"] = sent
    if settings.environment == "development":
        if url:
            result["dev_invitation_url"] = url
    return result


@app.get("/api/tenants/{tenant_id}/schools")
def list_schools(tenant_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "schools.read")
    bind_context(db, user.id, tenant_id)
    all_sc = db.scalars(select(School).where(School.tenant_id == tenant_id, School.is_active == True).order_by(School.name)).all()
    return [{"id": s.id, "name": s.name, "timezone": s.timezone}
            for s in all_sc if permitted(db, user, tenant_id, "schools.read", s.id)]


@app.post("/api/tenants/{tenant_id}/schools", status_code=201)
def create_school(tenant_id: str, data: SchoolCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    tenant = authorize(db, user, tenant_id, "schools.create", write=True)
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Fuso horário inválido.")
    bind_context(db, user.id, tenant_id)
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    count = db.scalar(select(func.count(School.id)).where(School.tenant_id == tenant_id, School.is_active == True))
    if count >= tenant.max_schools:
        raise HTTPException(409, "Limite de escolas da organização atingido.")
    school = School(tenant_id=tenant_id, name=data.name.strip(), timezone=data.timezone)
    db.add(school); db.flush()
    logged(db, tenant_id, user, "school.created", "school", school.id, name=school.name)
    db.commit()
    return {"id": school.id, "name": school.name, "timezone": school.timezone}


@app.get("/api/tenants/{tenant_id}/roles")
def list_roles(tenant_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "roles.read")
    bind_context(db, user.id, tenant_id)
    return [{"id": r.id, "name": r.name, "code": r.code, "permissions": r.permissions, "is_system": r.is_system}
            for r in db.scalars(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)).all()]


@app.post("/api/tenants/{tenant_id}/roles", status_code=201)
def create_role(tenant_id: str, data: RoleCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    authorize(db, user, tenant_id, "roles.manage", write=True)
    if not data.permissions or set(data.permissions) - KNOWN_PERMISSIONS:
        raise HTTPException(422, "Permissões não reconhecidas.")
    if not all(permitted(db, user, tenant_id, p) for p in data.permissions):
        raise HTTPException(403, "Não é permitido conceder permissões superiores às suas.")
    bind_context(db, user.id, tenant_id)
    if db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.code == data.code)):
        raise HTTPException(409, "Código de perfil já existente.")
    r = Role(tenant_id=tenant_id, code=data.code, name=data.name, permissions=sorted(set(data.permissions)), is_system=False)
    db.add(r); db.flush()
    logged(db, tenant_id, user, "role.created", "role", r.id, code=r.code)
    db.commit()
    return {"id": r.id, "code": r.code, "name": r.name, "permissions": r.permissions}


@app.get("/api/tenants/{tenant_id}/users")
def list_tenant_users(tenant_id: str, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "users.invite")
    bind_context(db, user.id, tenant_id)
    rows = db.execute(
        select(Membership, User, Role, School)
        .join(User, User.id == Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .outerjoin(School, School.id == Membership.school_id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(User.name, Role.name, School.name)
    ).all()
    result = []
    for membership, account, role, school in rows:
        if not permitted(db, user, tenant_id, "users.invite", membership.school_id):
            continue
        result.append({
            "user_id": account.id,
            "name": account.name,
            "email": account.email,
            "role_id": role.id,
            "role_code": role.code,
            "role_name": role.name,
            "school_id": membership.school_id,
            "school_name": school.name if school else None,
            "membership_active": membership.is_active,
            "account_active": account.is_active,
            "must_change_password": account.must_change_password,
            "temporary_password_expires_at": (
                account.temporary_password_expires_at.isoformat()
                if account.temporary_password_expires_at else None
            ),
        })
    return result


@app.post("/api/tenants/{tenant_id}/users", status_code=201)
def provision_tenant_user(tenant_id: str, data: UserProvisionCreate, request: Request,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    if not data.school_id:
        raise HTTPException(422, "Selecione uma unidade para este vínculo.")
    tenant = authorize(db, user, tenant_id, "users.invite",
                       school_id=data.school_id, write=True)
    bind_context(db, user.id, tenant_id)
    school = db.scalar(select(School).where(
        School.id == data.school_id, School.tenant_id == tenant_id,
        School.is_active == True,
    ))
    if not school:
        raise HTTPException(404, "Unidade não encontrada.")
    role = db.scalar(select(Role).where(
        Role.id == data.role_id, Role.tenant_id == tenant_id,
    ))
    if not role:
        raise HTTPException(404, "Perfil não encontrado.")
    if role.code == "org_admin":
        raise HTTPException(403, "Somente a plataforma pode designar administrador da organização.")
    role_can_delegate(db, user, tenant_id, role, data.school_id)

    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    email = str(data.email).lower().strip()
    account = db.scalar(select(User).where(User.email == email).with_for_update())
    if account and not account.is_active:
        raise HTTPException(409, "A conta existente está desativada; solicite suporte à plataforma.")
    membership = None
    if account:
        membership = db.scalar(select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == account.id,
            Membership.school_id == data.school_id, Membership.role_id == role.id,
        ).with_for_update())
        if membership and membership.is_active:
            raise HTTPException(409, "Este usuário já possui o vínculo ativo.")

    active_in_tenant = bool(account and db.scalar(select(Membership.id).where(
        Membership.tenant_id == tenant_id, Membership.user_id == account.id,
        Membership.is_active == True,
    ).limit(1)))
    if data.is_active and not active_in_tenant:
        active_users = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(
            Membership.tenant_id == tenant_id, Membership.is_active == True,
        ))
        if active_users >= tenant.max_users:
            raise HTTPException(409, "Limite de usuários ativos da organização atingido.")

    created_account = account is None
    temporary_password = None
    expires_at = None
    if created_account:
        temporary_password = new_temporary_password()
        expires_at = utcnow() + timedelta(hours=24)
        account = User(
            email=email, name=data.name.strip(),
            password_hash=hash_password(temporary_password),
            is_active=True, must_change_password=True,
            temporary_password_expires_at=expires_at,
        )
        db.add(account)
        db.flush()
    elif membership:
        membership.is_active = data.is_active
    else:
        membership = Membership(
            tenant_id=tenant_id, user_id=account.id, role_id=role.id,
            school_id=data.school_id, is_active=data.is_active,
        )
        db.add(membership)
    if created_account:
        membership = Membership(
            tenant_id=tenant_id, user_id=account.id, role_id=role.id,
            school_id=data.school_id, is_active=data.is_active,
        )
        db.add(membership)
    db.flush()
    logged(db, tenant_id, user, "user.provisioned", "membership", membership.id,
           role=role.code, school_id=data.school_id, created_account=created_account)
    db.commit()
    return {
        "user_id": account.id, "name": account.name, "email": account.email,
        "membership_active": membership.is_active, "account_active": account.is_active,
        "role_code": role.code, "role_name": role.name,
        "school_id": membership.school_id, "school_name": school.name,
        "created_account": created_account,
        "temporary_password": temporary_password,
        "temporary_password_expires_at": expires_at.isoformat() if expires_at else None,
    }


@app.patch("/api/tenants/{tenant_id}/users/{user_id}")
def update_tenant_user(tenant_id: str, user_id: str, data: UserMembershipUpdate,
                       request: Request, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    require_write(request)
    bind_context(db, user.id, tenant_id)
    membership = db.scalar(select(Membership).where(
        Membership.tenant_id == tenant_id, Membership.user_id == user_id,
    ).with_for_update())
    if not membership:
        raise HTTPException(404, "Vínculo não encontrado.")
    authorize(db, user, tenant_id, "users.invite",
              school_id=membership.school_id, write=True)
    role = db.scalar(select(Role).where(
        Role.id == membership.role_id, Role.tenant_id == tenant_id,
    ))
    if not role or role.code == "org_admin":
        raise HTTPException(403, "Este vínculo é administrado pela plataforma.")
    if data.is_active:
        role_can_delegate(db, user, tenant_id, role, membership.school_id)
        if not membership.is_active:
            tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
            active_in_tenant = db.scalar(select(Membership.id).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id,
                Membership.is_active == True,
            ).limit(1))
            if not active_in_tenant:
                active_users = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(
                    Membership.tenant_id == tenant_id, Membership.is_active == True,
                ))
                if active_users >= tenant.max_users:
                    raise HTTPException(409, "Limite de usuários ativos da organização atingido.")
    membership.is_active = data.is_active
    logged(db, tenant_id, user,
           "user.membership_activated" if data.is_active else "user.membership_deactivated",
           "membership", membership.id, role=role.code, school_id=membership.school_id)
    db.commit()
    account = db.get(User, user_id)
    school = db.get(School, membership.school_id) if membership.school_id else None
    return {
        "user_id": account.id, "name": account.name, "email": account.email,
        "role_id": role.id, "role_code": role.code, "role_name": role.name,
        "school_id": membership.school_id, "school_name": school.name if school else None,
        "membership_active": membership.is_active, "account_active": account.is_active,
        "must_change_password": account.must_change_password,
        "temporary_password_expires_at": (
            account.temporary_password_expires_at.isoformat()
            if account.temporary_password_expires_at else None
        ),
    }


@app.post("/api/tenants/{tenant_id}/users/{user_id}/reset-password")
def reset_tenant_user_password(tenant_id: str, user_id: str, request: Request,
                               user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    bind_context(db, user.id, tenant_id)
    membership = db.scalar(select(Membership).where(
        Membership.tenant_id == tenant_id, Membership.user_id == user_id,
        Membership.is_active == True,
    ).with_for_update())
    if not membership:
        raise HTTPException(404, "Usuário ativo não encontrado nesta organização.")
    authorize(db, user, tenant_id, "users.invite",
              school_id=membership.school_id, write=True)
    role = db.scalar(select(Role).where(
        Role.id == membership.role_id, Role.tenant_id == tenant_id,
    ))
    if not role or role.code == "org_admin":
        raise HTTPException(403, "Este vínculo é administrado pela plataforma.")
    role_can_delegate(db, user, tenant_id, role, membership.school_id)
    account = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not account or not account.is_active:
        raise HTTPException(409, "A conta está desativada.")
    temporary_password = new_temporary_password()
    expires_at = utcnow() + timedelta(hours=24)
    account.password_hash = hash_password(temporary_password)
    account.must_change_password = True
    account.temporary_password_expires_at = expires_at
    account.session_version += 1
    logged(db, tenant_id, user, "user.password_reset", "user", account.id,
           school_id=membership.school_id, role=role.code)
    db.commit()
    return {
        "user_id": account.id, "email": account.email,
        "temporary_password": temporary_password,
        "temporary_password_expires_at": expires_at.isoformat(),
    }


@app.post("/api/tenants/{tenant_id}/invitations", status_code=201)
def create_invitation(tenant_id: str, data: InvitationCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    if settings.user_provisioning_mode.strip().lower() != "email":
        raise HTTPException(409, "Convites por e-mail estão desativados; use o cadastro administrativo.")
    tenant = authorize(db, user, tenant_id, "users.invite", school_id=data.school_id, write=True)
    if data.school_id:
        ensure_school(db, tenant_id, data.school_id)
    bind_context(db, user.id, tenant_id)
    role = db.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == data.role_id))
    if not role:
        raise HTTPException(404, "Perfil inexistente.")
    if data.school_id is None and role.code != "org_admin":
        # All operational roles besides org admin are explicitly school scoped.
        raise HTTPException(422, "Selecione a unidade para este perfil.")
    role_can_delegate(db, user, tenant_id, role, data.school_id)
    if data.teacher_id:
        if role.code != "teacher" or not data.school_id:
            raise HTTPException(422, "Vínculo de professor exige perfil de professor e escola.")
        t = ensure_teacher(db, tenant_id, data.teacher_id)
        link = db.scalar(select(TeacherSchool).where(TeacherSchool.tenant_id == tenant_id,
                         TeacherSchool.school_id == data.school_id, TeacherSchool.teacher_id == t.id))
        if not link or t.user_id is not None:
            raise HTTPException(409, "Professor sem vínculo disponível com a unidade.")
    active = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(Membership.tenant_id == tenant_id, Membership.is_active == True))
    if active >= tenant.max_users:
        raise HTTPException(409, "Limite de vínculos ativos atingido.")
    inv, token, url = invite_record(db, tenant, data.email, role, data.school_id, user, data.teacher_id)
    sent = deliver_invitation(inv.email, url)
    logged(db, tenant_id, user, "invitation.created", "invitation", inv.id, school=data.school_id, role=role.code)
    db.commit()
    result = {"id": inv.id, "email": inv.email, "sent": sent, "expires_at": iso(inv.expires_at)}
    if settings.environment == "development":
        result["dev_invitation_url"] = url
    return result


@app.get("/api/tenants/{tenant_id}/teachers")
def teachers(tenant_id: str, school_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "teachers.read", school_id=school_id)
    bind_context(db, user.id, tenant_id)
    stmt = (select(Teacher, TeacherSchool).join(TeacherSchool, Teacher.id == TeacherSchool.teacher_id)
            .where(Teacher.tenant_id == tenant_id, Teacher.active == True, TeacherSchool.tenant_id == tenant_id))
    if school_id:
        ensure_school(db, tenant_id, school_id)
        stmt = stmt.where(TeacherSchool.school_id == school_id)
    rows = db.execute(stmt.order_by(Teacher.name)).all()
    seen = {}
    for teacher, link in rows:
        if permitted(db, user, tenant_id, "teachers.read", link.school_id):
            seen.setdefault(teacher.id, {"id": teacher.id, "name": teacher.name, "schools": []})["schools"].append(link.school_id)
    return list(seen.values())


@app.post("/api/tenants/{tenant_id}/teachers", status_code=201)
def create_teacher(tenant_id: str, data: TeacherCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    tenant = authorize(db, user, tenant_id, "teachers.create", data.school_id, write=True)
    bind_context(db, user.id, tenant_id)
    ensure_school(db, tenant_id, data.school_id)
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    n = db.scalar(select(func.count(Teacher.id)).where(Teacher.tenant_id == tenant_id, Teacher.active == True))
    if n >= tenant.max_teachers:
        raise HTTPException(409, "Limite de professores ativos atingido.")
    t = Teacher(tenant_id=tenant_id, name=data.name.strip())
    db.add(t); db.flush()
    db.add(TeacherSchool(tenant_id=tenant_id, teacher_id=t.id, school_id=data.school_id))
    logged(db, tenant_id, user, "teacher.created", "teacher", t.id, school=data.school_id)
    db.commit()
    return {"id": t.id, "name": t.name, "school_id": data.school_id}


@app.get("/api/tenants/{tenant_id}/teachers/{teacher_id}/availability")
def get_availability(tenant_id: str, teacher_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bind_context(db, user.id, tenant_id)
    t = ensure_teacher(db, tenant_id, teacher_id)
    if t.user_id != user.id:
        accessible_teacher(db, user, tenant_id, teacher_id)
    return [{"weekday": x.weekday, "start": hhmm(x.start_minute), "end": hhmm(x.end_minute)}
            for x in db.scalars(select(Availability).where(Availability.tenant_id == tenant_id,
               Availability.teacher_id == teacher_id).order_by(Availability.weekday, Availability.start_minute)).all()]


@app.put("/api/tenants/{tenant_id}/teachers/{teacher_id}/availability")
def replace_availability(tenant_id: str, teacher_id: str, data: AvailabilityReplace, request: Request,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    authorize(db, user, tenant_id, "teachers.availability", write=True)
    bind_context(db, user.id, tenant_id)
    ensure_teacher(db, tenant_id, teacher_id)
    items = sorted([(x.weekday, local_minutes(x.start), local_minutes(x.end)) for x in data.intervals])
    prev = None
    for day, start, end in items:
        if start >= end or (prev and prev[0] == day and start < prev[2]):
            raise HTTPException(422, "Faixas inválidas ou sobrepostas.")
        prev = (day, start, end)
    db.query(Availability).filter(Availability.tenant_id == tenant_id, Availability.teacher_id == teacher_id).delete()
    db.add_all([Availability(tenant_id=tenant_id, teacher_id=teacher_id, weekday=d, start_minute=s, end_minute=e) for d,s,e in items])
    logged(db, tenant_id, user, "availability.replaced", "teacher", teacher_id, intervals=len(items))
    db.commit()
    return {"updated": len(items), "message": "Disponibilidade geral registrada."}


@app.post("/api/tenants/{tenant_id}/teachers/{teacher_id}/availability-requests", status_code=201)
def request_availability(tenant_id: str, teacher_id: str, data: AvailabilityRequestCreate, request: Request,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_write(request)
    bind_context(db, user.id, tenant_id)
    teacher = ensure_teacher(db, tenant_id, teacher_id)
    if teacher.user_id != user.id:
        raise HTTPException(403, "Solicitação permitida apenas ao próprio professor vinculado.")
    linked_schools = db.scalars(select(TeacherSchool.school_id).where(TeacherSchool.teacher_id == teacher_id,
        TeacherSchool.tenant_id == tenant_id)).all()
    authorized_school = next((s for s in linked_schools if permitted(db, user, tenant_id, "teachers.requests.create", s)), None)
    if not authorized_school:
        raise HTTPException(403, "Sem permissão para solicitar nesta unidade.")
    authorize(db, user, tenant_id, "teachers.requests.create", authorized_school, write=True)
    start, end = local_minutes(data.start), local_minutes(data.end)
    if start >= end:
        raise HTTPException(422, "Horário inválido.")
    req = AvailabilityRequest(tenant_id=tenant_id, teacher_id=teacher_id, requested_by=user.id,
                              weekday=data.weekday, start_minute=start, end_minute=end, reason=data.reason)
    db.add(req); db.flush()
    logged(db, tenant_id, user, "availability.requested", "request", req.id)
    db.commit()
    return {"id": req.id, "status": "pending"}


@app.get("/api/tenants/{tenant_id}/audit")
def list_audit(tenant_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "audit.read")
    if not permitted(db, user, tenant_id, "audit.read"):
        raise HTTPException(403, "A auditoria geral requer escopo de organização.")
    bind_context(db, user.id, tenant_id)
    events = db.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.created_at.desc()).limit(50)).all()
    return [{"id": x.id, "action": x.action, "type": x.object_type, "date": iso(x.created_at), "details": x.details} for x in events]


@app.get("/api/tenants/{tenant_id}/my-teacher")
def my_teacher(tenant_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "teachers.self")
    bind_context(db, user.id, tenant_id)
    teacher = db.scalar(select(Teacher).where(Teacher.tenant_id == tenant_id, Teacher.user_id == user.id, Teacher.active == True))
    if not teacher:
        return {"teacher": None, "message": "Nenhum cadastro de professor vinculado a esta conta."}
    intervals = db.scalars(select(Availability).where(Availability.tenant_id == tenant_id, Availability.teacher_id == teacher.id).order_by(Availability.weekday, Availability.start_minute)).all()
    return {"teacher": {"id": teacher.id, "name": teacher.name}, "availability": [{"weekday": x.weekday, "start": hhmm(x.start_minute), "end": hhmm(x.end_minute)} for x in intervals]}


@app.get("/api/tenants/{tenant_id}/availability-requests")
def list_availability_requests(tenant_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize(db, user, tenant_id, "teachers.requests.read")
    bind_context(db, user.id, tenant_id)
    rows = db.execute(select(AvailabilityRequest, Teacher, TeacherSchool)
        .join(Teacher, AvailabilityRequest.teacher_id == Teacher.id)
        .join(TeacherSchool, TeacherSchool.teacher_id == Teacher.id)
        .where(AvailabilityRequest.tenant_id == tenant_id).order_by(AvailabilityRequest.created_at.desc()).limit(100)).all()
    seen = set(); output = []
    for x, t, link in rows:
        if x.id in seen or not permitted(db, user, tenant_id, "teachers.requests.read", link.school_id):
            continue
        seen.add(x.id)
        output.append({"id": x.id, "teacher": t.name, "weekday": x.weekday,
                       "start": hhmm(x.start_minute), "end": hhmm(x.end_minute),
                       "reason": x.reason, "status": x.status})
    return output


# Fase 2: planejamento pedagógico e geração de prévia sem publicação.
from .planning import router as planning_router
app.include_router(planning_router)

from .workflow import router as workflow_router
app.include_router(workflow_router)

# Fase 4C: pré-validação e publicação transacional PostgreSQL.
from .publication import router as publication_router
app.include_router(publication_router)
