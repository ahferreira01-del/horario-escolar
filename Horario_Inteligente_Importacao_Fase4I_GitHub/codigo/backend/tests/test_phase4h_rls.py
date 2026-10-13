"""Testes de regressão Fase 4H — políticas canônicas e SET ROLE."""
import pytest
from app.runtime_checks import validate_rls_contract
from test_phase4g_policy_guard import fixture_contract


def test_pg_catalog_canonical_forms_only():
    assert validate_rls_contract(*fixture_contract()) > 15


def test_noinherit_does_not_prevent_set_role():
    role, tables, policies, names = fixture_contract()
    # Em PostgreSQL, a role NOINHERIT ainda pode fazer SET ROLE para papéis
    # dos quais é membro. A guarda de runtime deve barrar essa associação.
    with pytest.raises(RuntimeError, match='SET ROLE'):
        validate_rls_contract(role, tables, policies, names, ['horario_owner'])


@pytest.mark.parametrize('malicious',[ 
    "tenant_id = tenant_id AND current_setting('app.tenant_id', true) IS NOT NULL",
    "(tenant_id = nullif(current_setting('app.tenant_id', true), ''))OR(true)",
    "tenant_id = nullif(current_setting('app.tenant_id', true), '') AND true",
    "true AND tenant_id = tenant_id AND nullif(current_setting('app.tenant_id', true),'') IS NOT NULL",
])
def test_rls_rejects_policy_with_extra_predicates(malicious):
    role, tables, policies, names = fixture_contract()
    policies[0]['qual'] = malicious
    with pytest.raises(RuntimeError, match='isolamento alterado'):
        validate_rls_contract(role, tables, policies, names)


def test_own_memberships_policy_must_be_permissive():
    role, tables, policies, names = fixture_contract()
    next(p for p in policies if p['policyname']=='own_memberships_read')['permissive'] = 'RESTRICTIVE'
    with pytest.raises(RuntimeError, match='memberships'):
        validate_rls_contract(role, tables, policies, names)
