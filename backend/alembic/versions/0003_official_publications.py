"""Reservas oficiais, lotes e deslocamento entre unidades.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
from sqlalchemy import text
import json
from app.models import SchoolTravelTime, PublishedGrade, PublishedLesson, PublishedClass

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None
TABLES = ('school_travel_times', 'published_grades', 'published_lessons', 'published_classes')
FILTER = "tenant_id = nullif(current_setting('app.tenant_id', true), '')"


def upgrade():
    conn = op.get_bind()
    for model in (SchoolTravelTime, PublishedGrade, PublishedLesson, PublishedClass):
        model.__table__.create(bind=conn)
    if conn.dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY')
            op.execute(f'CREATE POLICY tenant_isolation ON public.{table} FOR ALL '
                       f'USING ({FILTER}) WITH CHECK ({FILTER})')
            # Versões oficiais são append-only para o usuário operacional.
            if table in ('published_grades', 'published_lessons', 'published_classes'):
                op.execute(f'REVOKE UPDATE, DELETE ON public.{table} FROM horario_runtime')
                op.execute(f'GRANT SELECT, INSERT ON public.{table} TO horario_runtime')
            else:
                op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO horario_runtime')
        # Atualizar APENAS perfis padrão de organizações já existentes. Permissões
        # customizadas jamais devem ser concedidas silenciosamente.
        for tenant_id, in conn.execute(text('SELECT id FROM public.tenants')).all():
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {'tid':tenant_id})
            roles=conn.execute(text("SELECT id,code,permissions FROM public.roles "
                                    "WHERE is_system = true AND code IN ('org_admin','school_admin')")).all()
            for role_id,code,permissions in roles:
                current=json.loads(permissions) if isinstance(permissions,str) else list(permissions or [])
                new=set(current)|{'grades.publish'}
                if code=='org_admin':new.add('grades.publish_partial')
                conn.execute(text('UPDATE public.roles SET permissions=CAST(:ps AS json) WHERE id=:rid'),
                             {'ps':json.dumps(sorted(new)), 'rid':role_id})


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        raise RuntimeError('Não remover grades oficiais e RLS por downgrade em produção.')
    for table in reversed(TABLES):
        op.drop_table(table)
