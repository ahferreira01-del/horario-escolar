"""Guarda de RLS: testes locais determinísticos, sem simular PostgreSQL como prova real."""
import pytest
from app.cli import RLS_TABLES
from app.runtime_checks import validate_rls_contract


def fixture_contract():
    role = {'username': 'horario_runtime', 'rolsuper': False,
            'rolbypassrls': False, 'rolcreatedb': False,
            'rolcreaterole': False, 'rolinherit': False}
    tables = {t: {'relrowsecurity':True, 'relforcerowsecurity': True,
                   'owner': 'horario_owner'} for t in RLS_TABLES}
    tenant_expression = "(tenant_id = NULLIF(current_setting('app.tenant_id'::text, true), ''::text))"
    policies = [{'tablename': t,'policyname':'tenant_isolation', 'cmd':'ALL',
                 'permissive':'PERMISSIVE','qual':tenant_expression,
                 'with_check':tenant_expression} for t in RLS_TABLES]
    policies.append({'tablename':'memberships','policyname':'own_memberships_read',
                     'cmd':'SELECT','permissive':'PERMISSIVE',
                     'qual':"(user_id = nullif(current_setting('app.user_id', true), ''))",
                     'with_check':None})
    return role,tables,policies,list(RLS_TABLES)


def test_expected_contract_accepted():
    assert validate_rls_contract(*fixture_contract()) == len(RLS_TABLES)


def test_unexpected_permissive_policy_blocks_start():
    role,tables,policies,names=fixture_contract()
    policies.append({'tablename':'schools','policyname':'all_access',
                     'cmd':'ALL','permissive':'PERMISSIVE','qual':'true','with_check':'true'})
    with pytest.raises(RuntimeError,match='políticas inesperadas'):
        validate_rls_contract(role,tables,policies,names)


def test_replacing_tenant_policy_with_true_blocks_start():
    role,tables,policies,names=fixture_contract()
    policies[0]['qual']='true'
    with pytest.raises(RuntimeError,match='isolamento alterado'):
        validate_rls_contract(role,tables,policies,names)


def test_new_tenant_table_without_review_blocks_start():
    role,tables,policies,names=fixture_contract()
    with pytest.raises(RuntimeError,match='sem revisão'):
        validate_rls_contract(role,tables,policies,names+['sensitive_teacher_data'])


def test_unsafe_role_and_owner_blocks_start():
    role,tables,policies,names=fixture_contract()
    role['rolinherit']=True
    with pytest.raises(RuntimeError,match='NOINHERIT'):
        validate_rls_contract(role,tables,policies,names)
    role['rolinherit']=False
    tables['schools']['owner']='horario_runtime'
    with pytest.raises(RuntimeError,match='RLS ausente'):
        validate_rls_contract(role,tables,policies,names)


def test_missing_user_scoping_policy_blocks_start():
    role,tables,policies,names=fixture_contract()
    policies=[p for p in policies if p['policyname']!='own_memberships_read']
    with pytest.raises(RuntimeError,match='memberships'):
        validate_rls_contract(role,tables,policies,names)


def test_tenant_policy_or_true_bypass_is_rejected():
    role,tables,policies,names=fixture_contract()
    policies[0]['qual'] = '(' + policies[0]['qual'] + ' OR true)'
    with pytest.raises(RuntimeError,match='isolamento alterado'):
        validate_rls_contract(role,tables,policies,names)
