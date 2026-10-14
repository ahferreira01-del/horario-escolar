"""Executar SOMENTE com banco PostgreSQL temporário já migrado (não produção).

Env: HI_TEST_PG_OWNER_URL, HI_TEST_PG_RUNTIME_URL.
Teste o deny-by-default e a negação cruzada diretamente no PostgreSQL,
sem depender do escopo implementado pela API.
"""
import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from postgres_test_safety import postgres_tests_may_skip

owner_url = os.getenv('HI_TEST_PG_OWNER_URL')
runtime_url = os.getenv('HI_TEST_PG_RUNTIME_URL')

@pytest.mark.skipif(
    postgres_tests_may_skip(owner_url, runtime_url),
    reason='PostgreSQL efêmero opcional não configurado fora do gate CI obrigatório',
)
def test_postgres_rls_no_cross_tenant():
    from app.runtime_checks import verify_database_isolation
    own = create_engine(owner_url)
    run = create_engine(runtime_url)
    verify_database_isolation(run)
    ta, tb = str(uuid.uuid4()), str(uuid.uuid4())
    sa, sb = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        with own.begin() as c:
            for tid in (ta, tb):
                c.execute(text("INSERT INTO tenants(id,name,status,suspension_mode,max_schools,max_teachers,max_users,created_at) "
                               "VALUES (:id,'TEST TENANT','active',null,5,150,200,now())"), {'id':tid})
            # Owner PostgreSQL na migração é o dono; FORCE RLS exige contexto tenant.
            for tid, sid in ((ta,sa),(tb,sb)):
                c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {'t':tid})
                c.execute(text("INSERT INTO schools(id,tenant_id,name,timezone,is_active) "
                               "VALUES (:id,:t,'TEST SCHOOL','America/Sao_Paulo',true)"), {'id':sid,'t':tid})
        with run.begin() as c:
            assert c.scalar(text("SELECT count(*) FROM schools WHERE id IN (:a,:b)"), {'a':sa,'b':sb}) == 0
            c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {'t':ta})
            ids = set(c.scalars(text("SELECT id FROM schools WHERE id IN (:a,:b)"), {'a':sa,'b':sb}))
            assert ids == {sa}
        with run.begin() as c:
            c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {'t':tb})
            assert set(c.scalars(text("SELECT id FROM schools WHERE id IN (:a,:b)"), {'a':sa,'b':sb})) == {sb}
            assert c.execute(text("UPDATE schools SET name='BAD' WHERE id=:sid"),{'sid':sa}).rowcount == 0
        # A política WITH CHECK proíbe escrita em organização fora do contexto.
        with pytest.raises(Exception):
            with run.begin() as c:
                c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {'t':tb})
                c.execute(text("INSERT INTO schools(id,tenant_id,name,timezone,is_active) "
                               "VALUES (:id,:t,'BLOCKED','America/Sao_Paulo',true)"),
                          {'id':str(uuid.uuid4()), 't':ta})
        with run.begin() as c:
            with pytest.raises(Exception):
                c.execute(text('DROP TABLE schools'))
    finally:
        # Cleanup com superusuário de TESTE isolado, em transação. FK de cascata ausente,
        # eliminar dependentes criados manualmente primeiro.
        with own.begin() as c:
            for tid, sid in ((ta,sa),(tb,sb)):
                c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {'t':tid})
                c.execute(text('DELETE FROM schools WHERE id=:sid'),{'sid':sid})
                c.execute(text('DELETE FROM tenants WHERE id=:tid'),{'tid':tid})
        own.dispose(); run.dispose()

@pytest.mark.skipif(
    postgres_tests_may_skip(owner_url, runtime_url),
    reason='PostgreSQL efêmero opcional não configurado fora do gate CI obrigatório',
)
def test_postgres_guard_rejects_extra_permissive_policy():
    """Teste REAL de fail-closed: uma segunda política OR true não pode passar no startup.

    Requer PostgreSQL efêmero de CI: esta função modifica políticas no catálogo.
    Não executar contra bancos com dados reais.
    """
    from app.runtime_checks import verify_database_isolation
    from sqlalchemy import create_engine, text
    owner = create_engine(owner_url)
    runtime = create_engine(runtime_url)
    try:
        verify_database_isolation(runtime)
        with owner.begin() as conn:
            conn.execute(text("CREATE POLICY unsafe_phase4g ON public.schools "
                              "FOR SELECT TO PUBLIC USING (true)"))
        with pytest.raises(RuntimeError, match='políticas inesperadas'):
            verify_database_isolation(runtime)
    finally:
        with owner.begin() as conn:
            conn.execute(text('DROP POLICY IF EXISTS unsafe_phase4g ON public.schools'))
        owner.dispose()
        runtime.dispose()
