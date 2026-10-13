"""Comprovação REAL de bloqueio SET ROLE em banco PostgreSQL descartável.

Modificar GRANT de runtime role é proibido fora de ambiente de teste isolado.
"""
import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from app.runtime_checks import verify_database_isolation

OWNER = os.environ.get('HI_TEST_PG_OWNER_URL')
RUNTIME = os.environ.get('HI_TEST_PG_RUNTIME_URL')


@pytest.mark.skipif(not OWNER or not RUNTIME, reason='PostgreSQL efêmero de testes indisponível')
def test_postgres_runtime_membership_must_fail_closed():
    owner = create_engine(OWNER)
    runtime = create_engine(RUNTIME)
    name = 'hi_h_role_' + uuid.uuid4().hex[:12]
    try:
        verify_database_isolation(runtime)
        with owner.begin() as c:
            # O nome é gerado internamente e só contém [a-z0-9_].
            c.execute(text(f'CREATE ROLE {name} NOLOGIN'))
            c.execute(text(f'GRANT {name} TO horario_runtime'))
        with pytest.raises(RuntimeError,match='SET ROLE'):
            verify_database_isolation(runtime)
    finally:
        with owner.begin() as c:
            c.execute(text(f'REVOKE {name} FROM horario_runtime'))
            c.execute(text(f'DROP ROLE IF EXISTS {name}'))
        owner.dispose()
        runtime.dispose()
