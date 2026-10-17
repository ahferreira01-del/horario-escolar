"""Integração API da Fase 2. Executa em SQLite; PostgreSQL/RLS requer ensaio separado."""
from test_app import context, tenant_with_admin, school, invitation, accept, login
from app.database import Base


def pfx(tenant,school_id): return f"/api/tenants/{tenant}/schools/{school_id}"

def configure(client,tenant,school_id,h):
    base=pfx(tenant,school_id)
    y=client.post(base+"/years",headers=h,json={"year":2027,"label":"Ano letivo 2027"})
    assert y.status_code==201, y.text
    sub=client.post(base+"/subjects",headers=h,json={"name":"Matemática"})
    assert sub.status_code==201,sub.text
    cls=client.post(base+"/classes",headers=h,json={"academic_year_id":y.json()["id"],"name":"6º Ano A","students":25})
    assert cls.status_code==201,cls.text
    return y.json()["id"],sub.json()["id"],cls.json()["id"]

def set_periods(client,base,cls,h):
    periods=[{"weekday":day,"position":n,"start":start,"end":end,"shift":"manha"}
             for day in (0,1,2,3,4) for n,start,end in [(1,"07:10","07:55"),(2,"07:55","08:40"),(3,"09:00","09:45"),(4,"09:55","10:40")]]
    return client.put(base+f"/classes/{cls}/periods",headers=h,json={"periods":periods})

def assign(client,base,cls,subject,teacher,h,lessons=3):
    return client.post(base+f"/classes/{cls}/assignments",headers=h,json={"subject_id":subject,"teacher_id":teacher,"lessons":lessons,"max_consecutive":2})

def teacher(client,tenant,school_id,h,name="Paulo"):
    r=client.post(f"/api/tenants/{tenant}/teachers",headers=h,json={"name":name,"school_id":school_id})
    assert r.status_code==201,r.text
    return r.json()["id"]

def availability(client,tenant,tid,h,start="07:00",end="11:00"):
    return client.put(f"/api/tenants/{tenant}/teachers/{tid}/availability",headers=h,json={"intervals":[{"weekday":i,"start":start,"end":end} for i in range(5)]})


def test_end_to_end_preview_complete_and_teacher_split(context):
    client,_=context
    tenant_id,h=tenant_with_admin(client,"escola")
    sid=school(client,tenant_id,h)
    base=pfx(tenant_id,sid)
    year,sub,cls=configure(client,tenant_id,sid,h)
    assert set_periods(client,base,cls,h).status_code==200
    paulo=teacher(client,tenant_id,sid,h)
    maria=teacher(client,tenant_id,sid,h,"Maria")
    assert availability(client,tenant_id,paulo,h).status_code==200
    assert availability(client,tenant_id,maria,h).status_code==200
    assert assign(client,base,cls,sub,paulo,h,3).status_code==201
    assert assign(client,base,cls,sub,maria,h,2).status_code==201
    r=client.post(base+"/preview",headers=h,json={"academic_year_id":year,"profile":"equilibrado","time_limit":5})
    assert r.status_code==200,r.text
    v=r.json(); assert v["total_assigned"]==5 and v["total_required"]==5 and v["result"]=="complete"
    assert v["preview_only"] is True and v["conflicts"]==0
    from collections import Counter
    assert Counter(x["teacher"] for x in v["assignments"])=={paulo:3,maria:2}
    # No three consecutive Mathematics classes even across a recess.
    by_day={d:[] for d in ("Seg","Ter","Qua","Qui","Sex")}
    for a in v["assignments"]: by_day[a["day"]].append(a["order"])
    assert all(not {1,2,3}.issubset(set(orders)) and not {2,3,4}.issubset(set(orders)) for orders in by_day.values())


def test_exact_availability_yields_partial_and_no_fake_period(context):
    client,_=context
    tenant_id,h=tenant_with_admin(client,"parcial")
    sid=school(client,tenant_id,h)
    base=pfx(tenant_id,sid)
    year,sub,cls=configure(client,tenant_id,sid,h)
    assert set_periods(client,base,cls,h).status_code==200
    prof=teacher(client,tenant_id,sid,h)
    assert availability(client,tenant_id,prof,h,"10:45","12:00").status_code==200
    assert assign(client,base,cls,sub,prof,h,2).status_code==201
    r=client.post(base+"/preview",headers=h,json={"academic_year_id":year,"time_limit":5})
    assert r.status_code==200,r.text
    v=r.json();assert v["result"]=="partial" and v["total_assigned"]==0 and sum(p["missing"] for p in v["pending"])==2
    assert "Nenhum período" in v["pending"][0]["reason"]


