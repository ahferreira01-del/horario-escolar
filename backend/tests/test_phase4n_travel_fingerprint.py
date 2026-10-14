"""Fase 4N: um novo tempo de deslocamento invalida propostas antigas.

A assinatura agora inclui os trajetos direcionais entre as unidades às quais
os professores envolvidos no ano letivo estão vinculados.
"""
from sqlalchemy import select

from test_app import context, school
from test_workflow import ready, proposals, create
from app.models import TeacherSchool, SchoolTravelTime
from app.workflow import source_fingerprint


def test_shared_teacher_travel_change_invalidates_saved_proposal(context):
    client, Session = context
    tenant_id, origin_id, year_id, teacher_id, admin = ready(client, '4n-travel')
    destination_id = school(client, tenant_id, admin, 'Escola Norte')

    # O professor integra as duas escolas; antes da geração, as duas
    # direções são explícitas e válidas.
    with Session() as db:
        db.add(TeacherSchool(
            tenant_id=tenant_id, teacher_id=teacher_id, school_id=destination_id))
        db.add_all([
            SchoolTravelTime(
                tenant_id=tenant_id, from_school_id=origin_id,
                to_school_id=destination_id, minutes=25),
            SchoolTravelTime(
                tenant_id=tenant_id, from_school_id=destination_id,
                to_school_id=origin_id, minutes=30),
        ])
        db.commit()

    with Session() as db:
        baseline=source_fingerprint(db,tenant_id,origin_id,year_id)

    saved=create(client,tenant_id,origin_id,year_id,admin)
    assert saved.status_code==201,saved.text
    proposal_id=saved.json()['id']

    # Direção Centro -> Norte alterada depois da geração da proposta.
    response=client.put(
        f'/api/tenants/{tenant_id}/publications/travel/{origin_id}',
        headers=admin,
        json={'destination_school_id':destination_id, 'minutes':65})
    assert response.status_code==200,response.text

    with Session() as db:
        updated=source_fingerprint(db,tenant_id,origin_id,year_id)
        assert updated!=baseline

    rejected=client.post(
        proposals(client,tenant_id,origin_id)+f'/{proposal_id}/submit',
        headers=admin,json={})
    assert rejected.status_code==409,rejected.text
    assert 'mudaram' in rejected.text.lower() or 'nova proposta' in rejected.text.lower()


def test_unrelated_teacher_travel_does_not_invalidate_proposal(context):
    client,Session=context
    tenant_id,origin_id,year_id,teacher_id,admin=ready(client,'4n-unrelated')
    other_a=school(client,tenant_id,admin,'Outra A')
    other_b=school(client,tenant_id,admin,'Outra B')
    with Session() as db:
        baseline=source_fingerprint(db,tenant_id,origin_id,year_id)
    response=client.put(
        f'/api/tenants/{tenant_id}/publications/travel/{other_a}',
        headers=admin,
        json={'destination_school_id':other_b,'minutes':45})
    assert response.status_code==200,response.text
    with Session() as db:
        assert source_fingerprint(db,tenant_id,origin_id,year_id)==baseline
