"""Teste real de publicação concorrente (somente PostgreSQL efêmero migrado).

As credenciais OWNER/RUNTIME são fornecidas pelo CI. Este teste NÃO é
substituível por SQLite: advisory locks e RLS precisam ser PostgreSQL reais.
A base fornecida DEVE ser descartável: cria contas e uma organização de teste.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import database
from app.main import app
from app.models import User
from app.security import hash_password
from app.runtime_checks import verify_database_isolation
from test_publication import approved, uri

OWNER=os.getenv('HI_TEST_PG_OWNER_URL')
RUNTIME=os.getenv('HI_TEST_PG_RUNTIME_URL')


@pytest.mark.skipif(not OWNER or not RUNTIME, reason='Requer PostgreSQL efêmero de CI')
def test_real_postgres_atomic_publish_no_duplicate_competing_requests(monkeypatch):
    owner_engine=create_engine(OWNER,pool_pre_ping=True)
    runtime_engine=create_engine(RUNTIME,pool_pre_ping=True)
    verify_database_isolation(runtime_engine)
    owner_session=sessionmaker(bind=owner_engine,expire_on_commit=False)
    runtime_session=sessionmaker(bind=runtime_engine,expire_on_commit=False)
    with owner_session() as db:
        if not db.scalar(select(User).where(User.email=='root@example.com')):
            db.add(User(name='Administrador de Teste',email='root@example.com',
                        password_hash=hash_password('Senha-muito-forte-123'),
                        is_platform_admin=True))
            db.commit()
    monkeypatch.setattr(database, 'SessionLocal', runtime_session)
    suffix='pg-race-'+uuid.uuid4().hex[:8]
    with TestClient(app) as cli:
        tid,sid,year,admin,_,body=approved(cli,suffix)
    # Cada concorrente usa seu próprio cliente/cookie, compartilhando o MESMO
    # PostgreSQL runtime; não há sessão SQLAlchemy compartilhada entre threads.
    barrier=Barrier(2)
    def contender():
        with TestClient(app) as c:
            email=f'diretor-{suffix}@example.com'
            r=c.post('/api/auth/login',json={'email':email,'password':'Senha-forte-diretor-123'})
            assert r.status_code==200,r.text
            h={'X-CSRF-Token':r.json()['csrf']}
            barrier.wait(timeout=15)
            response=c.post(uri(tid)+'/publish',headers=h,json=body)
            return response.status_code, response.json()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            fa=executor.submit(contender)
            fb=executor.submit(contender)
            a,b=fa.result(timeout=45),fb.result(timeout=45)
        assert sorted([a[0],b[0]])==[201,409],(a,b)
        with TestClient(app) as verify:
            r=verify.post('/api/auth/login',json={
                'email':f'diretor-{suffix}@example.com',
                'password':'Senha-forte-diretor-123'})
            assert r.status_code==200
            published=verify.get(uri(tid),params={'school_id':sid})
            assert published.status_code==200,published.text
            assert len(published.json())==1,published.json()
    finally:
        owner_engine.dispose();runtime_engine.dispose()
