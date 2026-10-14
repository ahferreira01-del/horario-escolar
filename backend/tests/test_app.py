"""Testes unitários auxiliares com SQLite em memória; não comprovam RLS ou integração."""
import urllib.parse
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import database
from app.database import Base
from app.models import User, Membership, School, Teacher, TeacherSchool, Tenant
from app.main import app
from app.security import hash_password


@pytest.fixture
def context(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", Session)
    with Session() as db:
        db.add(User(email="root@example.com", name="Root", password_hash=hash_password("Senha-muito-forte-123"), is_platform_admin=True))
        db.commit()
    client = TestClient(app)
    yield client, Session
    client.close(); engine.dispose()


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email":email,"password":password})
    assert r.status_code==200, r.text
    return {"X-CSRF-Token":r.json()["csrf"]}


def tenant_with_admin(client, suffix):
    root_headers = login(client, "root@example.com", "Senha-muito-forte-123")
    r = client.post("/api/platform/tenants", headers=root_headers,
                    json={"name":f"Rede {suffix}","first_admin_email":f"diretor-{suffix}@example.com","first_admin_name":f"Diretor {suffix}"})
    assert r.status_code==201, r.text
    tenant_id = r.json()["id"]
    parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(r.json()["dev_invitation_url"]).query)
    r = client.post("/api/auth/accept-invitation",json={"tenant_id":tenant_id,"token":parsed["token"][0],"name":"Diretor","password":"Senha-forte-diretor-123"})
    assert r.status_code==200, r.text
    h={"X-CSRF-Token":r.json()["csrf"]}
    return tenant_id, h


def school(client, tenant_id, h, name="Centro"):
    r=client.post(f"/api/tenants/{tenant_id}/schools",headers=h,json={"name":name})
    assert r.status_code==201, r.text
    return r.json()["id"]


def invitation(client, tenant, h, role, school_id, email, teacher_id=None):
    roles=client.get(f"/api/tenants/{tenant}/roles").json()
    role_id=next(r["id"] for r in roles if r["code"]==role)
    r=client.post(f"/api/tenants/{tenant}/invitations",headers=h,json={"email":email,"role_id":role_id,"school_id":school_id,"teacher_id":teacher_id})
    assert r.status_code==201, r.text
    return urllib.parse.parse_qs(urllib.parse.urlsplit(r.json()["dev_invitation_url"]).query)["token"][0]


def accept(client, tenant, token, name="Usuário"):
    r=client.post("/api/auth/accept-invitation",json={"tenant_id":tenant,"token":token,"name":name,"password":"senha-super-segura-123"})
    assert r.status_code==200, r.text
    return {"X-CSRF-Token":r.json()["csrf"]}


def test_health(context):
    client,_=context
    assert client.get("/api/health").json()["status"]=="ok"
    assert client.get("/api/auth/me").status_code==401


def test_invite_only_and_csrf(context):
    client,_=context
    tid,h=tenant_with_admin(client,"alfa")
    assert client.post(f"/api/tenants/{tid}/schools", json={"name":"Test"}).status_code==403
    assert client.post("/api/platform/tenants",headers=h,json={"name":"Illegal","first_admin_email":"x@example.com","first_admin_name":"X X"}).status_code==403
    assert school(client,tid,h)


def test_school_and_teacher_scope(context):
    client,_=context
    tid,h=tenant_with_admin(client,"alfa")
    one=school(client,tid,h,"Escola Centro")
    two=school(client,tid,h,"Escola Norte")
    r=client.post(f"/api/tenants/{tid}/teachers",headers=h,json={"name":"Professor Centro","school_id":one})
    assert r.status_code==201
    teacher_id=r.json()["id"]
    invite=invitation(client,tid,h,"school_admin",one,"schooladmin@example.com")
    h_admin=accept(client,tid,invite)
    assert len(client.get(f"/api/tenants/{tid}/schools").json())==1
    assert client.get(f"/api/tenants/{tid}/teachers").json()[0]["id"]==teacher_id
    assert client.get(f"/api/tenants/{tid}/teachers?school_id={two}").status_code==403
    assert client.post(f"/api/tenants/{tid}/teachers", headers=h_admin,json={"name":"Tentativa","school_id":two}).status_code==403
    assert client.post(f"/api/tenants/{tid}/schools", headers=h_admin,json={"name":"Nao pode"}).status_code==403
    assert client.put(f"/api/tenants/{tid}/teachers/{teacher_id}/availability",headers=h_admin,json={"intervals":[]}).status_code==403


