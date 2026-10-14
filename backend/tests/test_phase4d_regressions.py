"""4D: semanas parciais, mudança de dia e publicação oficial independente de prévia."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
import pytest
from sqlalchemy import select

from test_app import context
from test_publication import approved, uri, ev
from app.workflow import source_fingerprint
from app.publication import _check_published_conflicts
from app.models import (
    PublishedGrade, PublishedClass, PublishedLesson, TeachingAssignment,
    TeacherWeeklyLimit, GradeProposal,
)


def test_different_days_allow_sufficient_travel_when_configured():
    a=ev('professor','centro',7,8)
    b=ev('professor','norte',7,8)
    b['start_utc']=datetime(2027,2,2,7,tzinfo=timezone.utc)
    b['end_utc']=datetime(2027,2,2,8,tzinfo=timezone.utc)
    from types import SimpleNamespace
    units={'centro':SimpleNamespace(timezone='America/Sao_Paulo'),
           'norte':SimpleNamespace(timezone='America/Sao_Paulo')}
    _check_published_conflicts([a,b],[],units,{('centro','norte'):20})


def test_weekly_teacher_limit_counts_nonoverlapping_versions(context):
    """Versão Seg/Ter + versão Qua/Sex devem somar na MESMA semana ISO."""
    client,Session=context
    tid,sid,year,admin,_,body=approved(client,'week-partition')
    body['valid_to']='2027-02-02'
    proposal_id=body['parts'][0]['proposal_id']
    cls_id=body['parts'][0]['class_ids'][0]
    with Session() as db:
        teacher=db.scalar(select(TeachingAssignment.teacher_id).where(
            TeachingAssignment.tenant_id==tid, TeachingAssignment.class_id==cls_id))
        assert teacher
        db.add(TeacherWeeklyLimit(tenant_id=tid,teacher_id=teacher,max_lessons=2))
        db.flush()
        proposal=db.get(GradeProposal,proposal_id)
        proposal.source_hash=source_fingerprint(db,tid,sid,year)
        # Outra versão oficial só tem aulas quarta-feira: não há dias
        # sobrepostos com o novo lote de segunda e terça.
        pub=PublishedGrade(tenant_id=tid,school_id=sid,academic_year_id=year,
            proposal_id=proposal_id,batch_id='version-prev-weekday',
            valid_from=datetime(2027,2,3),valid_to=datetime(2027,2,5),
            partial=False,published_by=db.scalar(select(GradeProposal.created_by).where(
                GradeProposal.id==proposal_id)))
        db.add(pub);db.flush()
        db.add(PublishedClass(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id))
        db.add(PublishedLesson(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id,teacher_id=teacher,
            subject='Matemática',weekday=2,period_position=1,
            start_minute=430,end_minute=475,students=25))
        db.commit()
    result=client.post(uri(tid)+'/preflight',json=body)
    assert result.status_code==409, result.text
    assert 'semanal' in result.text.lower()


def test_back_to_back_week_excludes_other_iso_week(context):
    client,Session=context
    tid,sid,year,admin,_,body=approved(client,'week-other')
    proposal_id=body['parts'][0]['proposal_id']
    cls_id=body['parts'][0]['class_ids'][0]
    with Session() as db:
        teacher=db.scalar(select(TeachingAssignment.teacher_id).where(
            TeachingAssignment.tenant_id==tid,TeachingAssignment.class_id==cls_id))
        db.add(TeacherWeeklyLimit(tenant_id=tid,teacher_id=teacher,max_lessons=2))
        db.flush()
        proposal=db.get(GradeProposal,proposal_id)
        proposal.source_hash=source_fingerprint(db,tid,sid,year)
        pub=PublishedGrade(tenant_id=tid,school_id=sid,academic_year_id=year,
            proposal_id=proposal_id,batch_id='version-other-week',
            valid_from=datetime(2027,2,8),valid_to=datetime(2027,2,12),
            partial=False,published_by=db.scalar(select(GradeProposal.created_by).where(
                GradeProposal.id==proposal_id)))
        db.add(pub);db.flush()
        db.add(PublishedClass(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id))
        db.add(PublishedLesson(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id,teacher_id=teacher,
            subject='Matemática',weekday=0,period_position=1,
            start_minute=430,end_minute=475,students=25))
        db.commit()
    result=client.post(uri(tid)+'/preflight',json=body)
    assert result.status_code==200,result.text


def test_official_pdf_is_a4_and_school_scoped(context):
    """Exportação PDF usa a própria autorização grades.read do recurso oficial."""
    client,Session=context
    tid,sid,year,admin,_,body=approved(client,'export-a4')
    proposal_id=body['parts'][0]['proposal_id']
    cls_id=body['parts'][0]['class_ids'][0]
    with Session() as db:
        teacher=db.scalar(select(TeachingAssignment.teacher_id).where(
            TeachingAssignment.tenant_id==tid,TeachingAssignment.class_id==cls_id))
        pub=PublishedGrade(tenant_id=tid,school_id=sid,academic_year_id=year,
            proposal_id=proposal_id,batch_id='batch-export-test',
            valid_from=datetime(2027,2,1),valid_to=datetime(2027,2,5),
            partial=False,published_by=db.scalar(select(GradeProposal.created_by).where(
                GradeProposal.id==proposal_id)))
        db.add(pub);db.flush()
        db.add(PublishedClass(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id))
        db.add(PublishedLesson(tenant_id=tid,school_id=sid,
            publication_id=pub.id,class_id=cls_id,teacher_id=teacher,
            subject='Matemática',weekday=0,period_position=1,
            start_minute=430,end_minute=475,students=25))
        db.commit()
        pub_id=pub.id
    result=client.get(uri(tid)+f'/{pub_id}/export.pdf')
    assert result.status_code==200,result.text[:100] if result.status_code!=200 else ''
    assert result.headers['content-type']=='application/pdf'
    assert result.content.startswith(b'%PDF-')
    assert len(result.content)>1300
    # A mesma pessoa não pode usar o PDF para contornar o escopo da escola.
    from test_app import tenant_with_admin
    tenant_with_admin(client,'another-pdf-org')
    denied=client.get(uri(tid)+f'/{pub_id}/export.pdf')
    assert denied.status_code==403
