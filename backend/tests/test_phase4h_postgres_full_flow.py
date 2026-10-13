"""Homologação API oficial — somente PostgreSQL migrado e descartável.

Não executa no SQLite; requer env HI_TEST_PG_OWNER_URL / HI_TEST_PG_RUNTIME_URL.
A validação da web no navegador é outro gate e não é inferida deste teste.
"""
import io
import os
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import database
from app.main import app
from app.models import User
from app.security import hash_password
from app.runtime_checks import verify_database_isolation
from test_publication import approved, uri
from test_app import tenant_with_admin, login

OWNER = os.environ.get('HI_TEST_PG_OWNER_URL')
RUNTIME = os.environ.get('HI_TEST_PG_RUNTIME_URL')


@pytest.mark.skipif(not OWNER or not RUNTIME, reason='Exige PostgreSQL efêmero, RLS e migrações')
def test_postgres_complete_publish_exports_and_cross_tenant_denial(monkeypatch):
    owner_engine = create_engine(OWNER, pool_pre_ping=True)
    runtime_engine = create_engine(RUNTIME, pool_pre_ping=True)
    try:
        result = verify_database_isolation(runtime_engine)
        assert result['rls'] == 'enforced'
        owner_session = sessionmaker(bind=owner_engine, expire_on_commit=False)
        with owner_session() as db:
            if not db.scalar(select(User).where(User.email=='root@example.com')):
                db.add(User(name='Administrador de Teste',email='root@example.com',
                            password_hash=hash_password('Senha-muito-forte-123'),
                            is_platform_admin=True))
                db.commit()
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=runtime_engine, expire_on_commit=False))
        suffix='full-'+uuid.uuid4().hex[:12]
        with TestClient(app) as c:
            tid,sid,_,headers,_,body=approved(c,suffix)
            pre=c.post(uri(tid)+'/preflight',json=body)
            assert pre.status_code==200,pre.text
            assert pre.json()['eligible'] and pre.json()['dated_occurrences']>0
            published=c.post(uri(tid)+'/publish',headers=headers,json=body)
            assert published.status_code==201,published.text
            # A segunda tentativa deve falhar por sobreposição de vigência.
            duplicate=c.post(uri(tid)+'/publish',headers=headers,json=body)
            assert duplicate.status_code==409,duplicate.text
            listing=c.get(uri(tid),params={'school_id':sid})
            assert listing.status_code==200,listing.text
            assert len(listing.json())==1
            publication_id=listing.json()[0]['id']
            grade=c.get(uri(tid)+'/'+publication_id)
            assert grade.status_code==200 and len(grade.json()['lessons'])==2
            csv=c.get(uri(tid)+'/'+publication_id+'/export.csv')
            pdf=c.get(uri(tid)+'/'+publication_id+'/export.pdf')
            xlsx=c.get(uri(tid)+'/'+publication_id+'/export.xlsx')
            assert csv.status_code==200 and b'HOR' in csv.content
            assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
            assert xlsx.status_code==200
            with zipfile.ZipFile(io.BytesIO(xlsx.content)) as f:
                assert f.testzip() is None
                assert 'xl/workbook.xml' in f.namelist()
            # Uma organização B independente não pode sequer baixar o arquivo A.
            tenant_with_admin(c, suffix+'-other')
            assert c.get(uri(tid),params={'school_id':sid}).status_code==403
            assert c.get(uri(tid)+'/'+publication_id).status_code in (403,404)
            assert c.get(uri(tid)+'/'+publication_id+'/export.xlsx').status_code in (403,404)
            assert c.get(uri(tid)+'/'+publication_id+'/export.pdf').status_code in (403,404)
            # Voltar à organização A não pode alterar uma versão passada.
            login(c,f'diretor-{suffix}@example.com','Senha-forte-diretor-123')
            assert len(c.get(uri(tid),params={'school_id':sid}).json())==1
    finally:
        owner_engine.dispose()
        runtime_engine.dispose()
