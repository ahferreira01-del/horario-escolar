"""Modelos de horário por escola, ano letivo e turno.

Revision ID: 0007
Revises: 0006

Revisão local de turnos após as migrations PR9 0004/0005 e o marcador 0006.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


TABLES = (
    "school_shift_schedules",
    "school_shift_schedule_days",
    "school_shift_recesses",
)
TENANT_FILTER = "tenant_id = nullif(current_setting('app.tenant_id', true), '')"


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        role_exists = bind.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'horario_runtime')"
        )).scalar_one()
        if not role_exists:
            raise RuntimeError("Role horario_runtime ausente; a migration de horários não será aplicada.")

    op.create_table(
        "school_shift_schedules",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("school_id", sa.String(36), nullable=False),
        sa.Column("academic_year_id", sa.String(36), nullable=False),
        sa.Column("shift", sa.String(20), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.Column("lesson_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("default_lessons_per_day", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("tenant_id", "school_id", "academic_year_id", "shift",
                           name="uq_school_shift_schedule_context"),
        sa.UniqueConstraint("id", "tenant_id", "school_id", "academic_year_id",
                           name="uq_school_shift_schedule_scope"),
        sa.ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        sa.ForeignKeyConstraint(["academic_year_id", "tenant_id", "school_id"],
                                ["academic_years.id", "academic_years.tenant_id", "academic_years.school_id"]),
        sa.CheckConstraint("shift IN ('manha','tarde','noite')", name="school_shift_schedule_shift_valid"),
        sa.CheckConstraint("start_minute >= 0 AND end_minute <= 1439 AND start_minute < end_minute",
                           name="school_shift_schedule_time_valid"),
        sa.CheckConstraint("lesson_duration_minutes BETWEEN 20 AND 180",
                           name="school_shift_schedule_duration_valid"),
        sa.CheckConstraint("default_lessons_per_day BETWEEN 1 AND 30",
                           name="school_shift_schedule_lesson_count_valid"),
        sa.CheckConstraint("revision >= 1", name="school_shift_schedule_revision_valid"),
    )
    op.create_table(
        "school_shift_schedule_days",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("school_id", sa.String(36), nullable=False),
        sa.Column("academic_year_id", sa.String(36), nullable=False),
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("lessons_per_day", sa.Integer(), nullable=False),
        sa.UniqueConstraint("schedule_id", "weekday", name="uq_school_shift_schedule_day"),
        sa.ForeignKeyConstraint(
            ["schedule_id", "tenant_id", "school_id", "academic_year_id"],
            ["school_shift_schedules.id", "school_shift_schedules.tenant_id",
             "school_shift_schedules.school_id", "school_shift_schedules.academic_year_id"],
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="school_shift_schedule_day_valid"),
        sa.CheckConstraint("(active AND lessons_per_day BETWEEN 1 AND 30) OR "
                           "(NOT active AND lessons_per_day = 0)",
                           name="school_shift_schedule_day_count_valid"),
    )
    op.create_table(
        "school_shift_recesses",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("school_id", sa.String(36), nullable=False),
        sa.Column("academic_year_id", sa.String(36), nullable=False),
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("after_lesson", sa.Integer(), nullable=True),
        sa.Column("start_minute", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("schedule_id", "position", name="uq_school_shift_recess_position"),
        sa.ForeignKeyConstraint(
            ["schedule_id", "tenant_id", "school_id", "academic_year_id"],
            ["school_shift_schedules.id", "school_shift_schedules.tenant_id",
             "school_shift_schedules.school_id", "school_shift_schedules.academic_year_id"],
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 5", name="school_shift_recess_position_valid"),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 180", name="school_shift_recess_duration_valid"),
        sa.CheckConstraint(
            "(mode = 'after_lesson' AND after_lesson BETWEEN 1 AND 29 AND start_minute IS NULL) OR "
            "(mode = 'fixed' AND after_lesson IS NULL AND start_minute BETWEEN 0 AND 1439)",
            name="school_shift_recess_mode_valid",
        ),
    )

    with op.batch_alter_table("school_classes") as batch:
        batch.add_column(sa.Column("shift", sa.String(20), nullable=True))
        batch.add_column(sa.Column("schedule_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("schedule_revision", sa.Integer(), nullable=True))
        batch.create_unique_constraint(
            "uq_school_class_schedule_scope",
            ["id", "tenant_id", "school_id", "academic_year_id"],
        )
        batch.create_foreign_key(
            "fk_school_class_shift_schedule", "school_shift_schedules",
            ["schedule_id", "tenant_id", "school_id", "academic_year_id"],
            ["id", "tenant_id", "school_id", "academic_year_id"],
        )
        batch.create_check_constraint(
            "school_class_shift_valid",
            "shift IS NULL OR shift IN ('manha','tarde','noite')",
        )
        batch.create_check_constraint(
            "school_class_schedule_reference_consistent",
            "(schedule_id IS NULL AND schedule_revision IS NULL) OR "
            "(schedule_id IS NOT NULL AND schedule_revision IS NOT NULL AND shift IS NOT NULL)",
        )

    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON public.{table} FOR ALL "
                f"USING ({TENANT_FILTER}) WITH CHECK ({TENANT_FILTER})"
            )
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO horario_runtime"
            )


def downgrade():
    raise RuntimeError(
        "Migration não destrutiva de calendário: não remova modelos ou vínculos. "
        "Faça rollback do código mantendo o schema."
    )
