"""Persist distributed login throttles in PostgreSQL.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    is_postgres = connection.dialect.name == "postgresql"
    if is_postgres:
        runtime_role = connection.execute(sa.text(
            "SELECT rolsuper = false AND rolbypassrls = false "
            "FROM pg_roles WHERE rolname = 'horario_runtime'"
        )).scalar()
        if runtime_role is not True:
            raise RuntimeError(
                "Role horario_runtime ausente ou privilegiada; "
                "configure uma role de runtime sem BYPASSRLS."
            )

    op.create_table(
        "auth_login_limits",
        sa.Column("identity_hash", sa.String(length=64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempts >= 1", name="auth_login_limits_positive_attempts"
        ),
    )
    op.create_index(
        "ix_auth_login_limits_expires_at",
        "auth_login_limits",
        ["expires_at"],
    )

    if is_postgres:
        op.execute("ALTER TABLE public.auth_login_limits ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.auth_login_limits FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY auth_login_limits_runtime ON public.auth_login_limits "
            "FOR ALL TO horario_runtime USING (true) WITH CHECK (true)"
        )
        op.execute("REVOKE ALL ON public.auth_login_limits FROM PUBLIC")
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON public.auth_login_limits TO horario_runtime"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Reverter o limitador de autenticação removeria uma proteção ativa; "
            "use um procedimento de recuperação aprovado."
        )
    op.drop_index(
        "ix_auth_login_limits_expires_at", table_name="auth_login_limits"
    )
    op.drop_table("auth_login_limits")
