import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Integer, JSON, UniqueConstraint, Index, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db_base import Base


def uid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    suspension_mode: Mapped[str | None] = mapped_column(String(20))
    max_schools: Mapped[int] = mapped_column(Integer, default=5)
    max_teachers: Mapped[int] = mapped_column(Integer, default=150)
    max_users: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class School(Base):
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    timezone: Mapped[str] = mapped_column(String(80), default="America/Sao_Paulo")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(70))
    name: Mapped[str] = mapped_column(String(100))
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("tenant_id", "code"), UniqueConstraint("id", "tenant_id"))


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    school_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("schools.id"))
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "school_id", "role_id"),
        ForeignKeyConstraint(["role_id", "tenant_id"], ["roles.id", "roles.tenant_id"]),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
    )


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"))
    teacher_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teachers.id"))
    school_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("schools.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(["role_id", "tenant_id"], ["roles.id", "roles.tenant_id"]),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
    )


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)


class TeacherSchool(Base):
    __tablename__ = "teacher_schools"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(String(36), ForeignKey("teachers.id"))
    school_id: Mapped[str] = mapped_column(String(36), ForeignKey("schools.id"))
    __table_args__ = (
        UniqueConstraint("teacher_id", "school_id"),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
    )


class Availability(Base):
    __tablename__ = "availabilities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(String(36), ForeignKey("teachers.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        Index("ix_availability_teacher_day", "tenant_id", "teacher_id", "weekday"),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
    )


class AvailabilityRequest(Base):
    __tablename__ = "availability_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(String(36), ForeignKey("teachers.id"))
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    weekday: Mapped[int] = mapped_column(Integer)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(600))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(90))
    object_type: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Fase 2: planejamento pedagógico por escola e ano; nenhum registro é uma grade publicada.
class AcademicYear(Base):
    __tablename__ = "academic_years"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "school_id", "year"),
        UniqueConstraint("id", "tenant_id", "school_id"),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        CheckConstraint("year BETWEEN 2000 AND 2200", name="academic_year_range"),
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "school_id", "name"),
        UniqueConstraint("id", "tenant_id", "school_id"),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
    )


class SchoolClass(Base):
    __tablename__ = "school_classes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    academic_year_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    students: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("academic_year_id", "name"),
        UniqueConstraint("id", "tenant_id", "school_id"),
        ForeignKeyConstraint(["academic_year_id", "tenant_id", "school_id"], ["academic_years.id", "academic_years.tenant_id", "academic_years.school_id"]),
        CheckConstraint("students BETWEEN 1 AND 500", name="class_students_range"),
    )


class ClassPeriod(Base):
    __tablename__ = "class_periods"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    shift: Mapped[str] = mapped_column(String(40), nullable=False)
    __table_args__ = (
        UniqueConstraint("class_id", "weekday", "position"),
        ForeignKeyConstraint(["class_id", "tenant_id", "school_id"], ["school_classes.id", "school_classes.tenant_id", "school_classes.school_id"]),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="period_day_range"),
        CheckConstraint("position BETWEEN 1 AND 30", name="period_position_range"),
        CheckConstraint("start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute", name="period_time_range"),
    )


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    teacher_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lessons: Mapped[int] = mapped_column(Integer, nullable=False)
    load_mode: Mapped[str] = mapped_column(String(10), default="lessons", nullable=False)
    target_minutes: Mapped[int | None] = mapped_column(Integer)
    min_minutes: Mapped[int | None] = mapped_column(Integer)
    max_minutes: Mapped[int | None] = mapped_column(Integer)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    max_consecutive: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    __table_args__ = (
        UniqueConstraint("class_id", "subject_id", "teacher_id"),
        ForeignKeyConstraint(["class_id", "tenant_id", "school_id"], ["school_classes.id", "school_classes.tenant_id", "school_classes.school_id"]),
        ForeignKeyConstraint(["subject_id", "tenant_id", "school_id"], ["subjects.id", "subjects.tenant_id", "subjects.school_id"]),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
        CheckConstraint("lessons BETWEEN 1 AND 50", name="assignment_lessons_range"),
        CheckConstraint("load_mode IN ('lessons','minutes')", name="assignment_mode"),
        CheckConstraint("target_minutes IS NULL OR target_minutes BETWEEN 1 AND 2000"),
        CheckConstraint("min_minutes IS NULL OR min_minutes BETWEEN 1 AND 2000"),
        CheckConstraint("max_minutes IS NULL OR max_minutes BETWEEN 1 AND 2000"),
        CheckConstraint("max_consecutive BETWEEN 1 AND 2", name="assignment_consecutive_range"),
    )