def test_reject_cross_school_foreign_year_subject_teacher(context):
    client,_=context
    tenant_id,h=tenant_with_admin(client,"escopos")
    s1=school(client,tenant_id,h,"Centro");s2=school(client,tenant_id,h,"Norte")
    b1=pfx(tenant_id,s1);b2=pfx(tenant_id,s2)
    y,sub,cls=configure(client,tenant_id,s1,h)
    prof=teacher(client,tenant_id,s1,h)
    y2=client.post(b2+"/years",headers=h,json={"year":2027,"label":"Ano 2027"}).json()["id"]
    assert client.post(b2+"/classes",headers=h,json={"academic_year_id":y,"name":"Invasão","students":20}).status_code==404
    cls2=client.post(b2+"/classes",headers=h,json={"academic_year_id":y2,"name":"7º B","students":30}).json()["id"]
    assert client.post(b2+f"/classes/{cls2}/assignments",headers=h,json={"subject_id":sub,"teacher_id":prof,"lessons":2}).status_code==404
    assert client.put(b2+f"/classes/{cls}/periods",headers=h,json={"periods":[{"weekday":0,"position":1,"start":"07:00","end":"08:00","shift":"manha"}]}).status_code==404
    assert client.post(b2+"/preview",headers=h,json={"academic_year_id":y}).status_code==404


def test_cross_tenant_preview_and_planning_read_blocked(context):
    client,_=context
    a,ha=tenant_with_admin(client,"alfa")
    sa=school(client,a,ha);year,sub,cls=configure(client,a,sa,ha)
    b,hb=tenant_with_admin(client,"beta")
    school(client,b,hb)
    assert client.get(pfx(a,sa)+"/years").status_code==403
    assert client.post(pfx(a,sa)+"/preview",headers=hb,json={"academic_year_id":year}).status_code==403
    assert client.post(pfx(a,sa)+"/subjects",headers=hb,json={"name":"Invasão"}).status_code==403


def test_school_admin_scoped_to_one_school_and_teacher_cannot_plan(context):
    client,_=context
    t,h=tenant_with_admin(client,"hierarquia")
    s1=school(client,t,h,"Centro");s2=school(client,t,h,"Norte")
    y,sub,cls=configure(client,t,s1,h)
    token=invitation(client,t,h,"school_admin",s1,"schooladmin-fase2@example.com")
    school_h=accept(client,t,token)
    assert client.get(pfx(t,s1)+"/years").status_code==200
    assert client.get(pfx(t,s2)+"/years").status_code==403
    assert client.post(pfx(t,s2)+"/subjects",headers=school_h,json={"name":"Arte"}).status_code==403
    teacher_id=teacher(client,t,s1,school_h)
    h=login(client,f"diretor-hierarquia@example.com","Senha-forte-diretor-123")
    token=invitation(client,t,h,"teacher",s1,"teacher-fase2@example.com",teacher_id=teacher_id)
    accept(client,t,token)
    assert client.get(pfx(t,s1)+"/subjects").status_code==403


def test_periods_validation_and_persist_unchanged(context):
    client,_=context
    t,h=tenant_with_admin(client,"periodos")
    s=school(client,t,h);base=pfx(t,s);y,sub,c=configure(client,t,s,h)
    assert set_periods(client,base,c,h).status_code==200
    original=client.get(base+f"/classes/{c}/periods").json()
    bad=[{"weekday":0,"position":1,"start":"09:00","end":"09:40","shift":"manha"},{"weekday":0,"position":2,"start":"09:30","end":"10:10","shift":"manha"}]
    assert client.put(base+f"/classes/{c}/periods",headers=h,json={"periods":bad}).status_code==422
    assert client.get(base+f"/classes/{c}/periods").json()==original
    assert client.put(base+f"/classes/{c}/periods",headers=h,json={"periods":[]}).status_code==422
    assert client.post(base+"/years",headers=h,json={"year":2027,"label":"Duplicado"}).status_code==409
    assert client.post(base+"/subjects",headers=h,json={"name":"Matemática"}).status_code==409


def test_custom_weights_invalid_not_silent(context):
    client,_=context
    t,h=tenant_with_admin(client,"pesos")
    s=school(client,t,h);base=pfx(t,s);y,sub,c=configure(client,t,s,h)
    assert set_periods(client,base,c,h).status_code==200
    prof=teacher(client,t,s,h);assert availability(client,t,prof,h).status_code==200
    assert assign(client,base,c,sub,prof,h,2).status_code==201
    r=client.post(base+"/preview",headers=h,json={"academic_year_id":y,"profile":"personalizado","weights":{"gaps":50},"time_limit":3})
    assert r.status_code==422, r.text


def test_assignment_duplicate_and_deletion(context):
    client,_=context
    t,h=tenant_with_admin(client,"demanda")
    s=school(client,t,h);b=pfx(t,s);y,sub,c=configure(client,t,s,h)
    prof=teacher(client,t,s,h)
    r=assign(client,b,c,sub,prof,h)
    assert r.status_code==201
    assert assign(client,b,c,sub,prof,h).status_code==409
    assert len(client.get(b+f"/classes/{c}/assignments").json())==1
    assert client.delete(b+f"/classes/{c}/assignments/{r.json()['id']}",headers=h).status_code==200
    assert len(client.get(b+f"/classes/{c}/assignments").json())==0


