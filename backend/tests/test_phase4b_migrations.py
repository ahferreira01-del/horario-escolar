"""Testes de migração em SQLite (NÃO comprovam RLS PostgreSQL)."""
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_schema_alembic_sqlite(tmp_path):
    db = tmp_path / 'new.db'
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{db}')
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'],
                   cwd=ROOT, env=env, check=True, capture_output=True, text=True, timeout=25)
    engine = create_engine(env['DATABASE_URL'])
    tables = set(inspect(engine).get_table_names())
    assert {'tenants', 'users', 'schools', 'teachers', 'grade_proposals', 'published_grades', 'published_lessons', 'published_classes',
            'academic_years', 'teaching_assignments', 'alembic_version'} <= tables
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0005'


def test_rls_migration_covers_every_tenant_table():
    import importlib.util
    from app.cli import RLS_TABLES
    path = ROOT / 'alembic/versions/0002_tenant_rls_and_runtime_grants.py'
    spec = importlib.util.spec_from_file_location('migration_0002', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.TENANT_TABLES) | {'school_travel_times', 'published_grades', 'published_lessons', 'published_classes'} == set(RLS_TABLES)
    assert 'tenant_id' in module.FILTER

def test_sqlite_does_not_claim_postgres_rls():
    from app.runtime_checks import verify_database_isolation
    check = verify_database_isolation(create_engine('sqlite:///:memory:'))
    assert check == {'engine':'sqlite','rls':'not_available'}

def test_postgres_role_guard_denies_superuser_and_owner():
    from app.runtime_checks import verify_database_isolation
    from app.cli import RLS_TABLES

    class Rows:
        def __init__(self, v): self.v = v
        def mappings(self): return self
        def scalars(self): return self
        def one(self): return self.v
        def all(self): return self.v
        def scalar(self): return self.v
    class DummyConnection:
        def __init__(self, role, owner): self.role=role;self.owner=owner
        def execute(self, stmt):
            sql=str(stmt)
            if 'rolsuper' in sql:
                return Rows({'username':'horario_runtime','rolsuper':self.role,
                             'rolbypassrls':False,'rolcreatedb':False,'rolcreaterole':False,'rolinherit':False})
            if 'FROM pg_class' in sql:
                return Rows([{'table_name':t,'relrowsecurity':True,'relforcerowsecurity':True,
                              'owner': self.owner} for t in RLS_TABLES])
            if 'FROM pg_policies' in sql:
                expr="(tenant_id = nullif(current_setting('app.tenant_id', true), ''))"
                rows=[{'tablename':t,'policyname':'tenant_isolation','permissive':'PERMISSIVE',
                       'cmd':'ALL','qual':expr,'with_check':expr} for t in RLS_TABLES]
                rows.append({'tablename':'memberships','policyname':'own_memberships_read',
                             'permissive':'PERMISSIVE','cmd':'SELECT',
                             'qual':"(user_id = nullif(current_setting('app.user_id', true), ''))",
                             'with_check':None})
                return Rows(rows)
            if 'FROM pg_auth_members' in sql:
                return Rows([])
            if 'FROM pg_attribute' in sql:
                return Rows([(t,) for t in RLS_TABLES])
            raise AssertionError(sql)
        def scalar(self, stmt): return '0005'
    class DummyEngine:
        class dialect: name='postgresql'
        def __init__(self, su=False, owner='horario_owner'):
            self.c=DummyConnection(su,owner)
        class CM:
            def __init__(self, c): self.c=c
            def __enter__(self): return self.c
            def __exit__(self,*args): return False
        def connect(self): return self.CM(self.c)

    assert verify_database_isolation(DummyEngine())['rls']=='enforced'
    import pytest
    with pytest.raises(RuntimeError,match='bypass'):
        verify_database_isolation(DummyEngine(su=True))
    with pytest.raises(RuntimeError,match='RLS'):
        verify_database_isolation(DummyEngine(owner='horario_runtime'))
