"""Fase 2: cadastros escolares e PRÉVIA (não publica, não reserva horários)."""
from __future__ import annotations
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db, bind_context
from .models import (User, School, Teacher, TeacherSchool, Availability, AuditLog, AcademicYear,
                     SchoolClass, Subject, ClassPeriod, TeachingAssignment, TeacherLimit, TeacherWeeklyLimit, SchoolResource, ResourceAvailability)
from .security import current_user, authorize, require_csrf
from .solver_preview import all_grid, DAYS

router = APIRouter(prefix="/api/tenants/{tenant_id}/schools/{school_id}", tags=["Planejamento escolar"])


def scope(db: Session, user: User, tenant_id: str, school_id: str, permission: str, write=False):
    authorize(db, user, tenant_id, permission, school_id=school_id, write=write)
    bind_context(db, user.id, tenant_id)
    school = db.scalar(select(School).where(School.id == school_id, School.tenant_id == tenant_id, School.is_active.is_(True)))
    if not school:
        raise HTTPException(404, "Escola não encontrada nesta organização.")
    return school


def audit(db: Session, user: User, tenant_id: str, action: str, kind: str, id: str, **details):
    db.add(AuditLog(tenant_id=tenant_id, actor_id=user.id, action=action, object_type=kind,
                    object_id=id, details=details))


def year_in(db, tenant_id, school_id, year_id):
    item=db.scalar(select(AcademicYear).where(AcademicYear.id==year_id,AcademicYear.tenant_id==tenant_id,AcademicYear.school_id==school_id))
    if not item: raise HTTPException(404, "Ano letivo não encontrado nesta escola.")
    return item


def class_in(db, tenant_id, school_id, class_id):
    item=db.scalar(select(SchoolClass).where(SchoolClass.id==class_id,SchoolClass.tenant_id==tenant_id,SchoolClass.school_id==school_id))
    if not item: raise HTTPException(404, "Turma não encontrada nesta escola.")
    return item


class YearNew(BaseModel):
    year: int = Field(ge=2000, le=2200)
    label: str = Field(min_length=2, max_length=100)

class SubjectNew(BaseModel):
    name: str = Field(min_length=2, max_length=120)

class ClassNew(BaseModel):
    academic_year_id: str
    name: str = Field(min_length=2, max_length=100)
    students: int = Field(ge=1, le=500)

class PeriodNew(BaseModel):
    weekday: int = Field(ge=0, le=6)
    position: int = Field(ge=1, le=30)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-zÀ-ÿ0-9_-]+$")

class PeriodReplace(BaseModel):
    periods: list[PeriodNew] = Field(min_length=1, max_length=150)

class AssignmentNew(BaseModel):
    subject_id: str
    teacher_id: str
    lessons: int = Field(ge=1, le=50)
    max_consecutive: int = Field(default=2, ge=1, le=2)
    load_mode: str = Field(default="lessons", pattern=r"^(lessons|minutes)$")
    target_minutes: int | None = Field(default=None, ge=1, le=2000)
    min_minutes: int | None = Field(default=None, ge=1, le=2000)
    max_minutes: int | None = Field(default=None, ge=1, le=2000)
    resource_id: str | None = None

