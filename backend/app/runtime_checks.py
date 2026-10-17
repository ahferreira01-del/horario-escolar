"""Controles de inicialização fail-closed para isolamento multiempresa PostgreSQL.

Além de verificar ENABLE/FORCE RLS, examina TODAS as políticas relevantes.
Uma nova política PERMISSIVE pode efetivamente transformar ``tenant A OR true``
e expor dados entre organizações, mesmo que ``tenant_isolation`` exista.
"""
import re
from sqlalchemy import text
from .database import engine
from .cli import RLS_TABLES


def _policy_has_context(expression: str | None, setting: str, column: str) -> bool:
    """Só aceita igualdade canônica do escopo RLS, nunca uma substring.

    A forma `tenant_id = tenant_id AND current_setting(...) IS NOT NULL`,
    por exemplo, contém palavras corretas, mas não filtra o tenant.
    Expressões novas exigem revisão explícita antes de chegar à produção.
    """
    compact = re.sub(r"\s+", "", expression or "").lower()
    # O pg_policies converte VARCHAR para TEXT no lado esquerdo:
    # ((tenant_id)::text = NULLIF(current_setting('app.tenant_id'::text, true), ''::text))
    # Aceitar SOMENTE a igualdade estrutural com ou sem este cast, nunca AND/OR.
    lhs = rf"(?:{re.escape(column)}|\({re.escape(column)}\)::text)"
    expected = (rf"\(*{lhs}=nullif\(current_setting\("
                rf"'{re.escape(setting)}'(?:::text)?,true\),''(?:::text)?\)\)*")
    return re.fullmatch(expected, compact) is not None


def validate_rls_contract(role, tables, policies, tenant_tables, role_memberships=()):
    """Valida metadados obtidos do catálogo PostgreSQL, sem alterar o banco.

    Política desconhecida ou expressão modificada = BLOQUEIO; a equipe precisa
    revisar explicitamente uma mudança na barreira de isolamento.
    """
    if any(role.get(k) for k in ('rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole')):
        raise RuntimeError('Banco inseguro: role da API possui privilégios administrativos/bypass.')
    if role.get('rolinherit'):
        raise RuntimeError('Banco inseguro: role da API deve ser NOINHERIT.')
    # Mesmo com NOINHERIT, o runtime pode executar SET ROLE sobre uma role
    # concedida diretamente. A conta operacional não terá NENHUMA associação.
    if role_memberships:
        raise RuntimeError('Banco inseguro: role da API pode executar SET ROLE.')

    expected = set(RLS_TABLES)
    unreviewed = sorted(set(tenant_tables) - expected)
    if unreviewed:
        raise RuntimeError('Tabelas com tenant_id sem revisão de RLS: ' + ', '.join(unreviewed))

    by_table = {}
    for p in policies:
        by_table.setdefault(p['tablename'], []).append(p)
    missing = []
    for table in RLS_TABLES:
        info = tables.get(table)
        if not info or not info['relrowsecurity'] or not info['relforcerowsecurity'] or info['owner'] == role['username']:
            missing.append(table)
            continue
        ps = by_table.get(table, [])
        names = {p['policyname'] for p in ps}
        allowed = {'tenant_isolation', 'own_memberships_read'} if table == 'memberships' else {'tenant_isolation'}
        if names != allowed or len(ps) != len(allowed):
            missing.append(f'{table}(políticas inesperadas/ausentes)')
            continue
        isolation = next(p for p in ps if p['policyname'] == 'tenant_isolation')
        if (isolation['cmd'] != 'ALL' or isolation['permissive'] != 'PERMISSIVE'
                or not _policy_has_context(isolation['qual'], 'app.tenant_id', 'tenant_id')
                or not _policy_has_context(isolation['with_check'], 'app.tenant_id', 'tenant_id')
                or 'tenant_id' not in isolation['qual'].lower()
                or 'tenant_id' not in isolation['with_check'].lower()):
            missing.append(f'{table}(isolamento alterado)')
            continue
        if table == 'memberships':
            own = next(p for p in ps if p['policyname'] == 'own_memberships_read')
            if (own['cmd'] != 'SELECT' or own['permissive'] != 'PERMISSIVE' or not own['qual']
                    or not _policy_has_context(own['qual'], 'app.user_id', 'user_id')
                    or 'user_id' not in own['qual'].lower()):
                missing.append('memberships(leitura própria insegura)')
    if missing:
        raise RuntimeError('PostgreSQL RLS ausente/insegura: ' + ', '.join(missing))
    return len(RLS_TABLES)


def verify_database_isolation(db_engine=None):
    db_engine = db_engine or engine
    if db_engine.dialect.name != 'postgresql':
        return {'engine': db_engine.dialect.name, 'rls': 'not_available'}
    with db_engine.connect() as conn:
        role = conn.execute(text("""
            SELECT current_user AS username, rolsuper, rolbypassrls, rolcreatedb,
                   rolcreaterole, rolinherit
            FROM pg_roles WHERE rolname = current_user
        """)).mappings().one()
        rows = conn.execute(text("""
            SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                   pg_get_userbyid(c.relowner) AS owner
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
        """)).mappings().all()
        tables = {r['table_name']: r for r in rows}
        policies = conn.execute(text("""
            SELECT tablename, policyname, permissive, cmd, qual, with_check
            FROM pg_policies WHERE schemaname='public'
        """)).mappings().all()
        tenant_tables = [row[0] for row in conn.execute(text("""
            SELECT DISTINCT c.relname FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
              AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
        """)).all()]
        # A ausência de INHERIT não impede SET ROLE. Proibir memberships.
        role_memberships = conn.execute(text("SELECT granted.rolname "
            "FROM pg_auth_members m "
            "JOIN pg_roles actor ON actor.oid = m.member "
            "JOIN pg_roles granted ON granted.oid = m.roleid "
            "WHERE actor.rolname = current_user")).scalars().all()
        checked = validate_rls_contract(role, tables, policies, tenant_tables, role_memberships)
        version = conn.scalar(text('SELECT version_num FROM alembic_version'))
        if version != '0005':
            raise RuntimeError('Banco não está na migração aprovada (0005).')
        return {'engine': 'postgresql', 'rls': 'enforced', 'checked_tables': checked}