def test_cross_tenant_isolation(context):
    client,_=context
    a,ha=tenant_with_admin(client,"alfa")
    sa=school(client,a,ha,"Escola A")
    b,hb=tenant_with_admin(client,"beta")
    sb=school(client,b,hb,"Escola B")
    assert client.get(f"/api/tenants/{a}/schools").status_code==403
    assert client.post(f"/api/tenants/{a}/schools",headers=hb,json={"name":"Invasao"}).status_code==403
    assert client.get(f"/api/tenants/{b}/schools").json()[0]["id"]==sb
    assert client.get(f"/api/tenants/{a}/teachers").status_code==403
    assert client.post(f"/api/tenants/{b}/teachers",headers=hb,json={"name":"Inválido","school_id":sa}).status_code==404


def test_availability_exact_and_overlap(context):
    client,_=context
    t,h=tenant_with_admin(client,"alfa")
    s=school(client,t,h)
    teacher_id=client.post(f"/api/tenants/{t}/teachers",headers=h,json={"name":"Paulo","school_id":s}).json()["id"]
    endpoint=f"/api/tenants/{t}/teachers/{teacher_id}/availability"
    r=client.put(endpoint,headers=h,json={"intervals":[{"weekday":1,"start":"10:45","end":"12:00"},{"weekday":2,"start":"07:00","end":"08:40"}]})
    assert r.status_code==200, r.text
    assert client.get(endpoint).json()[0]["start"]=="10:45"
    bad=client.put(endpoint,headers=h,json={"intervals":[{"weekday":1,"start":"10:45","end":"12:00"},{"weekday":1,"start":"11:00","end":"12:10"}]})
    assert bad.status_code==422
    assert len(client.get(endpoint).json())==2


def test_custom_role_no_escalation_and_invitation_reuse(context):
    client,_=context
    t,h=tenant_with_admin(client,"alfa")
    s=school(client,t,h)
    r=client.post(f"/api/tenants/{t}/roles",headers=h,json={"name":"Leitura","code":"leitura_escolas","permissions":["schools.read"]})
    assert r.status_code==201
    token=invitation(client,t,h,"viewer",s,"consulta@example.com")
    h_view=accept(client,t,token)
    assert client.get(f"/api/tenants/{t}/schools").status_code==200
    assert client.post(f"/api/tenants/{t}/roles",headers=h_view,json={"name":"Super","code":"superadmin","permissions":["roles.manage"]}).status_code==403
    assert client.post("/api/auth/accept-invitation",json={"tenant_id":t,"token":token,"name":"Consulta","password":"senha-super-segura-123"}).status_code==400


def test_teacher_invite_request_flow(context):
    client,_=context
    t,h=tenant_with_admin(client,"alfa")
    s=school(client,t,h)
    teacher_id=client.post(f"/api/tenants/{t}/teachers",headers=h,json={"name":"Paulo","school_id":s}).json()["id"]
    token=invitation(client,t,h,"teacher",s,"paulo@example.com",teacher_id=teacher_id)
    h_prof=accept(client,t,token,"Paulo")
    r=client.get(f"/api/tenants/{t}/my-teacher")
    assert r.status_code==200 and r.json()["teacher"]["id"]==teacher_id
    req=client.post(f"/api/tenants/{t}/teachers/{teacher_id}/availability-requests",headers=h_prof,json={"weekday":1,"start":"10:45","end":"12:00","reason":"Outra escola"})
    assert req.status_code==201,req.text
    assert client.put(f"/api/tenants/{t}/teachers/{teacher_id}/availability",headers=h_prof,json={"intervals":[]}).status_code==403
    login(client,"diretor-alfa@example.com","Senha-forte-diretor-123")
    result=client.get(f"/api/tenants/{t}/availability-requests")
    assert len(result.json())==1 and result.json()[0]["status"]=="pending"


def test_suspended_tenant_and_quota(context):
    client,Session=context
    t,h=tenant_with_admin(client,"alfa")
    with Session() as db:
        o=db.get(Tenant,t);o.max_schools=1;db.commit()
    school(client,t,h)
    assert client.post(f"/api/tenants/{t}/schools",headers=h,json={"name":"Segunda"}).status_code==409
    with Session() as db:
        o=db.get(Tenant,t);o.status="suspended";o.suspension_mode="read_only";db.commit()
    assert client.get(f"/api/tenants/{t}/schools").status_code==200
    assert client.post(f"/api/tenants/{t}/schools",headers=h,json={"name":"Terceira"}).status_code==423
    with Session() as db:
        o=db.get(Tenant,t);o.suspension_mode="blocked";db.commit()
    assert client.get(f"/api/tenants/{t}/schools").status_code==423