class ResourceNew(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    max_groups: int = Field(ge=1, le=50)
    max_students: int = Field(ge=1, le=5000)

class AvailableInterval(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

class ResourceIntervals(BaseModel):
    intervals: list[AvailableInterval] = Field(min_length=1, max_length=40)

class LimitsPayload(BaseModel):
    weekly: int = Field(ge=0, le=150)
    daily: dict[int,int]

class PreviewRequest(BaseModel):
    academic_year_id: str
    profile: str = Field(default="equilibrado", pattern=r"^(equilibrado|menos_janelas|menos_dias|personalizado)$")
    weights: dict[str,int] | None = None
    time_limit: int = Field(default=8, ge=1, le=15)


def minutes(hhmm):
    h,m=map(int, hhmm.split(":"))
    return h*60+m

def hhmm(x): return f"{x//60:02}:{x%60:02}"


@router.get("/years")
def years(tenant_id: str, school_id: str, db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    return [{"id":y.id,"year":y.year,"label":y.label} for y in db.scalars(select(AcademicYear).where(AcademicYear.tenant_id==tenant_id,AcademicYear.school_id==school_id).order_by(AcademicYear.year.desc())).all()]

@router.post("/years", status_code=201)
def add_year(tenant_id:str,school_id:str,data:YearNew,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    if db.scalar(select(AcademicYear.id).where(AcademicYear.tenant_id==tenant_id,AcademicYear.school_id==school_id,AcademicYear.year==data.year)):
        raise HTTPException(409,"Ano letivo já cadastrado nesta escola.")
    obj=AcademicYear(tenant_id=tenant_id,school_id=school_id,year=data.year,label=data.label.strip())
    db.add(obj);db.flush();audit(db,user,tenant_id,"academic_year.created","academic_year",obj.id,school_id=school_id)
    db.commit();return {"id":obj.id,"year":obj.year,"label":obj.label}

@router.get("/subjects")
def subjects(tenant_id:str,school_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    return [{"id":x.id,"name":x.name} for x in db.scalars(select(Subject).where(Subject.tenant_id==tenant_id,Subject.school_id==school_id).order_by(Subject.name)).all()]

@router.post("/subjects",status_code=201)
def add_subject(tenant_id:str,school_id:str,data:SubjectNew,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    name=data.name.strip()
    if db.scalar(select(Subject.id).where(Subject.tenant_id==tenant_id,Subject.school_id==school_id,Subject.name==name)):
        raise HTTPException(409,"Disciplina já cadastrada nesta escola.")
    obj=Subject(tenant_id=tenant_id,school_id=school_id,name=name)
    db.add(obj);db.flush();audit(db,user,tenant_id,"subject.created","subject",obj.id,school_id=school_id)
    db.commit();return {"id":obj.id,"name":obj.name}

@router.get("/classes")
def classes(tenant_id:str,school_id:str,academic_year_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    year_in(db,tenant_id,school_id,academic_year_id)
    return [{"id":x.id,"name":x.name,"students":x.students,"academic_year_id":x.academic_year_id} for x in db.scalars(select(SchoolClass).where(SchoolClass.tenant_id==tenant_id,SchoolClass.school_id==school_id,SchoolClass.academic_year_id==academic_year_id).order_by(SchoolClass.name)).all()]

@router.post("/classes",status_code=201)
def add_class(tenant_id:str,school_id:str,data:ClassNew,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    year_in(db,tenant_id,school_id,data.academic_year_id)
    if db.scalar(select(SchoolClass.id).where(SchoolClass.academic_year_id==data.academic_year_id,SchoolClass.name==data.name.strip())):
        raise HTTPException(409,"Turma já cadastrada nesse ano letivo.")
    obj=SchoolClass(tenant_id=tenant_id,school_id=school_id,academic_year_id=data.academic_year_id,name=data.name.strip(),students=data.students)
    db.add(obj);db.flush();audit(db,user,tenant_id,"class.created","class",obj.id,school_id=school_id)
    db.commit();return {"id":obj.id,"name":obj.name,"students":obj.students,"academic_year_id":obj.academic_year_id}

@router.get("/classes/{class_id}/periods")
def periods(tenant_id:str,school_id:str,class_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read");class_in(db,tenant_id,school_id,class_id)
    items=db.scalars(select(ClassPeriod).where(ClassPeriod.tenant_id==tenant_id,ClassPeriod.school_id==school_id,ClassPeriod.class_id==class_id).order_by(ClassPeriod.weekday,ClassPeriod.position)).all()
    return [{"weekday":p.weekday,"position":p.position,"start":hhmm(p.start_minute),"end":hhmm(p.end_minute),"shift":p.shift} for p in items]

@router.put("/classes/{class_id}/periods")
def replace_periods(tenant_id:str,school_id:str,class_id:str,data:PeriodReplace,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True);class_in(db,tenant_id,school_id,class_id)
    ordered=defaultdict(list)
    for item in data.periods:
        start,end=minutes(item.start),minutes(item.end)
        if start>=end: raise HTTPException(422,"O período deve terminar depois de começar.")
        ordered[item.weekday].append((item.position,start,end,item.shift))
    for day,items in ordered.items():
        positions=[v[0] for v in items]
        if len(positions)!=len(set(positions)): raise HTTPException(422,"Ordem duplicada no mesmo dia.")
        items.sort()
        for a,b in zip(items,items[1:]):
            if a[2]>b[1]:raise HTTPException(422,"Períodos sobrepostos ou fora da ordem cronológica.")
    db.query(ClassPeriod).filter(ClassPeriod.tenant_id==tenant_id,ClassPeriod.school_id==school_id,ClassPeriod.class_id==class_id).delete(synchronize_session=False)
    db.add_all([ClassPeriod(tenant_id=tenant_id,school_id=school_id,class_id=class_id,weekday=d,
               position=p,start_minute=s,end_minute=e,shift=shift)
               for d,items in ordered.items() for p,s,e,shift in items])
    audit(db,user,tenant_id,"periods.replaced","class",class_id,count=len(data.periods))
    db.commit();return {"updated":len(data.periods)}

@router.get("/classes/{class_id}/assignments")
def assignments(tenant_id:str,school_id:str,class_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read");class_in(db,tenant_id,school_id,class_id)
    items=db.scalars(select(TeachingAssignment).where(TeachingAssignment.tenant_id==tenant_id,TeachingAssignment.school_id==school_id,TeachingAssignment.class_id==class_id)).all()
    return [{"id":a.id,"subject_id":a.subject_id,"teacher_id":a.teacher_id,"lessons":a.lessons,
             "load_mode":a.load_mode,"target_minutes":a.target_minutes,"min_minutes":a.min_minutes,
             "max_minutes":a.max_minutes,"resource_id":a.resource_id,"max_consecutive":a.max_consecutive} for a in items]

@router.post("/classes/{class_id}/assignments",status_code=201)
def add_assignment(tenant_id:str,school_id:str,class_id:str,data:AssignmentNew,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True);class_in(db,tenant_id,school_id,class_id)
    if not db.scalar(select(Subject.id).where(Subject.id==data.subject_id,Subject.tenant_id==tenant_id,Subject.school_id==school_id)):
        raise HTTPException(404,"Disciplina não pertence à escola.")
    if not db.scalar(select(TeacherSchool.id).where(TeacherSchool.teacher_id==data.teacher_id,TeacherSchool.tenant_id==tenant_id,TeacherSchool.school_id==school_id)):
        raise HTTPException(404,"Professor não está vinculado à escola.")
    if data.load_mode=="minutes":
        lo=data.min_minutes if data.min_minutes is not None else data.target_minutes
        hi=data.max_minutes if data.max_minutes is not None else data.target_minutes
        if data.target_minutes is None or lo is None or hi is None or not lo<=data.target_minutes<=hi:
            raise HTTPException(422,"Minutos: informe meta e faixa válida mínimo <= meta <= máximo.")
    elif any(v is not None for v in (data.target_minutes,data.min_minutes,data.max_minutes)):
        raise HTTPException(422,"Carga por aulas não aceita limites em minutos.")
    if data.resource_id and not db.scalar(select(SchoolResource.id).where(SchoolResource.id==data.resource_id,
                                             SchoolResource.tenant_id==tenant_id,SchoolResource.school_id==school_id)):
        raise HTTPException(404,"Recurso não pertence a esta escola.")
    if db.scalar(select(TeachingAssignment.id).where(TeachingAssignment.class_id==class_id,TeachingAssignment.subject_id==data.subject_id,TeachingAssignment.teacher_id==data.teacher_id)):
        raise HTTPException(409,"Atribuição já cadastrada para este professor e disciplina.")
    obj=TeachingAssignment(tenant_id=tenant_id,school_id=school_id,class_id=class_id,subject_id=data.subject_id,
                           teacher_id=data.teacher_id,lessons=data.lessons,max_consecutive=data.max_consecutive,
                           load_mode=data.load_mode,target_minutes=data.target_minutes,min_minutes=data.min_minutes,
                           max_minutes=data.max_minutes,resource_id=data.resource_id)
    db.add(obj);db.flush();audit(db,user,tenant_id,"assignment.created","assignment",obj.id,school_id=school_id)
    db.commit();return {"id":obj.id,"subject_id":obj.subject_id,"teacher_id":obj.teacher_id,"lessons":obj.lessons,
                         "load_mode":obj.load_mode,"resource_id":obj.resource_id,"max_consecutive":obj.max_consecutive}

@router.delete("/classes/{class_id}/assignments/{assignment_id}")
def delete_assignment(tenant_id:str,school_id:str,class_id:str,assignment_id:str,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True);class_in(db,tenant_id,school_id,class_id)
    obj=db.scalar(select(TeachingAssignment).where(TeachingAssignment.id==assignment_id,TeachingAssignment.tenant_id==tenant_id,TeachingAssignment.school_id==school_id,TeachingAssignment.class_id==class_id))
    if not obj:raise HTTPException(404,"Atribuição inexistente.")
    db.delete(obj);audit(db,user,tenant_id,"assignment.deleted","assignment",assignment_id,school_id=school_id)
    db.commit();return {"deleted":True}


# A gestão dos limites é GLOBAL ao professor; requer permissão de organização,
# já que a mudança pode impactar várias unidades vinculadas.
@router.get("/teacher-limits/{teacher_id}")
def get_teacher_limits(tenant_id:str,school_id:str,teacher_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    if not db.scalar(select(TeacherSchool.id).where(TeacherSchool.tenant_id==tenant_id,TeacherSchool.school_id==school_id,TeacherSchool.teacher_id==teacher_id)):
        raise HTTPException(404,"Professor não vinculado à unidade.")
    weekly=db.scalar(select(TeacherWeeklyLimit).where(TeacherWeeklyLimit.tenant_id==tenant_id,TeacherWeeklyLimit.teacher_id==teacher_id))
    rows=db.scalars(select(TeacherLimit).where(TeacherLimit.tenant_id==tenant_id,TeacherLimit.teacher_id==teacher_id)).all()
    return {"weekly":weekly.max_lessons if weekly else None,"daily":{str(x.weekday):x.max_lessons for x in rows}}

@router.put("/teacher-limits/{teacher_id}")
def set_teacher_limits(tenant_id:str,school_id:str,teacher_id:str,data:LimitsPayload,request:Request,
                       db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    # Restrito à autorização de nível ORGANIZAÇÃO para docente compartilhado.
    authorize(db,user,tenant_id,"teachers.availability",write=True)
    if not db.scalar(select(TeacherSchool.id).where(TeacherSchool.tenant_id==tenant_id,TeacherSchool.school_id==school_id,TeacherSchool.teacher_id==teacher_id)):
        raise HTTPException(404,"Professor não vinculado à unidade.")
    if any(type(k) is not int or not 0<=k<=6 or type(v) is not int or not 0<=v<=30 for k,v in data.daily.items()):
        raise HTTPException(422,"Limites diários exigem dias 0 a 6 e valores de 0 a 30.")
    db.query(TeacherWeeklyLimit).filter(TeacherWeeklyLimit.tenant_id==tenant_id,TeacherWeeklyLimit.teacher_id==teacher_id).delete()
    db.query(TeacherLimit).filter(TeacherLimit.tenant_id==tenant_id,TeacherLimit.teacher_id==teacher_id).delete()
    db.add(TeacherWeeklyLimit(tenant_id=tenant_id,teacher_id=teacher_id,max_lessons=data.weekly))
    db.add_all([TeacherLimit(tenant_id=tenant_id,teacher_id=teacher_id,weekday=d,max_lessons=n) for d,n in data.daily.items()])
    audit(db,user,tenant_id,"teacher_limits.changed","teacher",teacher_id,weekly=data.weekly,daily=data.daily)
    db.commit();return {"updated":True}

@router.get("/resources")
def list_resources(tenant_id:str,school_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    rows=db.scalars(select(SchoolResource).where(SchoolResource.tenant_id==tenant_id,SchoolResource.school_id==school_id).order_by(SchoolResource.name)).all()
    return [{"id":r.id,"name":r.name,"max_groups":r.max_groups,"max_students":r.max_students} for r in rows]

@router.post("/resources",status_code=201)
def add_resource(tenant_id:str,school_id:str,data:ResourceNew,request:Request,
                 db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    name=data.name.strip()
    if db.scalar(select(SchoolResource.id).where(SchoolResource.tenant_id==tenant_id,SchoolResource.school_id==school_id,SchoolResource.name==name)):
        raise HTTPException(409,"Recurso já existe nesta unidade.")
    r=SchoolResource(tenant_id=tenant_id,school_id=school_id,name=name,max_groups=data.max_groups,max_students=data.max_students)
    db.add(r);db.flush();audit(db,user,tenant_id,"resource.created","resource",r.id,school_id=school_id)
    db.commit();return {"id":r.id,"name":r.name,"max_groups":r.max_groups,"max_students":r.max_students}

@router.get("/resources/{resource_id}/availability")
def resource_availability(tenant_id:str,school_id:str,resource_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    scope(db,user,tenant_id,school_id,"planning.read")
    resource_in(db,tenant_id,school_id,resource_id)
    rows=db.scalars(select(ResourceAvailability).where(ResourceAvailability.tenant_id==tenant_id,
                    ResourceAvailability.school_id==school_id,ResourceAvailability.resource_id==resource_id).order_by(ResourceAvailability.weekday,ResourceAvailability.start_minute)).all()
    return [{"weekday":x.weekday,"start":hhmm(x.start_minute),"end":hhmm(x.end_minute)} for x in rows]

def resource_in(db,tenant_id,school_id,resource_id):
    r=db.scalar(select(SchoolResource).where(SchoolResource.id==resource_id,SchoolResource.tenant_id==tenant_id,SchoolResource.school_id==school_id))
    if not r:raise HTTPException(404,"Recurso não encontrado nesta unidade.")
    return r

@router.put("/resources/{resource_id}/availability")
def set_resource_availability(tenant_id:str,school_id:str,resource_id:str,data:ResourceIntervals,request:Request,
                              db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.write",True)
    resource_in(db,tenant_id,school_id,resource_id)
    intervals=sorted((x.weekday,minutes(x.start),minutes(x.end)) for x in data.intervals)
    for i,(day,a,b) in enumerate(intervals):
        if a>=b or (i>0 and intervals[i-1][0]==day and intervals[i-1][2]>a):
            raise HTTPException(422,"Disponibilidade de recurso inválida ou sobreposta.")
    db.query(ResourceAvailability).filter(ResourceAvailability.tenant_id==tenant_id,ResourceAvailability.school_id==school_id,
                                         ResourceAvailability.resource_id==resource_id).delete()
    db.add_all([ResourceAvailability(tenant_id=tenant_id,school_id=school_id,resource_id=resource_id,
                                   weekday=d,start_minute=a,end_minute=b) for d,a,b in intervals])
    audit(db,user,tenant_id,"resource.availability.changed","resource",resource_id,school_id=school_id,count=len(intervals))
    db.commit();return {"updated":len(intervals)}

def build_preview(db, tenant_id:str,school_id:str,year_id:str,profile:str,weights,time_limit:int):
    class_rows=db.scalars(select(SchoolClass).where(SchoolClass.tenant_id==tenant_id,SchoolClass.school_id==school_id,SchoolClass.academic_year_id==year_id)).all()
    if not class_rows: raise HTTPException(422,"Cadastre pelo menos uma turma neste ano letivo.")
    ids=[c.id for c in class_rows]
    periods=db.scalars(select(ClassPeriod).where(ClassPeriod.tenant_id==tenant_id,ClassPeriod.school_id==school_id,ClassPeriod.class_id.in_(ids))).all()
    demands=db.scalars(select(TeachingAssignment).where(TeachingAssignment.tenant_id==tenant_id,TeachingAssignment.school_id==school_id,TeachingAssignment.class_id.in_(ids))).all()
    if not demands: raise HTTPException(422,"Cadastre as cargas horárias por turma e disciplina antes de gerar.")
    if len(demands)>120 or len(periods)>450:raise HTTPException(422,"Prévia experimental limitada a 120 atribuições e 450 períodos.")
    subject_ids={d.subject_id for d in demands};teacher_ids={d.teacher_id for d in demands}
    subj={v.id:v.name for v in db.scalars(select(Subject).where(Subject.tenant_id==tenant_id,Subject.school_id==school_id,Subject.id.in_(subject_ids))).all()}
    teacher_names={v.id:v.name for v in db.scalars(select(Teacher).where(Teacher.tenant_id==tenant_id,Teacher.id.in_(teacher_ids),Teacher.active.is_(True))).all()}
    if len(teacher_names)!=len(teacher_ids):raise HTTPException(409,"Uma atribuição referencia professor inexistente ou inativo.")
    available=db.scalars(select(Availability).where(Availability.tenant_id==tenant_id,Availability.teacher_id.in_(teacher_ids))).all()
    by_teacher=defaultdict(list)
    for a in available:
        by_teacher[a.teacher_id].append({"day":DAYS[a.weekday],"start":hhmm(a.start_minute),"end":hhmm(a.end_minute)})
    by_class=defaultdict(list)
    for p in periods:
        by_class[p.class_id].append({"day":DAYS[p.weekday],"order":p.position,"start":hhmm(p.start_minute),"end":hhmm(p.end_minute),"shift":p.shift})
    if any(not by_class[c.id] for c in class_rows):raise HTTPException(422,"Todas as turmas do ano selecionado devem possuir períodos cadastrados.")
    if any(not by_teacher[x] for x in teacher_ids):
        # Sem disponibilidade = professor sem aulas; o solver identifica a pendência.
        pass
    teacher_limits=db.scalars(select(TeacherLimit).where(TeacherLimit.tenant_id==tenant_id,TeacherLimit.teacher_id.in_(teacher_ids))).all()
    daily=defaultdict(dict)
    for v in teacher_limits:daily[v.teacher_id][DAYS[v.weekday]]=v.max_lessons
    weekly_rows=db.scalars(select(TeacherWeeklyLimit).where(TeacherWeeklyLimit.tenant_id==tenant_id,TeacherWeeklyLimit.teacher_id.in_(teacher_ids))).all()
    weekly={v.teacher_id:v.max_lessons for v in weekly_rows}
    resource_ids={d.resource_id for d in demands if d.resource_id}
    all_resources=db.scalars(select(SchoolResource).where(SchoolResource.tenant_id==tenant_id,SchoolResource.school_id==school_id,
                                                     SchoolResource.id.in_(resource_ids))).all() if resource_ids else []
    if len(all_resources)!=len(resource_ids):raise HTTPException(409,"Recurso obrigatório inexistente ou de outra unidade.")
    by_res={v.id:{"school_id":school_id,"max_groups":v.max_groups,"max_students":v.max_students,"availability":[]} for v in all_resources}
    if resource_ids:
        for v in db.scalars(select(ResourceAvailability).where(ResourceAvailability.tenant_id==tenant_id,
                            ResourceAvailability.school_id==school_id,ResourceAvailability.resource_id.in_(resource_ids))).all():
            by_res[v.resource_id]["availability"].append({"day":DAYS[v.weekday],"start":hhmm(v.start_minute),"end":hhmm(v.end_minute)})
    params={"mode":"mixed","organization_id":tenant_id,"profile":profile,
            "time_limit":time_limit,"schools":{school_id:{"organization_id":tenant_id}},
            "classes":{c.id:{"school_id":school_id,"students":c.students,"slots":by_class[c.id]} for c in class_rows},
            "teachers":{tid:{"organization_id":tenant_id,"availability":by_teacher[tid],"weekly_limit":weekly.get(tid,150),"daily_limits":daily[tid]} for tid in teacher_ids},
            "demands":[{"class_id":d.class_id,"teacher_id":d.teacher_id,"subject":subj[d.subject_id],
                        "lessons":d.lessons,"max_consecutive":d.max_consecutive,
                        "unit":d.load_mode,"target_minutes":d.target_minutes,"min_minutes":d.min_minutes,
                        "max_minutes":d.max_minutes,"resource_id":d.resource_id} for d in demands],
            "resources":by_res,"travel_minutes":{}}
    if profile=="personalizado":params["weights"]=weights
    try: result=all_grid(params)
    except (ValueError, RuntimeError) as exc:raise HTTPException(422,str(exc)) from exc
    for a in result.get("assignments",[]):
        a["class_name"]=next(c.name for c in class_rows if c.id==a["class_id"])
        a["teacher_name"]=teacher_names[a["teacher"]]
    for p in result.get("pending",[]):
        p["class_name"]=next(c.name for c in class_rows if c.id==p["class_id"])
        p["teacher_name"]=teacher_names[p["teacher"]]
    result["preview_only"]=True
    result["safety_notice"]="PRÉVIA NÃO PUBLICÁVEL: limites docentes, minutos e recursos integrados apenas nesta escola; sem reservas oficiais, geração entre unidades, vigência ou publicação."
    return result

@router.post("/preview")
def preview(tenant_id:str,school_id:str,data:PreviewRequest,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request);scope(db,user,tenant_id,school_id,"planning.preview",True)
    year_in(db,tenant_id,school_id,data.academic_year_id)
    result=build_preview(db,tenant_id,school_id,data.academic_year_id,data.profile,data.weights,data.time_limit)
    audit(db,user,tenant_id,"planning.preview","academic_year",data.academic_year_id,
          school_id=school_id,assigned=result["total_assigned"],required=result["total_required"],profile=data.profile)
    db.commit()
    return result
