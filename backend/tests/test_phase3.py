"""Fase 3: cenários executáveis da API. SQLite somente para desenvolvimento."""
from test_planning import (pfx, configure, set_periods, teacher, availability, assign)
from test_app import tenant_with_admin, school, invitation, accept, context


def setup_single(client, suffix='extra'):
    t,h=tenant_with_admin(client,suffix)
    s=school(client,t,h)
    base=pfx(t,s)
    year,subject,cls=configure(client,t,s,h)
    assert set_periods(client,base,cls,h).status_code==200
    p=teacher(client,t,s,h)
    assert availability(client,t,p,h).status_code==200
    return t,h,s,base,year,subject,cls,p


def test_minutes_exact_and_configurable_tolerance(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'minutos')
    endpoint=b+f'/classes/{cls}/assignments'
    invalid=client.post(endpoint,headers=h,json={"subject_id":sub,"teacher_id":p,"load_mode":"minutes",
                                                  "lessons":1,"target_minutes":250,"min_minutes":280,"max_minutes":300})
    assert invalid.status_code==422
    exact=client.post(endpoint,headers=h,json={"subject_id":sub,"teacher_id":p,"load_mode":"minutes",
                                                   "lessons":1,"target_minutes":250})
    assert exact.status_code==201, exact.text
    res=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6})
    assert res.status_code==200,res.text
    result=res.json()
    assert result['result']=='partial'
    assert result['required_minutes']==250 and result['total_assigned_minutes']==225
    assert result['pending'][0]['missing']==25 and result['pending'][0]['unit']=='minutes'
    client.delete(endpoint+'/'+exact.json()['id'],headers=h)
    tolerated=client.post(endpoint,headers=h,json={"subject_id":sub,"teacher_id":p,"load_mode":"minutes",
                                                       "lessons":1,"target_minutes":250,"min_minutes":250,"max_minutes":275})
    assert tolerated.status_code==201,tolerated.text
    res=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6})
    assert res.status_code==200,res.text
    result=res.json()
    assert result['result']=='complete' and result['total_assigned_minutes']==270
    assert result['demand_coverage'][0]['minutes_scheduled']==270


def test_teacher_daily_and_weekly_limits_enforced(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'limites')
    assert assign(client,b,cls,sub,p,h,4).status_code==201
    endpoint=b+f'/teacher-limits/{p}'
    updated=client.put(endpoint,headers=h,json={"weekly":2,"daily":{"0":1,"1":1,"2":0,"3":0,"4":0}})
    assert updated.status_code==200,updated.text
    read=client.get(endpoint)
    assert read.status_code==200 and read.json()['weekly']==2
    result=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6}).json()
    assert result['result']=='partial' and result['total_assigned']==2
    assert sum(x['missing'] for x in result['pending'])==2
    assert all(x['day'] in ('Seg','Ter') for x in result['assignments'])
    assert all(sum(a['day']==d for a in result['assignments'])<=1 for d in ('Seg','Ter'))


def test_resource_student_and_group_capacity(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'laboratorio')
    r=client.post(b+'/resources',headers=h,json={"name":"Laboratório","max_groups":1,"max_students":30})
    assert r.status_code==201,r.text
    rid=r.json()['id']
    assert client.put(b+f'/resources/{rid}/availability',headers=h,
        json={'intervals':[{'weekday':i,'start':'07:00','end':'11:00'} for i in range(5)]}).status_code==200
    assert client.post(b+f'/classes/{cls}/assignments',headers=h,
        json={'subject_id':sub,'teacher_id':p,'lessons':2,'resource_id':rid}).status_code==201
    # The resource holds <=30 students, so the class with 25 works.
    result=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6}).json()
    assert result['result']=='complete' and all(a['resource_id']==rid for a in result['assignments'])
    # A separate class with 35 students may not use it, even with an available teacher.
    second=client.post(b+'/classes',headers=h,json={'academic_year_id':y,'name':'7º B','students':35}).json()['id']
    assert set_periods(client,b,second,h).status_code==200
    other=teacher(client,t,s,h,'Outro')
    assert availability(client,t,other,h).status_code==200
    assert client.post(b+f'/classes/{second}/assignments',headers=h,
        json={'subject_id':sub,'teacher_id':other,'lessons':2,'resource_id':rid}).status_code==201
    result=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6}).json()
    assert result['total_assigned']==2 and result['result']=='partial'
    assert any(x['teacher']==other and x['missing']==2 for x in result['pending'])