# Fase 3: limites gerais por professor e recursos da unidade.
# Novas bases: create_all; instalações existentes precisam de migração Alembic ANTES de uso.
class TeacherLimit(Base):
    __tablename__ = "teacher_limits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(String(36), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    max_lessons: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "teacher_id", "weekday"),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
        CheckConstraint("weekday BETWEEN 0 AND 6"),
        CheckConstraint("max_lessons BETWEEN 0 AND 30"),
    )

class TeacherWeeklyLimit(Base):
    __tablename__ = "teacher_weekly_limits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(String(36), nullable=False)
    max_lessons: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "teacher_id"),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
        CheckConstraint("max_lessons BETWEEN 0 AND 150"),
    )

class SchoolResource(Base):
    __tablename__ = "school_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    max_groups: Mapped[int] = mapped_column(Integer, nullable=False)
    max_students: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", "school_id"),
        UniqueConstraint("tenant_id", "school_id", "name"),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        CheckConstraint("max_groups BETWEEN 1 AND 50"),
        CheckConstraint("max_students BETWEEN 1 AND 5000"),
    )

class ResourceAvailability(Base):
    __tablename__ = "resource_availabilities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["resource_id", "tenant_id", "school_id"], ["school_resources.id", "school_resources.tenant_id", "school_resources.school_id"]),
        CheckConstraint("weekday BETWEEN 0 AND 6"),
        CheckConstraint("start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute"),
    )


# Fase 4A: propostas de grade, APENAS PARA REVISÃO; nunca publicadas nesta fase.
class GradeProposal(Base):
    __tablename__ = "grade_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    academic_year_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    justification: Mapped[str | None] = mapped_column(String(1000))
    decision_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(["academic_year_id", "tenant_id", "school_id"], ["academic_years.id", "academic_years.tenant_id", "academic_years.school_id"]),
        UniqueConstraint("id", "tenant_id", "school_id"),
        CheckConstraint("status IN ('draft','submitted','approved','rejected')", name="proposal_status_check"),
        Index("ix_proposals_school_year", "tenant_id", "school_id", "academic_year_id", "created_at"),
    )


# Fase 4C: publicação imutável; lotes somente com transação confirmada.
class SchoolTravelTime(Base):
    __tablename__ = "school_travel_times"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    from_school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "from_school_id", "to_school_id"),
        ForeignKeyConstraint(["from_school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        ForeignKeyConstraint(["to_school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        CheckConstraint("minutes BETWEEN 0 AND 1440", name="travel_time_range"),
        CheckConstraint("from_school_id <> to_school_id", name="travel_time_different_units"),
    )


class PublishedGrade(Base):
    __tablename__ = "published_grades"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    academic_year_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)  # DATA no calendario local (00:00, sem fuso)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    partial: Mapped[bool] = mapped_column(Boolean, nullable=False)
    justification: Mapped[str | None] = mapped_column(String(1000))
    published_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", "school_id"),
        ForeignKeyConstraint(["school_id", "tenant_id"], ["schools.id", "schools.tenant_id"]),
        ForeignKeyConstraint(["academic_year_id", "tenant_id", "school_id"], ["academic_years.id", "academic_years.tenant_id", "academic_years.school_id"]),
        ForeignKeyConstraint(["proposal_id", "tenant_id", "school_id"], ["grade_proposals.id", "grade_proposals.tenant_id", "grade_proposals.school_id"]),
        CheckConstraint("valid_from <= valid_to", name="published_valid_range"),
    )


class PublishedLesson(Base):
    __tablename__ = "published_lessons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    publication_id: Mapped[str] = mapped_column(String(36), nullable=False)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False)
    teacher_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    period_position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    students: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["publication_id", "tenant_id", "school_id"], ["published_grades.id", "published_grades.tenant_id", "published_grades.school_id"]),
        ForeignKeyConstraint(["class_id", "tenant_id", "school_id"], ["school_classes.id", "school_classes.tenant_id", "school_classes.school_id"]),
        ForeignKeyConstraint(["teacher_id", "tenant_id"], ["teachers.id", "teachers.tenant_id"]),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="published_lesson_day_range"),
        CheckConstraint("start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute", name="published_lesson_time_range"),
        UniqueConstraint("publication_id", "class_id", "weekday", "period_position"),
        Index("ix_published_teacher_day", "tenant_id", "teacher_id", "weekday"),
    )


class PublishedClass(Base):
    """Turmas pertencentes a uma versão publicada (inclui turma sem aulas)."""
    __tablename__ = 'published_classes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey('tenants.id'), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(String(36), nullable=False)
    publication_id: Mapped[str] = mapped_column(String(36), nullable=False)
    class_id: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (
        UniqueConstraint('publication_id','class_id'),
        ForeignKeyConstraint(['publication_id','tenant_id','school_id'], ['published_grades.id','published_grades.tenant_id','published_grades.school_id']),
        ForeignKeyConstraint(['class_id','tenant_id','school_id'], ['school_classes.id','school_classes.tenant_id','school_classes.school_id']),
    )
