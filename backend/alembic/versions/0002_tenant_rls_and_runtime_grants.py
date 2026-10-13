"""Policies RLS por organização e privilégios mínimos de runtime.

Revision ID: 0002
Revises: 0001

Na instância PostgreSQL, horario_runtime DEVE existir ANTES desta migração.
Não remover esta camada de isolamento por downgrade em produção.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

TENANT_TABLES = (
    'schools', 'roles', 'memberships', 'invitations', 'teachers',
    'teacher_schools', 'availabilities', 'availability_requests',
    'audit_logs', 'academic_years', 'subjects', 'school_classes',
    'class_periods', 'teaching_assignments', 'teacher_limits',
    'teacher_weekly_limits', 'school_resources', 'resource_availabilities',
    'grade_proposals',
)
# Lista fechada e revisada: NUNCA receber nomes de tabela vindos de requisições.
FILTER = "tenant_id = nullif(current_setting('app.tenant_id', true), '')"


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != 'postgresql':
        return  # SQLite em testes NÃO possui RLS. Nunca equivalente a PostgreSQL.

    exists = connection.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'horario_runtime')"
    ))
    if not exists:
        raise RuntimeError('Role horario_runtime ausente; configure o banco de forma segregada antes da migração.')

    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public.{table}')
        op.execute(f'DROP POLICY IF EXISTS own_memberships_read ON public.{table}') if table == 'memberships' else None
        op.execute(
            f'CREATE POLICY tenant_isolation ON public.{table} FOR ALL '
            f'USING ({FILTER}) WITH CHECK ({FILTER})'
        )
    # A identificação do contexto de conta permite consultar SOMENTE as próprias
    # associações de usuário antes de escolher um tenant. Não libera WRITE.
    op.execute('CREATE POLICY own_memberships_read ON public.memberships FOR SELECT '
               "USING (user_id = nullif(current_setting('app.user_id', true), ''))")

    op.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    op.execute('GRANT USAGE ON SCHEMA public TO horario_runtime')
    # O controle lógico de operações continua na API. RLS impede vazamentos cruzados;
    # não é substituto de permissão por escola/perfil.
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO horario_runtime')
    op.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO horario_runtime')


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        raise RuntimeError('Reversão que remove RLS não é permitida; restaure backup validado com procedimento seguro.')