def test_resource_and_limit_isolation(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'isolamento3')
    other=school(client,t,h,'Outra')
    foreign=pfx(t,other)
    resource=client.post(b+'/resources',headers=h,json={'name':'Quadra','max_groups':2,'max_students':90}).json()['id']
    assert client.put(foreign+f'/resources/{resource}/availability',headers=h,
        json={'intervals':[{'weekday':0,'start':'07:00','end':'11:00'}]}).status_code==404
    assert client.post(foreign+f'/classes/{cls}/assignments',headers=h,
        json={'subject_id':sub,'teacher_id':p,'lessons':1,'resource_id':resource}).status_code==404
    token=invitation(client,t,h,'school_admin',s,'school-admin-limits@example.com')
    sub_h=accept(client,t,token)
    assert client.put(b+f'/teacher-limits/{p}',headers=sub_h,
        json={'weekly':3,'daily':{'0':2}}).status_code==403
    other_t,other_h=tenant_with_admin(client,'outro-tenant3')
    other_s=school(client,other_t,other_h)
    assert client.get(b+'/resources').status_code==403
    assert client.post(b+'/resources',headers=other_h,json={'name':'Tentar','max_groups':1,'max_students':40}).status_code==403


def test_missing_or_invalid_resource_availability_not_silently_ignored(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'recurso-sem-faixa')
    r=client.post(b+'/resources',headers=h,json={'name':'Sala Especial','max_groups':1,'max_students':30}).json()['id']
    assert client.post(b+f'/classes/{cls}/assignments',headers=h,
        json={'subject_id':sub,'teacher_id':p,'lessons':2,'resource_id':r}).status_code==201
    result=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':6}).json()
    assert result['total_assigned']==0
    assert 'Nenhum período' in result['pending'][0]['reason']
    bad=client.put(b+f'/resources/{r}/availability',headers=h,json={'intervals':[
        {'weekday':0,'start':'08:00','end':'10:00'},
        {'weekday':0,'start':'09:00','end':'11:00'}]})
    assert bad.status_code==422


def test_resource_max_groups_even_when_students_fit(context):
    client,_=context
    t,h,s,b,y,sub,cls,p=setup_single(client,'grupo-capacidade')
    fixed=[{'weekday':0,'position':1,'start':'07:10','end':'07:55','shift':'manha'}]
    assert client.put(b+f'/classes/{cls}/periods',headers=h,json={'periods':fixed}).status_code==200
    cls2=client.post(b+'/classes',headers=h,json={'academic_year_id':y,'name':'7º C','students':20}).json()['id']
    assert client.put(b+f'/classes/{cls2}/periods',headers=h,json={'periods':fixed}).status_code==200
    p2=teacher(client,t,s,h,'Maria')
    assert availability(client,t,p2,h).status_code==200
    r=client.post(b+'/resources',headers=h,json={'name':'Quadra','max_groups':1,'max_students':100}).json()['id']
    assert client.put(b+f'/resources/{r}/availability',headers=h,json={'intervals':[
        {'weekday':0,'start':'07:00','end':'09:00'}]}).status_code==200
    for cid,teacher_id in [(cls,p),(cls2,p2)]:
        assert client.post(b+f'/classes/{cid}/assignments',headers=h,
            json={'subject_id':sub,'teacher_id':teacher_id,'lessons':1,'resource_id':r}).status_code==201
    result=client.post(b+'/preview',headers=h,json={'academic_year_id':y,'time_limit':5}).json()
    assert result['result']=='partial' and result['total_assigned']==1
    assert len(result['pending'])==1 and result['pending'][0]['missing']==1
