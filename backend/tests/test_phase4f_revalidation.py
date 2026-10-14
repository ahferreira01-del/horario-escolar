"""Fase 4F: revalidação independente da cobertura e das aulas consecutivas.

Estes testes usam SQLite APENAS para as regras da pré-publicação. Não são
prova de RLS, locks ou publicação real em PostgreSQL.
"""
from copy import deepcopy
from sqlalchemy import select
from app.models import GradeProposal, TeachingAssignment
from app.workflow import source_fingerprint
from test_app import context
from test_publication import approved, uri


def test_declared_complete_cannot_omit_a_mandatory_lesson(context):
    client, Session = context
    tenant, school, year, _, _, payload = approved(client, 'fase4f-coverage')
    pid = payload['parts'][0]['proposal_id']
    with Session() as db:
        proposal = db.get(GradeProposal, pid)
        snap = deepcopy(proposal.snapshot)
        assert snap['result'] == 'complete' and len(snap['assignments']) == 2
        snap['assignments'].pop()
        # Mesmo se os indicadores declarados forem falsificados, a conferência
        # da carga real precisa bloquear o salvamento da versão oficial.
        snap['total_assigned'] = 2
        proposal.snapshot = snap
        db.commit()
    response = client.post(uri(tenant) + '/preflight', json=payload)
    assert response.status_code == 409, response.text
    assert 'Cobertura' in response.text


def test_declared_partial_requires_precise_pending_entries(context):
    client, Session = context
    tenant, school, year, _, _, payload = approved(client, 'fase4f-forgedpartial', partial=True)
    pid = payload['parts'][0]['proposal_id']
    payload['exceptional_justification'] = 'Pendências justificadas.'
    with Session() as db:
        proposal = db.get(GradeProposal, pid)
        snap = deepcopy(proposal.snapshot)
        assert snap['result'] == 'partial' and snap['pending']
        snap['pending'][0]['missing'] += 1
        proposal.snapshot = snap
        db.commit()
    response = client.post(uri(tenant) + '/preflight', json=payload)
    assert response.status_code == 409, response.text
    assert 'Cobertura' in response.text


def test_max_one_consecutive_is_enforced_at_publication_preflight(context):
    client, Session = context
    tenant, school, year, _, _, payload = approved(client, 'fase4f-maxone')
    pid = payload['parts'][0]['proposal_id']
    with Session() as db:
        assignment = db.scalar(select(TeachingAssignment).where(
            TeachingAssignment.tenant_id == tenant))
        assert assignment and assignment.max_consecutive == 2
        assignment.max_consecutive = 1
        db.flush()
        proposal = db.get(GradeProposal, pid)
        snap = deepcopy(proposal.snapshot)
        assert len(snap['assignments']) == 2
        for period, lesson in enumerate(snap['assignments'], start=1):
            lesson.update(day='Seg', order=period,
                          start='07:10' if period == 1 else '07:55',
                          end='07:55' if period == 1 else '08:40')
        proposal.snapshot = snap
        proposal.source_hash = source_fingerprint(db, tenant, school, year)
        db.commit()
    response = client.post(uri(tenant) + '/preflight', json=payload)
    assert response.status_code == 409, response.text
    assert 'uma aula consecutiva' in response.text
