"""Add one-time password state and session revocation version.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("temporary_password_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "users",
        sa.Column(
            "session_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        unsafe = connection.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM public.users "
                "WHERE must_change_password OR session_version <> 0)"
            )
        ).scalar()
        if unsafe:
            raise RuntimeError(
                "Não é seguro remover estado de senha temporária ou revogação "
                "de sessões; conclua a recuperação antes do downgrade."
            )
    op.drop_column("users", "session_version")
    op.drop_column("users", "temporary_password_expires_at")
    op.drop_column("users", "must_change_password")