def test_four_fifty_minute_periods_with_recess(context):
    """Quatro aulas exatas; 08:40–09:00 não é período agendável."""
    client, _ = context
    tenant_id, h = tenant_with_admin(client, "quatro-periodos-50min")
    school_id = school(client, tenant_id, h)
    base = pfx(tenant_id, school_id)
    year_id, first_subject, class_id = configure(client, tenant_id, school_id, h)
    periods = [
        {"weekday": 0, "position": 1, "start": "07:00", "end": "07:50", "shift": "manha"},
        {"weekday": 0, "position": 2, "start": "07:50", "end": "08:40", "shift": "manha"},
        {"weekday": 0, "position": 3, "start": "09:00", "end": "09:50", "shift": "manha"},
        {"weekday": 0, "position": 4, "start": "09:50", "end": "10:40", "shift": "manha"},
    ]
    uri = base + f"/classes/{class_id}/periods"
    saved = client.put(uri, headers=h, json={"periods": periods})
    assert saved.status_code == 200, saved.text
    persisted = client.get(uri)
    assert persisted.status_code == 200
    assert persisted.json() == periods
    assert sum(
        (int(p["end"][:2]) * 60 + int(p["end"][3:]))
        - (int(p["start"][:2]) * 60 + int(p["start"][3:]))
        for p in persisted.json()
    ) == 200

    # A segunda aula acaba às 08:40; não há slot até 09:00.
    assert all(not (p["start"] < "09:00" and p["end"] > "08:40")
               for p in persisted.json())

    teacher_id = teacher(client, tenant_id, school_id, h)
    teacher_availability = client.put(
        f"/api/tenants/{tenant_id}/teachers/{teacher_id}/availability",
        headers=h,
        json={"intervals": [{"weekday": 0, "start": "07:00", "end": "10:40"}]},
    )
    assert teacher_availability.status_code == 200, teacher_availability.text

    subjects = [first_subject]
    for name in ("Português", "Ciências", "História"):
        subject = client.post(base + "/subjects", headers=h, json={"name": name})
        assert subject.status_code == 201, subject.text
        subjects.append(subject.json()["id"])
    for subject_id in subjects:
        inserted = assign(client, base, class_id, subject_id, teacher_id, h, lessons=1)
        assert inserted.status_code == 201, inserted.text

    response = client.post(base + "/preview", headers=h, json={
        "academic_year_id": year_id, "profile": "equilibrado", "time_limit": 5,
    })
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["result"] == "complete", preview.get("pending")
    assert preview["total_required"] == 4
    assert preview["total_assigned"] == 4
    assert preview["total_assigned_minutes"] == 200
    assert preview["conflicts"] == 0
    assert {
        (a["day"], a["order"], a["start"], a["end"])
        for a in preview["assignments"]
    } == {
        ("Seg", 1, "07:00", "07:50"),
        ("Seg", 2, "07:50", "08:40"),
        ("Seg", 3, "09:00", "09:50"),
        ("Seg", 4, "09:50", "10:40"),
    }

    # Horários inválidos não podem sobrescrever a grade já persistida.
    invalid_overlap = [
        {**periods[0]},
        {**periods[1], "start": "07:40"},
        periods[2],
        periods[3],
    ]
    assert client.put(uri, headers=h, json={"periods": invalid_overlap}).status_code == 422
    invalid_duplicate = [periods[0], {**periods[1], "position": 1}]
    assert client.put(uri, headers=h, json={"periods": invalid_duplicate}).status_code == 422
    assert client.get(uri).json() == periods


def test_same_teacher_cannot_overlap_two_classes_in_preview(context):
    """Duas turmas simultâneas não podem usar o mesmo docente."""
    client, _ = context
    tenant_id, h = tenant_with_admin(client, "conflito-turmas-50min")
    school_id = school(client, tenant_id, h)
    base = pfx(tenant_id, school_id)
    year_id, subject_id, first_class_id = configure(
        client, tenant_id, school_id, h,
    )
    second = client.post(base + "/classes", headers=h, json={
        "academic_year_id": year_id, "name": "6º Ano B", "students": 25,
    })
    assert second.status_code == 201, second.text
    second_class_id = second.json()["id"]
    period = {"weekday": 0, "position": 1, "start": "07:00",
              "end": "07:50", "shift": "manha"}
    for cls in (first_class_id, second_class_id):
        saved = client.put(
            base + f"/classes/{cls}/periods",
            headers=h, json={"periods": [period]},
        )
        assert saved.status_code == 200, saved.text
    teacher_id = teacher(client, tenant_id, school_id, h)
    assert client.put(
        f"/api/tenants/{tenant_id}/teachers/{teacher_id}/availability",
        headers=h,
        json={"intervals": [{"weekday": 0, "start": "07:00", "end": "07:50"}]},
    ).status_code == 200
    for cls in (first_class_id, second_class_id):
        assert assign(client, base, cls, subject_id, teacher_id, h, lessons=1).status_code == 201
    result = client.post(base + "/preview", headers=h, json={
        "academic_year_id": year_id, "time_limit": 5,
    })
    assert result.status_code == 200, result.text
    preview = result.json()
    assert preview["total_required"] == 2
    assert preview["total_assigned"] == 1
    assert preview["result"] == "partial"
    assert preview["conflicts"] == 0
    assert len(preview["assignments"]) == 1
