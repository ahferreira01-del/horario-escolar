"""Marcador global, mínimo e imutável para o provisionamento inicial.

Revision ID: 0006
Revises: 0005

O marcador não contém nome, e-mail ou senha. Como não contém tenant_id, não é
uma tabela de dados escolares nem integra o conjunto de políticas RLS por tenant.
O runtime só pode ler e inserir; somente a role migradora pode removê-lo.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "initial_provisioning",
        sa.Column("key", sa.String(length=60), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("organization_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("key = 'first-organization-admin'",
                           name="initial_provisioning_singleton_key"),
        sa.UniqueConstraint("organization_id", name="uq_initial_provisioning_organization"),
        sa.UniqueConstraint("admin_user_id", name="uq_initial_provisioning_admin_user"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE ALL ON TABLE public.initial_provisioning FROM PUBLIC")
        op.execute("REVOKE ALL ON TABLE public.initial_provisioning FROM horario_runtime")
        op.execute("GRANT SELECT, INSERT ON TABLE public.initial_provisioning TO horario_runtime")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Não remova o marcador de provisionamento inicial em PostgreSQL; "
            "isso reabilitaria uma operação de primeiro acesso."
        )
    op.drop_table("initial_provisioning")
