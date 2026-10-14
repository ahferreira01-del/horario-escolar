"""Fase 4C: preflight sem gravação e publicação oficial atômica no PostgreSQL.

Limites explícitos: não implementa substituição de versões vigentes, geração conjunta,
feriados/exceções por data, bloqueios pontuais nem sincronização entre tenants. A
publicação exige proposta aprovada e horários semanais íntegros; não declara
uma grade matematicamente ótima ou adequada a um calendário excepcional.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from itertools import combinations
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import get_db, bind_context
from .models import (
    User, GradeProposal, School, SchoolClass, ClassPeriod, Subject,
    TeachingAssignment, Teacher, Availability, SchoolResource, ResourceAvailability,
    TeacherLimit, TeacherWeeklyLimit, SchoolTravelTime, PublishedGrade, PublishedLesson, PublishedClass,
)
from .security import current_user, require_csrf, authorize
from .planning import audit
from .workflow import source_fingerprint, safe_csv

router = APIRouter(prefix='/api/tenants/{tenant_id}/publications', tags=['Publicação de grades'])
WEEKDAYS = ('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom')
MAX_DAYS = 370
MAX_LESSONS = 2500
# Limite global de ocorrências datadas: impede expansão desnecessária de
# calendários grandes tanto na pré-validação como na publicação transacional.
MAX_OCCURRENCES = MAX_LESSONS * 10

class PublicationPart(BaseModel):
    school_id: str
    proposal_id: str
    class_ids: list[str] = Field(min_length=1, max_length=150)

    @model_validator(mode='after')
    def no_duplicates(self):
        if len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError('Turma duplicada na seleção.')
        return self


class PublicationRequest(BaseModel):
    parts: list[PublicationPart] = Field(min_length=1, max_length=20)
    valid_from: date
    valid_to: date
    exceptional_justification: str | None = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def range_ok(self):
        n = (self.valid_to - self.valid_from).days
        if n < 0 or n > MAX_DAYS:
            raise ValueError('Vigência deve ter de 1 a 371 dias corridos.')
        if len({(p.school_id, cid) for p in self.parts for cid in p.class_ids}) != sum(len(p.class_ids) for p in self.parts):
            raise ValueError('Turma foi incluída em mais de uma parte.')
        return self


class TravelPayload(BaseModel):
    destination_school_id: str
    minutes: int = Field(ge=0, le=1440)


def fail(reason: str, status: int = 409):
    raise HTTPException(status, reason)


def _local_utc(d: date, minute: int, tz: ZoneInfo) -> datetime:
    # Rejeitar instantes locais inexistentes ou ambíguos para não agendar em DST.
    naive = datetime.combine(d, time()) + timedelta(minutes=minute)
    aware = naive.replace(tzinfo=tz, fold=0)
    if aware.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
        fail('Há horário ambíguo ou inexistente por mudança de fuso/horário de verão.')
    utc = aware.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) != naive:
        fail('Há horário local inexistente na data de vigência.')
    return utc


def _events(rows: list[dict], schools: dict[str, School], from_date: date, to_date: date,
            *, max_events: int = MAX_OCCURRENCES):
    """Expande somente os dias de aula, com orçamento antes de materializar datas.

    A soma de ocorrências é verificada ANTES de reservar a lista em memória,
    evitando criar milhares de eventos apenas para rejeitá-los depois.
    """
    events=[]
    zones={}
    for sid, school in schools.items():
        try: zones[sid]=ZoneInfo(school.timezone)
        except ZoneInfoNotFoundError: fail(f'Fuso inválido cadastrado para a unidade {sid}.',422)
    span=(to_date-from_date).days
    budget=0
    for r in rows:
        weekday=r['weekday']
        if type(weekday) is not int or not 0<=weekday<=6:
            fail('Dia da semana inválido na grade publicada.',422)
        if r['school_id'] not in zones:
            fail('Unidade da aula não encontrada para conversão de fuso.',422)
        if span<0: continue
        first_offset=(weekday-from_date.weekday())%7
        if first_offset>span: continue
        occurrences=1+(span-first_offset)//7
        budget+=occurrences
        if budget>max_events:
            fail('Quantidade elevada de ocorrências; divida a vigência.',422)
    for r in rows:
        first_offset=(r['weekday']-from_date.weekday())%7
        d=from_date+timedelta(days=first_offset)
        while d<=to_date:
            tz=zones[r['school_id']]
            a=_local_utc(d,r['start_minute'],tz)
            b=_local_utc(d,r['end_minute'],tz)
            if b<=a: fail('Período horário inválido após conversão de fuso.')
            events.append({**r,'date':d, 'start_utc':a,'end_utc':b})
            d+=timedelta(days=7)
    return events


def _overlaps(a,b):
    return a['start_utc']<b['end_utc'] and b['start_utc']<a['end_utc']


def _check_published_conflicts(rows, existing, schools, travel):
    all_rows = rows + existing
    if len(all_rows)>MAX_OCCURRENCES:
        fail('Quantidade elevada de ocorrências; divida a vigência.',422)
    by_teacher=defaultdict(list)
    by_class=defaultdict(list)
    by_resource=defaultdict(list)
    for event in all_rows:
        by_teacher[event['teacher_id']].append(event)
        by_class[event['class_id']].append(event)
        if event['resource_id']:
            by_resource[(event['school_id'],event['resource_id'])].append(event)
    for events in by_class.values():
        ev=sorted(events,key=lambda r:r['start_utc'])
        for a,b in zip(ev,ev[1:]):
            if _overlaps(a,b):fail('A turma já tem aula oficial na vigência escolhida.')
    for events in by_teacher.values():
        ev=sorted(events,key=lambda r:r['start_utc'])
        for a,b in zip(ev,ev[1:]):
            if _overlaps(a,b):fail('Conflito de professor entre grades ou unidades.')
            if a['school_id'] != b['school_id']:
                # A matriz de deslocamento é obrigatória para qualquer troca
                # de unidade na agenda do docente. Não presumir zero quando
                # as datas locais forem diferentes (inclusive à meia-noite).
                # Intervalos longos satisfazem naturalmente o tempo cadastrado.
                k = (a['school_id'], b['school_id'])
                if k not in travel:
                    fail('Tempo de deslocamento entre unidades não configurado.')
                gap = (b['start_utc'] - a['end_utc']).total_seconds()
                if gap < travel[k] * 60:
                    fail('Conflito de deslocamento do professor entre unidades.')
    return by_resource


def _validate_resources(resource_events, resources):
    for key, arr in resource_events.items():
        r=resources.get(key)
        if not r:fail('Recurso vinculado à grade não existe ou pertence a outra unidade.')
        points=[]
        for x in arr:
            points.append((x['start_utc'],1,x['students'],1))
            points.append((x['end_utc'],0,-x['students'],-1))
        groups=students=0
        for _,_, ds,dg in sorted(points):
            students+=ds;groups+=dg
            if groups>r.max_groups or students>r.max_students:
                fail('Capacidade simultânea de turmas/alunos de recurso ultrapassada.')


def _prepare(db: Session, user: User, tenant_id: str, body: PublicationRequest):
    bind_context(db,user.id,tenant_id)
    schools={s.id:s for s in db.scalars(select(School).where(School.tenant_id==tenant_id)).all()}
    selected=set()
    entries=[]
    sections=[]
    for part in body.parts:
        authorize(db,user,tenant_id,'grades.publish',part.school_id,write=True)
        school=schools.get(part.school_id)
        if not school or not school.is_active:fail('Unidade inativa ou inexistente.',404)
        p=db.scalar(select(GradeProposal).where(GradeProposal.id==part.proposal_id,
                      GradeProposal.tenant_id==tenant_id,GradeProposal.school_id==part.school_id))
        if not p:fail('Proposta não encontrada nesta unidade.',404)
        if p.status!='approved':fail('A publicação requer proposta aprovada.')
        if p.source_hash!=source_fingerprint(db,tenant_id,part.school_id,p.academic_year_id):
            fail('Proposta desatualizada; os cadastros foram alterados.')
        if p.snapshot.get('conflicts')!=0 or p.snapshot.get('result') not in ('complete','partial'):
            fail('A proposta não é uma grade validada.')
        rows=db.scalars(select(SchoolClass).where(SchoolClass.tenant_id==tenant_id,
              SchoolClass.school_id==part.school_id,SchoolClass.academic_year_id==p.academic_year_id,
              SchoolClass.id.in_(part.class_ids))).all()
        if len(rows)!=len(part.class_ids):fail('Turma selecionada fora da unidade/ano.',404)
        for row in rows:
            if row.id in selected:fail('A mesma turma não pode ser selecionada em duas unidades.')
            selected.add(row.id)
        pending=[q for q in p.snapshot.get('pending',[]) if q.get('class_id') in set(part.class_ids)]
        if pending:
            authorize(db,user,tenant_id,'grades.publish_partial',part.school_id,write=True)
            if not body.exceptional_justification or not body.exceptional_justification.strip():
                fail('Publicação parcial exige justificativa excepcional.',422)
            if not p.justification:fail('A proposta parcial não possui justificativa na revisão.')
        known_classes={r.get('class_id') for r in p.snapshot.get('assignments',[])} | \
                      {r.get('class_id') for r in p.snapshot.get('pending',[])}
        if not set(part.class_ids).issubset(known_classes):
            fail('Turma selecionada não aparece na proposta calculada.',422)
        portions=[r for r in p.snapshot.get('assignments',[]) if r.get('class_id') in part.class_ids]
        sections.append((p,part, bool(pending)))
        entries+=portions
    if len(entries)>MAX_LESSONS:fail('Lote excessivo; publique em grupos menores.',422)
    # Revalidar identidade dos slots e alocação docente: confiar apenas em propostas de servidor.
    ids=set(selected)
    cls={c.id:c for c in db.scalars(select(SchoolClass).where(SchoolClass.tenant_id==tenant_id,SchoolClass.id.in_(ids))).all()}
    periods={(x.class_id,x.weekday,x.position):x for x in db.scalars(select(ClassPeriod).where(ClassPeriod.tenant_id==tenant_id,ClassPeriod.class_id.in_(ids))).all()}
    assignments=db.scalars(select(TeachingAssignment).where(TeachingAssignment.tenant_id==tenant_id,TeachingAssignment.class_id.in_(ids))).all()
    subjects={x.id:x.name for x in db.scalars(select(Subject).where(Subject.tenant_id==tenant_id)).all()}
    assignments_valid={(a.class_id,a.teacher_id,subjects.get(a.subject_id),a.resource_id) for a in assignments}
    out=[]; seen=set()
    for r in entries:
        try:
            cls_id=r['class_id']; teacher_id=r['teacher']; day=WEEKDAYS.index(r['day'])
            order=int(r['order']); st=int(r['start'][:2])*60+int(r['start'][3:]); en=int(r['end'][:2])*60+int(r['end'][3:])
        except (KeyError,ValueError,TypeError,IndexError):fail('Proposta possui aula inválida; gere nova prévia.')
        klass=cls.get(cls_id); slot=periods.get((cls_id,day,order))
        if not klass or not slot or (slot.start_minute,slot.end_minute)!=(st,en):
            fail('Aula difere dos períodos oficiais cadastrados.')
        if r.get('school_id') != klass.school_id:fail('Aula com unidade divergente.')
        if (cls_id,teacher_id,r.get('subject'),r.get('resource_id')) not in assignments_valid:
            fail('Aula não corresponde à atribuição de professor/disciplina/recurso.')
        if (cls_id,day,order) in seen:fail('Turma possui aulas duplicadas no mesmo período.')
        seen.add((cls_id,day,order))
        out.append({'tenant_id':tenant_id,'school_id':klass.school_id,'class_id':cls_id,
                    'teacher_id':teacher_id,'resource_id':r.get('resource_id'),
                    'subject':r['subject'],'weekday':day,'period_position':order,
                    'start_minute':st,'end_minute':en,'students':klass.students})
    # Uma aprovação não substitui a validação independente das cotas:
    # conferir os DÉFICITS declarados no snapshot, além de impedir excesso.
    # Uma proposta marcada como completa mas incompleta NÃO pode ser publicada.
    demand_counts=defaultdict(list)
    for e in out:
        demand_counts[(e['class_id'],e['teacher_id'],e['subject'],e['resource_id'])].append(e['end_minute']-e['start_minute'])
    pending_rows=[]
    for proposal, part, _ in sections:
        pending_rows.extend(q for q in proposal.snapshot.get('pending',[])
                            if q.get('class_id') in part.class_ids)
    pending_by_demand={}
    for row in pending_rows:
        key=(row.get('class_id'),row.get('teacher'),row.get('subject'))
        if key in pending_by_demand or not isinstance(row.get('missing'),int) or row['missing']<=0:
            fail('Pendências declaradas estão duplicadas ou inconsistentes.')
        pending_by_demand[key]=row
    for demand in assignments:
        subject=subjects.get(demand.subject_id)
        if subject is None:fail('Disciplina cadastrada não encontrada.')
        key=(demand.class_id,demand.teacher_id,subject,demand.resource_id)
        durations=demand_counts[key]
        pkey=(demand.class_id,demand.teacher_id,subject)
        if demand.load_mode=='lessons':
            delivered=len(durations)
            required=demand.lessons
            maximum=demand.lessons
            unit='lessons'
        else:
            delivered=sum(durations)
            required=demand.min_minutes if demand.min_minutes is not None else demand.target_minutes
            maximum=demand.max_minutes if demand.max_minutes is not None else demand.target_minutes
            unit='minutes'
        if required is None or maximum is None or delivered>maximum:
            fail('Carga semanal superior à autorizada ou configuração incompleta.')
        deficit=max(0,required-delivered)
        declared=pending_by_demand.pop(pkey,None)
        if (deficit == 0 and declared is not None) or (deficit and (
            declared is None or declared.get('missing')!=deficit or declared.get('unit')!=unit)):
            fail('Cobertura da grade não corresponde às aulas pendentes declaradas.')
    if pending_by_demand:
        fail('Proposta declara pendências inexistentes nos cadastros.')
    # Revalidar recursos, incluindo faixas reais de disponibilidade.
    resources={r.id:r for r in db.scalars(select(SchoolResource).where(SchoolResource.tenant_id==tenant_id)).all()}
    av_resources=defaultdict(list)
    for a in db.scalars(select(ResourceAvailability).where(ResourceAvailability.tenant_id==tenant_id)).all():
        av_resources[(a.resource_id,a.weekday)].append((a.start_minute,a.end_minute))
    for e in out:
        if e['resource_id']:
            r=resources.get(e['resource_id'])
            if not r or r.school_id!=e['school_id']:
                fail('Recurso obrigatório ausente ou de outra escola.')
            if not any(a<=e['start_minute'] and e['end_minute']<=b for a,b in av_resources[(r.id,e['weekday'])]):
                fail('Aula fora da disponibilidade do espaço escolar.')
    # Limite de aulas consecutivas é por disciplina/turma e pode ser UM.
    # Uma mesma disciplina com dois professores usa o limite mais restritivo.
    # O recreio NÃO interrompe a sequência de períodos letivos.
    limits={}
    for a in assignments:
        key=(a.class_id, subjects[a.subject_id])
        limits[key]=min(limits.get(key,2),a.max_consecutive)
    for cid in selected:
        for day in range(7):
            today=sorted([e for e in out if e['class_id']==cid and e['weekday']==day],key=lambda e:e['period_position'])
            indexes=sorted([p.position for p in periods.values() if p.class_id==cid and p.weekday==day])
            ordinal={p:i for i,p in enumerate(indexes)}
            for a,b in zip(today,today[1:]):
                if (a['subject']==b['subject'] and limits[(cid,a['subject'])]==1 and
                    ordinal[a['period_position']]+1==ordinal[b['period_position']]):
                    fail('Disciplina configurada para no máximo uma aula consecutiva.')
            for a,b,c in zip(today,today[1:],today[2:]):
                if a['subject']==b['subject']==c['subject'] and \
                   ordinal[a['period_position']]+1==ordinal[b['period_position']] and \
                   ordinal[b['period_position']]+1==ordinal[c['period_position']]:
                    fail('Mais de duas aulas consecutivas da mesma disciplina, inclusive após o recreio.')
    # Validação independente das disponibilidades reais (o snapshot pode ter sido manipulado).
    teacher_ids={x['teacher_id'] for x in out}
    av=defaultdict(list)
    for a in db.scalars(select(Availability).where(Availability.tenant_id==tenant_id,Availability.teacher_id.in_(teacher_ids))).all():
        av[(a.teacher_id,a.weekday)].append((a.start_minute,a.end_minute))
    for row in out:
        if not any(a<=row['start_minute'] and row['end_minute']<=b for a,b in av[(row['teacher_id'],row['weekday'])]):
            fail('Aula fora da disponibilidade do professor.')
    daily=defaultdict(int);weekly=defaultdict(int)
    for e in out:
        daily[(e['teacher_id'],e['weekday'])]+=1;weekly[e['teacher_id']]+=1
    for x in db.scalars(select(TeacherLimit).where(TeacherLimit.tenant_id==tenant_id,TeacherLimit.teacher_id.in_(teacher_ids))).all():
        if daily[(x.teacher_id,x.weekday)]>x.max_lessons:fail('Limite diário de professor ultrapassado.')
    for x in db.scalars(select(TeacherWeeklyLimit).where(TeacherWeeklyLimit.tenant_id==tenant_id,TeacherWeeklyLimit.teacher_id.in_(teacher_ids))).all():
        if weekly[x.teacher_id]>x.max_lessons:fail('Limite semanal de professor ultrapassado.')
    return schools,sections,out


def _build_events(db: Session, tenant_id: str, body: PublicationRequest, schools, new_rows):
    # Todos os compromissos nas semanas envolvidas, mesmo com vigências distintas.
    # Comparar a semana COMPLETA para validar limites docentes semanais.
    # Ex.: publicação segunda-terça + outra quarta-sexta podem ultrapassar a
    # cota semanal mesmo que suas vigências não se sobreponham.
    week_start=body.valid_from-timedelta(days=body.valid_from.weekday())
    week_end=body.valid_to+timedelta(days=6-body.valid_to.weekday())
    current=db.scalars(select(PublishedGrade).where(PublishedGrade.tenant_id==tenant_id,
        PublishedGrade.valid_from<=datetime.combine(week_end,time()),
        PublishedGrade.valid_to>=datetime.combine(week_start,time()))).all()
    # Vigências de uma turma são exclusivas somente no intervalo de PUBLICAÇÃO,
    # não em outros dias da mesma semana usados apenas para conferir as cotas.
    selected_class_ids={r['class_id'] for r in new_rows}
    selected_class_ids.update(cid for part in body.parts for cid in part.class_ids)
    if current:
        overlapping=[p.id for p in current if p.valid_from.date()<=body.valid_to
                     and p.valid_to.date()>=body.valid_from]
        old_ids={c.class_id for c in db.scalars(select(PublishedClass).where(
            PublishedClass.tenant_id==tenant_id,
            PublishedClass.publication_id.in_(overlapping))).all()} if overlapping else set()
        if selected_class_ids & old_ids:
            fail('Já existe grade oficial com vigência sobreposta para esta turma.')
    existing=[]
    for p in current:
        for l in db.scalars(select(PublishedLesson).where(PublishedLesson.tenant_id==tenant_id,
                PublishedLesson.publication_id==p.id)).all():
            existing.extend(_events([{'school_id':l.school_id,'class_id':l.class_id,
                'teacher_id':l.teacher_id,'resource_id':l.resource_id,
                'weekday':l.weekday,'start_minute':l.start_minute,'end_minute':l.end_minute,
                'students':l.students}],schools,max(p.valid_from.date(),week_start),min(p.valid_to.date(),week_end),
                max_events=MAX_OCCURRENCES-len(existing)))
    fresh=_events(new_rows,schools,body.valid_from,body.valid_to,
                  max_events=MAX_OCCURRENCES-len(existing))
    matrix={(x.from_school_id,x.to_school_id):x.minutes for x in db.scalars(select(SchoolTravelTime).where(SchoolTravelTime.tenant_id==tenant_id)).all()}
    res_ids={(e['school_id'],e['resource_id']) for e in fresh+existing if e['resource_id']}
    resources={(r.school_id,r.id):r for r in db.scalars(select(SchoolResource).where(SchoolResource.tenant_id==tenant_id)).all() if (r.school_id,r.id) in res_ids}
    resource_events=_check_published_conflicts(fresh,existing,schools,matrix)
    _validate_resources(resource_events,resources)
    # Limites docentes consolidados entre todas as escolas da organização,
    # sempre por data local da unidade; vários turnos contam no mesmo dia.
    daily=defaultdict(int); weekly=defaultdict(int)
    for e in fresh+existing:
        d=e['start_utc'].astimezone(ZoneInfo(schools[e['school_id']].timezone)).date()
        daily[(e['teacher_id'],d)]+=1
        weekly[(e['teacher_id'],d.isocalendar().year,d.isocalendar().week)]+=1
    for lim in db.scalars(select(TeacherLimit).where(TeacherLimit.tenant_id==tenant_id)).all():
        for (tid,d),n in daily.items():
            if tid==lim.teacher_id and d.weekday()==lim.weekday and n>lim.max_lessons:
                fail('Limite diário docente ultrapassado entre unidades.')
    for lim in db.scalars(select(TeacherWeeklyLimit).where(TeacherWeeklyLimit.tenant_id==tenant_id)).all():
        if any(tid==lim.teacher_id and n>lim.max_lessons for (tid,_,_),n in weekly.items()):
            fail('Limite semanal docente ultrapassado entre unidades.')
    return len(existing), len(fresh)


def _preflight(db,user,tenant_id,body):
    schools, sections, rows=_prepare(db,user,tenant_id,body)
    previous,occurrences=_build_events(db,tenant_id,body,schools,rows)
    return schools,sections,rows,{'eligible':True,'lessons':len(rows),'dated_occurrences':occurrences,
        'existing_occurrences_compared':previous, 'schools':len(set(p.school_id for p,_,_ in sections)),
        'partial':any(p for _,_,p in sections),'date_from':body.valid_from.isoformat(),
        'date_to':body.valid_to.isoformat(),
        'warning':'Pré-validação não reserva horário; publicação exige nova checagem transacional em PostgreSQL.'}


@router.post('/preflight')
def preflight(tenant_id:str,body:PublicationRequest,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return _preflight(db,user,tenant_id,body)[-1]


@router.post('/publish', status_code=201)
def publish(tenant_id:str,body:PublicationRequest,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request)
    if db.get_bind().dialect.name!='postgresql':
        raise HTTPException(503,'Publicação oficial disponível somente após validação com PostgreSQL/RLS.')
    from .runtime_checks import verify_database_isolation
    verify_database_isolation(db.get_bind())
    bind_context(db,user.id,tenant_id)
    # Um advisory lock por tenant serializa TODOS os lotes concorrentes da organização,
    # inclusive professores e recursos que atravessam suas unidades.
    key=int.from_bytes(hashlib.sha256(tenant_id.encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':key})
    schools,sections,rows,report=_preflight(db,user,tenant_id,body)
    batch_id=str(uuid4())
    selected_to_publication={}
    for proposal,part,partial in sections:
        pub=PublishedGrade(tenant_id=tenant_id,school_id=part.school_id,
            academic_year_id=proposal.academic_year_id,proposal_id=proposal.id,
            batch_id=batch_id,valid_from=datetime.combine(body.valid_from,time()),
            valid_to=datetime.combine(body.valid_to,time()),
            partial=partial,justification=body.exceptional_justification.strip() if partial else None,
            published_by=user.id)
        db.add(pub);db.flush()
        for cid in part.class_ids:
            selected_to_publication[cid]=pub.id
            db.add(PublishedClass(tenant_id=tenant_id, school_id=part.school_id,
                                  publication_id=pub.id, class_id=cid))
    for r in rows:
        db.add(PublishedLesson(**r, publication_id=selected_to_publication[r['class_id']]))
    audit(db,user,tenant_id,'grades.published','publication_batch',batch_id,
          schools=[p.school_id for p,_,_ in sections],classes=len(selected_to_publication),
          lessons=len(rows),partial=report['partial'],from_date=report['date_from'],to_date=report['date_to'])
    db.commit()
    return {'batch_id':batch_id,**report,'warning':'Publicação registrada; alterações exigem nova versão sem sobrescrever histórico.'}


@router.get('')
def list_publications(tenant_id:str,school_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    authorize(db,user,tenant_id,'grades.read',school_id)
    rows=db.scalars(select(PublishedGrade).where(PublishedGrade.tenant_id==tenant_id,
        PublishedGrade.school_id==school_id).order_by(PublishedGrade.published_at.desc()).limit(100)).all()
    return [{'id':p.id,'batch_id':p.batch_id,'school_id':p.school_id,'valid_from':p.valid_from.date().isoformat(),
             'valid_to':p.valid_to.date().isoformat(),'partial':p.partial,
             'published_at':p.published_at.isoformat()} for p in rows]


@router.put('/travel/{from_school_id}')
def set_travel(tenant_id:str,from_school_id:str,data:TravelPayload,request:Request,
               db:Session=Depends(get_db),user:User=Depends(current_user)):
    require_csrf(request)
    for sid in (from_school_id,data.destination_school_id):
        authorize(db,user,tenant_id,'planning.write',sid,write=True)
        if not db.scalar(select(School.id).where(School.tenant_id==tenant_id,School.id==sid,School.is_active.is_(True))):
            fail('Unidade não encontrada.',404)
    if from_school_id==data.destination_school_id:
        fail('Tempo entre a mesma unidade não precisa de configuração.',422)
    item=db.scalar(select(SchoolTravelTime).where(SchoolTravelTime.tenant_id==tenant_id,
        SchoolTravelTime.from_school_id==from_school_id,
        SchoolTravelTime.to_school_id==data.destination_school_id))
    if item:item.minutes=data.minutes
    else:
        item=SchoolTravelTime(tenant_id=tenant_id,from_school_id=from_school_id,
                              to_school_id=data.destination_school_id,minutes=data.minutes)
        db.add(item)
    db.flush()
    audit(db,user,tenant_id,'travel.configured','school_travel_time',item.id,
        from_school=from_school_id,to_school=data.destination_school_id,minutes=data.minutes)
    db.commit()
    return {'from_school_id':from_school_id,'to_school_id':data.destination_school_id,'minutes':item.minutes}


@router.get('/{publication_id}')
def get_published(tenant_id:str,publication_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    bind_context(db,user.id,tenant_id)
    p=db.scalar(select(PublishedGrade).where(PublishedGrade.tenant_id==tenant_id,
                                                PublishedGrade.id==publication_id))
    if not p:fail('Publicação não encontrada.',404)
    authorize(db,user,tenant_id,'grades.read',p.school_id)
    grades=db.scalars(select(PublishedLesson).where(PublishedLesson.tenant_id==tenant_id,
        PublishedLesson.publication_id==publication_id).order_by(PublishedLesson.class_id,
        PublishedLesson.weekday,PublishedLesson.period_position)).all()
    classes=db.scalars(select(PublishedClass).where(PublishedClass.tenant_id==tenant_id,
        PublishedClass.publication_id==publication_id)).all()
    proposal=db.scalar(select(GradeProposal).where(GradeProposal.tenant_id==tenant_id,GradeProposal.id==p.proposal_id))
    class_ids={c.class_id for c in classes}
    return {'id':p.id,'batch_id':p.batch_id,'school_id':p.school_id,
        'valid_from':p.valid_from.date().isoformat(),'valid_to':p.valid_to.date().isoformat(),
        'partial':p.partial,'justification':p.justification,
        'classes':sorted(class_ids),'published_at':p.published_at.isoformat(),
        'pending':[r for r in (proposal.snapshot.get('pending',[]) if proposal else [])
                   if r.get('class_id') in class_ids],
        'lessons':[{'class_id':l.class_id,'teacher_id':l.teacher_id,
            'resource_id':l.resource_id,'subject':l.subject,'day':WEEKDAYS[l.weekday],
            'period':l.period_position,'start':f'{l.start_minute//60:02}:{l.start_minute%60:02}',
            'end':f'{l.end_minute//60:02}:{l.end_minute%60:02}'} for l in grades]}


@router.get('/{publication_id}/export.csv')
def export_published_csv(tenant_id:str,publication_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    body=get_published(tenant_id,publication_id,db,user)
    out=io.StringIO();w=csv.writer(out,lineterminator='\r\n')
    w.writerow(['HORÁRIO OFICIAL','Vigência:',body['valid_from'],'a',body['valid_to']])
    w.writerow(['Publicação:',body['id'],'PARCIAL COM PENDÊNCIAS' if body['partial'] else 'COMPLETA'])
    w.writerow(['Turma ID','Dia','Aula','Início','Fim','Disciplina','Professor ID'])
    for r in body['lessons']:
        w.writerow([safe_csv(r.get(k)) for k in ('class_id','day','period','start','end','subject','teacher_id')])
    if body['pending']:
        w.writerow([]);w.writerow(['PENDÊNCIAS'])
        for r in body['pending']:
            w.writerow([safe_csv(str(r.get(k,''))) for k in ('class_name','subject','teacher_name','missing','reason')])
    return Response(content=('\ufeff'+out.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="grade-oficial-{publication_id}.csv"'})


@router.get('/{publication_id}/export.pdf')
def export_published_pdf(tenant_id:str,publication_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    """PDF A4 paisagem somente para grade publicada e usuário autorizado."""
    body=get_published(tenant_id,publication_id,db,user)
    from .official_report import render_official_pdf
    school=db.scalar(select(School).where(School.tenant_id==tenant_id,School.id==body['school_id']))
    classes=db.scalars(select(SchoolClass).where(
        SchoolClass.tenant_id==tenant_id,SchoolClass.id.in_(body['classes']))).all()
    teachers=db.scalars(select(Teacher).where(
        Teacher.tenant_id==tenant_id,
        Teacher.id.in_([r['teacher_id'] for r in body['lessons']]))).all()
    pdf=render_official_pdf(body,school.name if school else 'Escola',
        {c.id:c.name for c in classes},{t.id:t.name for t in teachers})
    return Response(content=pdf,media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="grade-oficial-{publication_id}.pdf"'})


@router.get('/{publication_id}/export.xlsx')
def export_published_xlsx(tenant_id:str,publication_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    """Planilha oficial por turma; mesmos controles de autorização do PDF."""
    body=get_published(tenant_id,publication_id,db,user)
    from .official_xlsx import render_official_xlsx
    school=db.scalar(select(School).where(School.tenant_id==tenant_id,School.id==body['school_id']))
    classes=db.scalars(select(SchoolClass).where(
        SchoolClass.tenant_id==tenant_id,SchoolClass.id.in_(body['classes']))).all()
    teachers=db.scalars(select(Teacher).where(
        Teacher.tenant_id==tenant_id,
        Teacher.id.in_([r['teacher_id'] for r in body['lessons']]))).all()
    excel=render_official_xlsx(body,school.name if school else 'Escola',
        {c.id:c.name for c in classes},{t.id:t.name for t in teachers})
    return Response(content=excel,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={
        'Content-Disposition':f'attachment; filename="grade-oficial-{publication_id}.xlsx"',
        'Cache-Control':'private, no-store'})
