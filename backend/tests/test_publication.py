"""Fase 4C: pré-validação API e regras puras. Publicação real depende de PostgreSQL."""
from datetime import date, datetime, timezone
from fastapi import HTTPException
import pytest
from test_app import context, tenant_with_admin, school, invitation, accept, login
from test_workflow import ready, proposals, create, coordinator
from test_planning import pfx
from app.publication import _check_published_conflicts, _validate_resources, _local_utc
from zoneinfo import ZoneInfo


def approved(client, slug='pub', partial=False):
    tid,sid,year,_,admin=ready(client,slug,lessons=2,possible=not partial)
    coord=coordinator(client,tid,sid,admin,f'coord-{slug}@example.com')
    p=create(client,tid,sid,year,coord)
    assert p.status_code==201,p.text
    pid=p.json()['id']
    sub=client.post(proposals(client,tid,sid)+f'/{pid}/submit',headers=coord,
        json={'justification':'Aguardando disponibilidade do professor.'} if partial else {})
    assert sub.status_code==200,sub.text
    admin=login(client,f'diretor-{slug}@example.com','Senha-forte-diretor-123')
    r=client.post(proposals(client,tid,sid)+f'/{pid}/approve',headers=admin,json={})
    assert r.status_code==200,r.text
    snap=client.get(proposals(client,tid,sid)+f'/{pid}').json()['snapshot']
    ids=list({a['class_id'] for a in snap['assignments']}|{p['class_id'] for p in snap['pending']})
    body={'valid_from':'2027-02-01','valid_to':'2027-02-05',
          'parts':[{'school_id':sid,'proposal_id':pid,'class_ids':ids}]}
    return tid,sid,year,admin,coord,body


def uri(tenant):return f'/api/tenants/{tenant}/publications'


def test_preflight_proposal_approved_and_sqlite_publish_denied(context):
    client,_=context
    tid,sid,year,admin,coord,body=approved(client,'preflight-ok')
    r=client.post(uri(tid)+'/preflight',json=body)
    assert r.status_code==200,r.text
    assert r.json()['eligible'] and r.json()['lessons']==2
    assert r.json()['dated_occurrences']==2
    r=client.post(uri(tid)+'/publish',headers=admin,json=body)
    assert r.status_code==503 and 'PostgreSQL' in r.text
    assert client.get(uri(tid)+'?school_id='+sid).json()==[]
    coord=login(client,'coord-preflight-ok@example.com','senha-super-segura-123')
    assert client.post(uri(tid)+'/preflight',json=body).status_code==403


def test_partial_exception_requires_reason(context):
    client,_=context
    tid,sid,_,admin,_,body=approved(client,'partial-pub',partial=True)
    assert client.post(uri(tid)+'/preflight',json=body).status_code==422
    body['exceptional_justification']='Publicar excepcionalmente para consulta, com pendências explícitas.'
    r=client.post(uri(tid)+'/preflight',json=body)
    assert r.status_code==200,r.text
    assert r.json()['partial'] and r.json()['lessons']==0


def test_permissions_and_earlier_than_one_year(context):
    client,_=context
    tid,sid,year,admin,_,body=approved(client,'range')
    body['valid_to']='2028-03-01'
    assert client.post(uri(tid)+'/preflight',json=body).status_code==422
    body['valid_to']='2027-02-05'
    body['parts'][0]['class_ids']*=2
    assert client.post(uri(tid)+'/preflight',json=body).status_code==422
    body['parts'][0]['class_ids']=list(set(body['parts'][0]['class_ids']))
    other,other_admin=tenant_with_admin(client,'other-pub')
    assert client.post(uri(tid)+'/preflight',json=body).status_code==403
    assert client.get(uri(tid)+'?school_id='+sid).status_code==403


def ev(teacher,school,start,end):
    return {'teacher_id':teacher,'school_id':school,'class_id':'class-'+school,
      'resource_id':None,'students':25,'start_utc':datetime(2027,2,1,start,tzinfo=timezone.utc),
      'end_utc':datetime(2027,2,1,end,tzinfo=timezone.utc)}


