"""Fase 4A — propostas imutáveis de grade, revisão, segregação de funções e exportação.

NÃO publica horários, NÃO reserva recursos e NÃO promete verificação entre unidades.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    User, GradeProposal, SchoolClass, ClassPeriod, TeachingAssignment, Subject,
    Availability, Teacher, TeacherSchool, TeacherLimit, TeacherWeeklyLimit,
    SchoolResource, ResourceAvailability, SchoolTravelTime, School, AcademicYear, utcnow,
)
from .planning import scope, year_in, build_preview, audit
from .security import current_user, require_csrf, authorize

router = APIRouter(prefix="/api/tenants/{tenant_id}/schools/{school_id}", tags=["Propostas de grade (sem publicação)"])


class ProposalNew(BaseModel):
    academic_year_id: str
    profile: str = Field(default="equilibrado", pattern=r"^(equilibrado|menos_janelas|menos_dias|personalizado)$")
    weights: dict[str, int] | None = None
    time_limit: int = Field(default=8, ge=1, le=15)


class ProposalSubmit(BaseModel):
    justification: str | None = Field(default=None, max_length=1000)


class ProposalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def source_fingerprint(db: Session, tenant_id: str, school_id: str, year_id: str) -> str:
    """Assinatura de entradas escolares e disponibilidades compartilhadas.

    Abrange registros da escola, as cargas do ano e informações globais dos
    professores vinculados. Não inclui versão nem auditoria (são mutáveis).
    """
    cls_ids = db.scalars(select(SchoolClass.id).where(
        SchoolClass.tenant_id == tenant_id, SchoolClass.school_id == school_id,
        SchoolClass.academic_year_id == year_id)).all()
    assignment_rows = db.scalars(select(TeachingAssignment).where(
        TeachingAssignment.tenant_id == tenant_id, TeachingAssignment.school_id == school_id,
        TeachingAssignment.class_id.in_(cls_ids))).all()
    teacher_ids = sorted({a.teacher_id for a in assignment_rows})
    resource_ids = sorted({a.resource_id for a in assignment_rows if a.resource_id})
    # Deslocamentos de professores compartilhados também fazem parte das
    # entradas da geração: alterar minutos torna propostas antigas obsoletas.
    linked_school_ids = sorted(set(db.scalars(select(TeacherSchool.school_id).where(
        TeacherSchool.tenant_id == tenant_id,
        TeacherSchool.teacher_id.in_(teacher_ids))).all()))
    parts = [
        (School, [School.tenant_id == tenant_id, School.id == school_id]),
        (AcademicYear, [AcademicYear.tenant_id == tenant_id, AcademicYear.school_id == school_id, AcademicYear.id == year_id]),
        (SchoolClass, [SchoolClass.tenant_id == tenant_id, SchoolClass.school_id == school_id, SchoolClass.academic_year_id == year_id]),
        (ClassPeriod, [ClassPeriod.tenant_id == tenant_id, ClassPeriod.school_id == school_id, ClassPeriod.class_id.in_(cls_ids)]),
        (TeachingAssignment, [TeachingAssignment.tenant_id == tenant_id, TeachingAssignment.school_id == school_id, TeachingAssignment.class_id.in_(cls_ids)]),
        (Subject, [Subject.tenant_id == tenant_id, Subject.school_id == school_id]),
        (Teacher, [Teacher.tenant_id == tenant_id, Teacher.id.in_(teacher_ids)]),
        (TeacherSchool, [TeacherSchool.tenant_id == tenant_id, TeacherSchool.teacher_id.in_(teacher_ids)]),
        (SchoolTravelTime, [SchoolTravelTime.tenant_id == tenant_id,
                            SchoolTravelTime.from_school_id.in_(linked_school_ids),
                            SchoolTravelTime.to_school_id.in_(linked_school_ids)]),
        (Availability, [Availability.tenant_id == tenant_id, Availability.teacher_id.in_(teacher_ids)]),
        (TeacherLimit, [TeacherLimit.tenant_id == tenant_id, TeacherLimit.teacher_id.in_(teacher_ids)]),
        (TeacherWeeklyLimit, [TeacherWeeklyLimit.tenant_id == tenant_id, TeacherWeeklyLimit.teacher_id.in_(teacher_ids)]),
        (SchoolResource, [SchoolResource.tenant_id == tenant_id, SchoolResource.school_id == school_id, SchoolResource.id.in_(resource_ids)]),
        (ResourceAvailability, [ResourceAvailability.tenant_id == tenant_id, ResourceAvailability.school_id == school_id, ResourceAvailability.resource_id.in_(resource_ids)]),
    ]
    state = {}
    for model, conditions in parts:
        rows = db.scalars(select(model).where(*conditions)).all()
        fields = [col.key for col in model.__table__.columns]
        values = [{key: getattr(row, key) for key in fields} for row in rows]
        state[model.__tablename__] = sorted(values, key=lambda obj: json.dumps(obj, sort_keys=True, default=str))
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def in_scope(db, tenant_id: str, school_id: str, proposal_id: str, lock=False):
    stmt = select(GradeProposal).where(GradeProposal.id == proposal_id,
        GradeProposal.tenant_id == tenant_id, GradeProposal.school_id == school_id)
    if lock:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if not obj:
        raise HTTPException(404, "Proposta não encontrada nesta escola.")
    return obj


def assert_fresh(db, proposal):
    if proposal.source_hash != source_fingerprint(db, proposal.tenant_id, proposal.school_id, proposal.academic_year_id):
        raise HTTPException(409, "Os dados escolares mudaram após o cálculo. Gere uma nova proposta.")


def overview(p):
    snapshot = p.snapshot
    return {"id": p.id, "academic_year_id": p.academic_year_id,
            "status": p.status, "created_by": p.created_by,
            "submitted_by": p.submitted_by, "decided_by": p.decided_by,
            "created_at": p.created_at.isoformat(),
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            "justification": p.justification, "decision_note": p.decision_note,
            "result": snapshot.get("result"), "solver_status": snapshot.get("solver_status"),
            "total_assigned": snapshot.get("total_assigned"),
            "total_required": snapshot.get("total_required"),
            "pending_count": len(snapshot.get("pending", [])),
            "published": False}


@router.get("/proposals")
def list_proposals(tenant_id: str, school_id: str, academic_year_id: str,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    scope(db, user, tenant_id, school_id, "grades.read")
    year_in(db, tenant_id, school_id, academic_year_id)
    rows = db.scalars(select(GradeProposal).where(
        GradeProposal.tenant_id == tenant_id, GradeProposal.school_id == school_id,
        GradeProposal.academic_year_id == academic_year_id
    ).order_by(GradeProposal.created_at.desc()).limit(100)).all()
    return [overview(p) for p in rows]


@router.post("/proposals", status_code=201)
def create_proposal(tenant_id: str, school_id: str, data: ProposalNew, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_csrf(request)
    scope(db, user, tenant_id, school_id, "grades.create", write=True)
    year_in(db, tenant_id, school_id, data.academic_year_id)
    fingerprint = source_fingerprint(db, tenant_id, school_id, data.academic_year_id)
    result = build_preview(db, tenant_id, school_id, data.academic_year_id,
                           data.profile, data.weights, data.time_limit)
    if result.get("result") not in ("complete", "partial") or result.get("conflicts") != 0:
        raise HTTPException(422, "O otimizador não retornou uma prévia válida verificável.")
    if fingerprint != source_fingerprint(db, tenant_id, school_id, data.academic_year_id):
        raise HTTPException(409, "Dados alterados durante a geração. Tente novamente.")
    obj = GradeProposal(tenant_id=tenant_id, school_id=school_id,
                        academic_year_id=data.academic_year_id, created_by=user.id,
                        source_hash=fingerprint, snapshot=result)
    db.add(obj); db.flush()
    audit(db, user, tenant_id, "grade.proposal.created", "grade_proposal", obj.id,
          school_id=school_id, coverage=result["result"], solver_status=result.get("solver_status"))
    db.commit()
    return overview(obj)


@router.get("/proposals/{proposal_id}")
def get_proposal(tenant_id: str, school_id: str, proposal_id: str,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    scope(db, user, tenant_id, school_id, "grades.read")
    obj = in_scope(db, tenant_id, school_id, proposal_id)
    return {**overview(obj), "snapshot": obj.snapshot}


@router.post("/proposals/{proposal_id}/submit")
def submit_proposal(tenant_id: str, school_id: str, proposal_id: str,
                    data: ProposalSubmit, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_csrf(request)
    scope(db, user, tenant_id, school_id, "grades.submit", write=True)
    obj = in_scope(db, tenant_id, school_id, proposal_id, lock=True)
    if obj.status != "draft":
        raise HTTPException(409, "Somente rascunhos podem ser enviados para revisão.")
    assert_fresh(db, obj)
    if obj.snapshot.get("pending") and not (data.justification and data.justification.strip()):
        raise HTTPException(422, "Proposta parcial exige justificativa para revisão.")
    obj.status = "submitted"
    obj.justification = data.justification.strip() if data.justification else None
    obj.submitted_by = user.id
    obj.submitted_at = utcnow()
    audit(db, user, tenant_id, "grade.proposal.submitted", "grade_proposal", obj.id,
          school_id=school_id, partial=bool(obj.snapshot.get("pending")))
    db.commit()
    return overview(obj)


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(tenant_id: str, school_id: str, proposal_id: str,
                     data: ProposalDecision, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_csrf(request)
    scope(db, user, tenant_id, school_id, "grades.approve", write=True)
    obj = in_scope(db, tenant_id, school_id, proposal_id, lock=True)
    if obj.status != "submitted":
        raise HTTPException(409, "Somente propostas submetidas podem ser aprovadas.")
    if user.id == obj.created_by or user.id == obj.submitted_by:
        raise HTTPException(403, "O criador ou remetente não pode aprovar a própria grade.")
    if obj.snapshot.get("pending"):
        authorize(db, user, tenant_id, "grades.approve_partial", school_id=school_id, write=True)
        if not obj.justification:
            raise HTTPException(422, "Proposta parcial sem justificativa.")
    assert_fresh(db, obj)
    obj.status = "approved"
    obj.decided_by = user.id
    obj.decided_at = utcnow()
    obj.decision_note = data.note.strip() if data.note else None
    audit(db, user, tenant_id, "grade.proposal.approved", "grade_proposal", obj.id,
          school_id=school_id, partial=bool(obj.snapshot.get("pending")))
    db.commit()
    return overview(obj)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(tenant_id: str, school_id: str, proposal_id: str,
                    data: ProposalDecision, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_csrf(request)
    scope(db, user, tenant_id, school_id, "grades.approve", write=True)
    obj = in_scope(db, tenant_id, school_id, proposal_id, lock=True)
    if obj.status != "submitted":
        raise HTTPException(409, "Somente propostas submetidas podem ser rejeitadas.")
    if not data.note or not data.note.strip():
        raise HTTPException(422, "Informe a justificativa da rejeição.")
    obj.status = "rejected"
    obj.decided_by = user.id
    obj.decided_at = utcnow()
    obj.decision_note = data.note.strip()
    audit(db, user, tenant_id, "grade.proposal.rejected", "grade_proposal", obj.id, school_id=school_id)
    db.commit()
    return overview(obj)


def safe_csv(value):
    """Neutraliza fórmulas em CSV, inclusive após espaços iniciais."""
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@router.get("/proposals/{proposal_id}/export.csv")
def export_proposal_csv(tenant_id: str, school_id: str, proposal_id: str,
                        db: Session = Depends(get_db), user: User = Depends(current_user)):
    scope(db, user, tenant_id, school_id, "grades.read")
    obj = in_scope(db, tenant_id, school_id, proposal_id)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["Turma", "Dia", "Aula", "Início", "Fim", "Disciplina", "Professor", "Situação"])
    for row in obj.snapshot.get("assignments", []):
        writer.writerow([safe_csv(row.get(key)) for key in
            ("class_name", "day", "order", "start", "end", "subject", "teacher_name")]
            + ["PROPOSTA NÃO PUBLICADA"])
    writer.writerow([])
    writer.writerow(["ESTADO", obj.status, "Prévia não oficial"])
    for row in obj.snapshot.get("pending", []):
        writer.writerow(["PENDÊNCIA", safe_csv(row.get("class_name")),
                         safe_csv(row.get("subject")), safe_csv(row.get("teacher_name")),
                         safe_csv(row.get("missing")), safe_csv(row.get("reason"))])
    result = "\ufeff" + buf.getvalue()
    return Response(content=result.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="proposta-{obj.id}.csv"',
                             "X-Content-Type-Options": "nosniff"})