def test_shared_teacher_conflicts_and_travel_matrix():
    a=ev('paulo','centro',7,8)
    b=ev('paulo','norte',8,9)
    with pytest.raises(HTTPException, match='Tempo de deslocamento'):
        _check_published_conflicts([a,b],[],{}, {})
    with pytest.raises(HTTPException, match='Conflito de deslocamento'):
        _check_published_conflicts([a,b],[],{}, {('centro','norte'):20})
    c={'teacher_id':'paulo','school_id':'norte','class_id':'class-norte',
       'resource_id':None,'students':20,'start_utc':datetime(2027,2,1,8,30,tzinfo=timezone.utc),
       'end_utc':datetime(2027,2,1,9,30,tzinfo=timezone.utc)}
    _check_published_conflicts([a,c],[],{}, {('centro','norte'):20})
    with pytest.raises(HTTPException, match='Conflito de professor'):
        _check_published_conflicts([a,{**b,'start_utc':datetime(2027,2,1,7,30,tzinfo=timezone.utc)}],[],{}, {})


def test_room_capacity_simultaneous_and_timezone():
    from types import SimpleNamespace
    a=ev('a','centro',7,8);a['resource_id']='lab'
    b=ev('b','centro',7,8);b['resource_id']='lab'
    with pytest.raises(HTTPException,match='Capacidade'):
        _validate_resources({('centro','lab'):[a,b]}, {('centro','lab'):SimpleNamespace(max_groups=1,max_students=90)})
    with pytest.raises(HTTPException,match='Capacidade'):
        _validate_resources({('centro','lab'):[a,b]}, {('centro','lab'):SimpleNamespace(max_groups=2,max_students=40)})
    _validate_resources({('centro','lab'):[a,b]}, {('centro','lab'):SimpleNamespace(max_groups=2,max_students=50)})
    assert _local_utc(date(2027,2,1),420,ZoneInfo('America/Sao_Paulo')).hour==10


def test_stale_inputs_block_preflight(context):
    client,_=context
    tid,sid,year,admin,_,body=approved(client,'stale-publish')
    r=client.post(pfx(tid,sid)+'/subjects',headers=admin,json={'name':'Arte'})
    assert r.status_code==201,r.text
    r=client.post(uri(tid)+'/preflight',json=body)
    assert r.status_code==409 and 'desatualizada' in r.text


def test_travel_setting_requires_permission_in_both_schools(context):
    client,_=context
    tid,admin=tenant_with_admin(client,'travel')
    s1=school(client,tid,admin,'Centro')
    s2=school(client,tid,admin,'Norte')
    r=client.put(uri(tid)+f'/travel/{s1}',headers=admin,json={'destination_school_id':s2,'minutes':25})
    assert r.status_code==200,r.text
    token=invitation(client,tid,admin,'school_admin',s1,'school-travel@example.com')
    h=accept(client,tid,token)
    assert client.put(uri(tid)+f'/travel/{s1}',headers=h,json={'destination_school_id':s2,'minutes':0}).status_code==403


def test_published_class_vigence_blocks_another_version_even_without_lesson(context):
    """Uma classe sem aulas publicadas também reserva sua vigência."""
    from app.models import PublishedGrade, PublishedClass, GradeProposal
    client, Session=context
    tid,sid,year,admin,_,body=approved(client,'duplicate-vigence')
    with Session() as db:
        pub=PublishedGrade(tenant_id=tid,school_id=sid,academic_year_id=year,
            proposal_id=body['parts'][0]['proposal_id'],batch_id='batch-test',
            valid_from=datetime(2027,2,1),valid_to=datetime(2027,2,5),
            partial=False,published_by=db.query(GradeProposal).filter_by(id=body['parts'][0]['proposal_id']).one().created_by)
        db.add(pub);db.flush()
        db.add(PublishedClass(tenant_id=tid,school_id=sid,publication_id=pub.id,
                              class_id=body['parts'][0]['class_ids'][0]))
        db.commit()
        pub_id=pub.id
    r=client.post(uri(tid)+'/preflight',json=body)
    assert r.status_code==409 and 'vigência sobreposta' in r.text
    r=client.get(uri(tid)+'/'+pub_id)
    assert r.status_code==200 and r.json()['classes']==body['parts'][0]['class_ids']
    csv=client.get(uri(tid)+'/'+pub_id+'/export.csv')
    assert csv.status_code==200 and 'HORÁRIO OFICIAL' in csv.content.decode('utf-8-sig')
    body['valid_from']='2027-02-08';body['valid_to']='2027-02-12'
    assert client.post(uri(tid)+'/preflight',json=body).status_code==200
