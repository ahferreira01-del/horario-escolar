"""Horário Inteligente · Fase 3 · MILP/HiGHS (CP-SAT ainda não instalado).

PROTÓTIPO: não expõe API, não autentica usuários, não publica grades.
Cobre: unidade única por execução, até várias escolas no mesmo tenant,
professores compartilhados, disponibilidade exata, limites, sequência,
transporte entre escolas, recursos (turmas/alunos), cobertura lexicográfica,
pesos de dias/janelas/evitar dia e penalidade proxy para múltiplos turnos.
Não cobre ainda: CP-SAT, workflows de aprovação, cross-tenant, RLS.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix

DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
PROFILES = {
    'equilibrado': {'gaps': 40, 'days': 30, 'pedagogy': 20, 'shifts': 10},
    'menos_janelas': {'gaps': 65, 'days': 15, 'pedagogy': 10, 'shifts': 10},
    'menos_dias': {'gaps': 15, 'days': 65, 'pedagogy': 10, 'shifts': 10},
}

def minute(s):
    parts = s.split(':')
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f'Horário inválido: {s}')
    h, m = map(int, parts)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f'Horário inválido: {s}')
    return h*60+m

def display(n):
    return f'{n//60:02d}:{n%60:02d}'

def fits(day, start, end, ranges):
    return any(item['day'] == day and minute(item['start']) <= start and end <= minute(item['end']) for item in ranges)

def overlaps(a, b):
    return a['start'] < b['end'] and b['start'] < a['end']

def travel_minutes(travel, a, b):
    if a == b:
        return 0
    key = f'{a}->{b}'
    if key not in travel:
        raise ValueError(f'Deslocamento não configurado para {key}; não se presume zero.')
    value = travel[key]
    if type(value) is not int or value < 0 or value > 1440:
        raise ValueError(f'Deslocamento inválido: {key}')
    return value

class MILP:
    def __init__(self):
        self.names=[]; self.constraints=[]
    def var(self, name):
        idx=len(self.names); self.names.append(name); return idx
    def add(self, terms, low=-np.inf, high=np.inf):
        self.constraints.append(({int(k):float(v) for k,v in terms.items() if v},float(low),float(high)))
    def solve(self, costs, time_limit):
        nr=len(self.constraints); nc=len(self.names)
        rows=[]; cols=[]; values=[]; lb=[]; ub=[]
        for r,(terms,low,high) in enumerate(self.constraints):
            lb.append(low); ub.append(high)
            for j, value in terms.items():
                rows.append(r);cols.append(j);values.append(value)
        A=coo_matrix((values,(rows,cols)),shape=(nr,nc)).tocsr()
        c=np.zeros(nc)
        for j,w in costs.items(): c[j]=w
        return milp(c,integrality=np.ones(nc),bounds=Bounds(np.zeros(nc),np.ones(nc)),
                    constraints=LinearConstraint(A,np.array(lb),np.array(ub)),
                    options={'time_limit':float(time_limit),'mip_rel_gap':0.0})

def check_input(data):
    if data.get('mode','lessons') not in ('lessons','mixed'):
        raise ValueError('Modo inválido; usar lessons ou mixed.')
    org=data.get('organization_id')
    if not isinstance(org,str) or not org:
        raise ValueError('organization_id obrigatório; uma organização por execução.')
    schools=data.get('schools',{}); classes=data.get('classes',{});
    teachers=data.get('teachers',{}); demands=data.get('demands',[])
    resources=data.get('resources',{}); travel=data.get('travel_minutes',{})
    if not schools or not classes or not teachers or not demands:
        raise ValueError('Cadastrar ao menos uma escola, turma, professor e demanda.')
    for sid, s in schools.items():
        if s.get('organization_id') != org:
            raise ValueError(f'Escola {sid} pertence a outra organização.')
    for t, cfg in teachers.items():
        if cfg.get('organization_id') != org:
            raise ValueError(f'Professor {t} pertence a outra organização.')
        for av in cfg.get('availability',[]):
            if av['day'] not in DAYS or minute(av['start']) >= minute(av['end']):
                raise ValueError(f'Disponibilidade inválida para {t}')
        for x in cfg.get('daily_limits',{}).values():
            if type(x) is not int or x<0: raise ValueError('Limite diário inválido')
        x=cfg.get('weekly_limit',0)
        if type(x) is not int or x<0: raise ValueError('Limite semanal inválido')
    periods={}
    for cls,cfg in classes.items():
        if cfg.get('school_id') not in schools: raise ValueError(f'Escola desconhecida da turma {cls}')
        n=cfg.get('students')
        if type(n) is not int or n<0: raise ValueError(f'Tamanho inválido da turma {cls}')
        slots=[]
        for slot in cfg.get('slots',[]):
            if slot['day'] not in DAYS: raise ValueError('Dia inválido')
            s,e=minute(slot['start']),minute(slot['end'])
            if not s<e: raise ValueError('Período de turma inválido')
            if not isinstance(slot.get('shift'),str) or not slot['shift']:
                raise ValueError('Todo período precisa de shift, ex.: manha/tarde')
            slots.append(dict(slot,start_min=s,end_min=e))
        if not slots: raise ValueError(f'Turma {cls} sem períodos')
        for day in {s['day'] for s in slots}:
            subset=sorted((s for s in slots if s['day']==day),key=lambda x:x['order'])
            if len({s['order'] for s in subset})!=len(subset): raise ValueError('Ordem duplicada de aula')
            for x,y in zip(subset,subset[1:]):
                if x['end_min']>y['start_min']: raise ValueError('Períodos sobrepostos na mesma turma')
        periods[cls]=slots
    for rid,r in resources.items():
        if r.get('school_id') not in schools: raise ValueError(f'Recurso {rid} com escola inválida')
        for k in ('max_groups','max_students'):
            if type(r.get(k)) is not int or r[k]<1: raise ValueError(f'Capacidade inválida de {rid}: {k}')
        for av in r.get('availability',[]):
            if av['day'] not in DAYS or minute(av['start'])>=minute(av['end']):
                raise ValueError(f'Disponibilidade inválida de recurso {rid}')
    seen=set()
    for index,d in enumerate(demands):
        cls=d.get('class_id'); t=d.get('teacher_id'); subj=d.get('subject')
        if cls not in classes or t not in teachers or not subj:
            raise ValueError(f'Demanda {index} com turma/professor/disciplina inválida')
        unit=d.get('unit','lessons')
        if unit not in ('lessons','minutes'): raise ValueError('Unidade inválida da demanda')
        if unit=='lessons':
            if type(d.get('lessons')) is not int or d['lessons'] < 0:
                raise ValueError('Quantidade de aulas deve ser inteira >= 0')
        else:
            target=d.get('target_minutes'); low=d.get('min_minutes') if d.get('min_minutes') is not None else target; high=d.get('max_minutes') if d.get('max_minutes') is not None else target
            if any(type(x) is not int or not 1<=x<=2000 for x in (target,low,high)) or not low<=target<=high:
                raise ValueError('Faixa de minutos inválida; requer mínimo <= meta <= máximo.')
        if d.get('max_consecutive',2) not in (1,2):
            raise ValueError('max_consecutive só aceita 1 ou 2')
        if d.get('resource_id') is not None:
            r=resources.get(d['resource_id'])
            if not r or r['school_id']!=classes[cls]['school_id']:
                raise ValueError('Recurso obrigatório inexistente ou em outra escola')
        key=(cls,subj,t)
        if key in seen: raise ValueError(f'Linha duplicada de demanda {key}')
        seen.add(key)
    for sid in schools:
        for other in schools:
            if sid!=other and f'{sid}->{other}' in travel:
                travel_minutes(travel,sid,other)
    profile=data.get('profile','equilibrado')
    if profile=='personalizado':
        weights=data.get('weights',{})
        if set(weights)!=set(PROFILES['equilibrado']) or any(type(v) is not int or v<0 for v in weights.values()) or sum(weights.values())!=100:
            raise ValueError('Pesos personalizados devem conter gaps/days/pedagogy/shifts, inteiros >=0 somando 100.')
    elif profile not in PROFILES: raise ValueError('Perfil desconhecido')
    # Deslocamentos entre escolas só exigidos quando docente tem demandas em ambas.
    for t in teachers:
        linked={classes[d['class_id']]['school_id'] for d in demands if d['teacher_id']==t}
        for a in linked:
            for b in linked:
                if a!=b: travel_minutes(travel,a,b)
    return periods

def all_grid(data):
    slots=check_input(data)
    teachers=data['teachers']; classes=data['classes']; demands=data['demands']
    resources=data.get('resources',{}); travel=data.get('travel_minutes',{})
    profile=data.get('profile','equilibrado')
    weights=(data['weights'] if profile=='personalizado' else PROFILES[profile])
    mdl=MILP(); choices=[]
    by_d=defaultdict(list); by_cls_slot=defaultdict(list); by_teacher_day=defaultdict(list)
    by_resource_day=defaultdict(list); by_cls_day_sub_slot=defaultdict(list)
    for di,d in enumerate(demands):
        cls=d['class_id']; teacher=d['teacher_id']; rid=d.get('resource_id')
        for i,slot in enumerate(slots[cls]):
            day=slot['day']; start=slot['start_min']; end=slot['end_min']
            if not fits(day,start,end,teachers[teacher].get('availability',[])):continue
            if rid and not fits(day,start,end,resources[rid].get('availability',[])):continue
            var=mdl.var(f'a/{di}/{cls}/{day}/{i}')
            c=dict(var=var,demand=di,class_id=cls,school_id=classes[cls]['school_id'],
                   subject=d['subject'],teacher=teacher,day=day,order=slot['order'],
                   shift=slot['shift'],start=start,end=end,slot_index=i,resource_id=rid,
                   students=classes[cls]['students'])
            choices.append(c);by_d[di].append(var);by_cls_slot[(cls,day,i)].append(var)
            by_teacher_day[(teacher,day)].append(c)
            if rid:by_resource_day[(rid,day)].append(c)
            by_cls_day_sub_slot[(cls,day,i,d['subject'])].append(var)
    # Nunca exceder carga máxima. Mínimo de minutos define COMPLETUDE da demanda,
    # mas não restrição rígida da grade parcial: o déficit deve aparecer como pendência.
    for di,d in enumerate(demands):
        if d.get('unit','lessons')=='minutes':
            duration_by_var={c['var']:c['end']-c['start'] for c in choices if c['demand']==di}
            mdl.add(duration_by_var,high=d['max_minutes'] if d.get('max_minutes') is not None else d['target_minutes'])
        else:
            mdl.add({i:1 for i in by_d[di]},high=d['lessons'])
    for xs in by_cls_slot.values(): mdl.add({x:1 for x in xs},high=1)
    # Sobreposição de professor e deslocamento entre diferentes unidades.
    for (teacher,day),items in by_teacher_day.items():
        for ii,a in enumerate(items):
            for b in items[ii+1:]:
                if a['school_id']==b['school_id']:
                    bad=overlaps(a,b)
                elif overlaps(a,b):
                    bad=True
                else:
                    first,second=(a,b) if (a['start'],a['end'])<=(b['start'],b['end']) else (b,a)
                    bad=(first['end']+travel_minutes(travel,first['school_id'],second['school_id'])>second['start'])
                if bad:mdl.add({a['var']:1,b['var']:1},high=1)
        daily=teachers[teacher].get('daily_limits',{}).get(day)
        if daily is not None:mdl.add({x['var']:1 for x in items},high=daily)
    for teacher,cfg in teachers.items():
        mdl.add({c['var']:1 for c in choices if c['teacher']==teacher},high=cfg['weekly_limit'])
    # Capacidade: simultâneas turmas e número total de alunos por recurso.
    for (rid,day),items in by_resource_day.items():
        boundaries=sorted({v for c in items for v in (c['start'],c['end'])})
        for start,end in zip(boundaries,boundaries[1:]):
            group=[c for c in items if c['start']<end and c['end']>start]
            if len(group)>1:
                mdl.add({c['var']:1 for c in group},high=resources[rid]['max_groups'])
                mdl.add({c['var']:c['students'] for c in group},high=resources[rid]['max_students'])
            elif len(group)==1 and group[0]['students']>resources[rid]['max_students']:
                mdl.add({group[0]['var']:1},high=0)
    # Sequência por DISCIPLINA, independe do docente e recreio.
    for cls in classes:
        for subject in {d['subject'] for d in demands if d['class_id']==cls}:
            rule=min(d.get('max_consecutive',2) for d in demands if d['class_id']==cls and d['subject']==subject)
            for day in {s['day'] for s in slots[cls]}:
                ordered=sorted(((i,s) for i,s in enumerate(slots[cls]) if s['day']==day),key=lambda p:p[1]['order'])
                for j in range(len(ordered)-rule):
                    idx=[v for i,s in ordered[j:j+rule+1] for v in by_cls_day_sub_slot[(cls,day,i,subject)]]
                    if idx:mdl.add({x:1 for x in idx},high=rule)
    # Etapa 1: cobertura máxima. Ótimo global só afirmado com status 0.
    all_vars=[c['var'] for c in choices]
    if all_vars:
        # Usar cobertura relativa por demanda evita privilegiar arbitrariamente
        # cargas em minutos sobre cargas por número de aulas.
        costs={c['var']: -(c['end']-c['start'])/max(1,demands[c['demand']].get('target_minutes',1))
               if demands[c['demand']].get('unit','lessons')=='minutes'
               else -1/max(1,demands[c['demand']]['lessons']) for c in choices}
        coverage=mdl.solve(costs,data.get('time_limit',12))
        if coverage.x is None:
            return {'result':'unsolved','solver_status':str(coverage.message),'coverage_proven_optimal':False,
                    'assignments':[],'pending':[],'total_required':sum(d['lessons'] for d in demands if d.get('unit','lessons')=='lessons'),
                    'total_assigned':0,'note':'Nenhuma solução validada; tempo ou status insuficiente.'}
        # Congelar a cobertura alcançada usando o MESMO objetivo ponderado, não
        # apenas contagem bruta; assim a etapa de janelas nunca sacrifica cobertura.
        best_score=sum(-costs[i]*coverage.x[i] for i in all_vars)
        mdl.add({i:round(-costs[i]*1000000) for i in all_vars},
                low=round(best_score*1000000)-1)
    else:
        coverage=None; best=0
    # Etapa 2: penalizar dias (exatos) e janelas entre aulas em cada turno (aproximação por período).
    dayvars={}; shiftvars={}; gapvars=[]
    for (teacher,day),items in by_teacher_day.items():
        vals={c['var']:1 for c in items}
        y=mdl.var(f'day/{teacher}/{day}');dayvars[(teacher,day)]=y
        for v in vals:mdl.add({y:1,v:-1},low=0)
        mdl.add({y:1,**{v:-1 for v in vals}},high=0)
        for shift in sorted({c['shift'] for c in items}):
            xs=[c['var'] for c in items if c['shift']==shift]
            z=mdl.var(f'shift/{teacher}/{day}/{shift}');shiftvars[(teacher,day,shift)]=z
            for x in xs:mdl.add({z:1,x:-1},low=0)
            mdl.add({z:1,**{x:-1 for x in xs}},high=0)
        # Disponíveis vagos por turno: apenas espaços letivos onde o professor realmente cabe.
        shifts={c['shift'] for c in items}
        for shift in shifts:
            grid=sorted({(s['start_min'],s['end_min']) for cfg in slots.values() for s in cfg
                         if s['day']==day and s['shift']==shift and fits(day,s['start_min'],s['end_min'],teachers[teacher]['availability'])})
            subset=[c for c in items if c['shift']==shift]
            for start,end in grid:
                earlier={c['var'] for c in subset if c['end']<=start}
                later={c['var'] for c in subset if c['start']>=end}
                covering={c['var'] for c in subset if c['start']<end and c['end']>start}
                if not earlier or not later:continue
                p=mdl.var(f'earlier/{teacher}/{day}/{start}');q=mdl.var(f'later/{teacher}/{day}/{start}')
                g=mdl.var(f'gap/{teacher}/{day}/{start}')
                for x in earlier:mdl.add({p:1,x:-1},low=0)
                mdl.add({p:1,**{x:-1 for x in earlier}},high=0)
                for x in later:mdl.add({q:1,x:-1},low=0)
                mdl.add({q:1,**{x:-1 for x in later}},high=0)
                mdl.add({g:1,p:-1},high=0);mdl.add({g:1,q:-1},high=0)
                mdl.add({g:1,**{x:1 for x in covering}},high=1)
                mdl.add({g:1,p:-1,q:-1,**{x:1 for x in covering}},low=-1)
                gapvars.append((g,teacher,day,shift,start,end))
    # Proxy interturno: trabalhar em múltiplos turnos no mesmo dia custa proporcional ao total além de 1.
    cross_shift={}
    for (teacher,day),y in dayvars.items():
        shifts=[z for (t,d,shift),z in shiftvars.items() if (t,d)==(teacher,day)]
        if len(shifts)>1:
            # cada turno adicional habilita binário z; objetivo penaliza Σ shift - day
            cross_shift[(teacher,day)]=(shifts,y)
    objective={}
    for i,*_ in gapvars:objective[i]=weights['gaps']
    for i in dayvars.values():objective[i]=objective.get(i,0)+weights['days']
    for shifts,y in cross_shift.values():
        for z in shifts:objective[z]=objective.get(z,0)+weights['shifts']
        objective[y]=objective.get(y,0)-weights['shifts']
    for c in choices:
        if c['day'] in demands[c['demand']].get('avoid_days',[]):
            objective[c['var']]=objective.get(c['var'],0)+weights['pedagogy']
    if all_vars:
        optimal=mdl.solve(objective,data.get('time_limit',12))
        selected=optimal.x if optimal.x is not None else coverage.x
    else:
        optimal=None; selected=np.zeros(len(mdl.names))
    assigned=[c for c in choices if selected[c['var']]>0.5]
    output=[{k:(display(c[k]) if k in ('start','end') else c[k]) for k in
             ('class_id','school_id','subject','teacher','day','order','start','end','shift','resource_id','students')}
            for c in sorted(assigned,key=lambda a:(a['school_id'],a['class_id'],DAYS.index(a['day']),a['start']))]
    pending=[]; coverage_by_demand=[]
    for i,d in enumerate(demands):
        actual=[c for c in assigned if c['demand']==i]
        got=len(actual); actual_minutes=sum(c['end']-c['start'] for c in actual)
        unit=d.get('unit','lessons')
        required=(d['min_minutes'] if d.get('min_minutes') is not None else d['target_minutes']) if unit=='minutes' else d['lessons']
        delivered=actual_minutes if unit=='minutes' else got
        missing=max(0,required-delivered)
        coverage_by_demand.append(dict(class_id=d['class_id'],subject=d['subject'],teacher=d['teacher_id'],
                            unit=unit,required=required,delivered=delivered,missing=missing,
                            target_minutes=d.get('target_minutes') if unit=='minutes' else None,
                            minutes_scheduled=actual_minutes,lessons_scheduled=got))
        if missing:
            if not by_d[i]:reason='Nenhum período compatível com a disponibilidade docente e do recurso exigido.'
            elif unit=='lessons' and len(by_d[i])<d['lessons']:
                reason='Períodos candidatos insuficientes, mesmo antes de cruzar todos os conflitos.'
            elif unit=='minutes' and sum(sorted((c['end']-c['start'] for c in choices if c['demand']==i),reverse=True)[:len(by_d[i])])<required:
                reason='Períodos candidatos têm duração total insuficiente para a meta mínima.'
            else:reason='Demanda compete por professor/turma/recurso, deslocamento, limites ou sequência; causa exata não isolada.'
            pending.append(dict(class_id=d['class_id'],school_id=classes[d['class_id']]['school_id'],
                                subject=d['subject'],teacher=d['teacher_id'],missing=missing,unit=unit,
                                scheduled_minutes=actual_minutes,required_minutes=required if unit=='minutes' else None,
                                reason=reason))
    metrics={}
    for t in teachers:
        done=[c for c in assigned if c['teacher']==t]
        days={c['day'] for c in done}
        gaps=0; multi_shift=0
        for day in days:
            subset=[c for c in done if c['day']==day]
            multi_shift+=max(0,len({c['shift'] for c in subset})-1)
            for shift in {c['shift'] for c in subset}:
                schoolperiods=sorted({(s['start_min'],s['end_min']) for cfg in slots.values() for s in cfg
                          if s['day']==day and s['shift']==shift and fits(day,s['start_min'],s['end_min'],teachers[t]['availability'])})
                sub=[c for c in subset if c['shift']==shift]
                for st,en in schoolperiods:
                    if (any(c['end']<=st for c in sub) and any(c['start']>=en for c in sub)
                            and not any(c['start']<en and c['end']>st for c in sub)):
                        gaps+=1
        metrics[t]=dict(lessons=len(done),working_days=len(days),gap_periods=gaps,
                        additional_shifts=multi_shift)
    errors=validate_solution(data,output)
    if errors:raise RuntimeError('Falhou validação independente: '+repr(errors))
    return {'result':'complete' if not pending else 'partial',
            'solver_status':'OPTIMAL' if optimal is not None and optimal.status==0 else 'FEASIBLE' if (optimal is not None and optimal.x is not None) else 'COVERAGE_ONLY',
            'coverage_proven_optimal':True if coverage is None else coverage.status==0,
            'total_required':sum(d['lessons'] for d in demands if d.get('unit','lessons')=='lessons'),
            'total_assigned':len(assigned), 'total_assigned_minutes':sum(c['end']-c['start'] for c in assigned),
            'required_minutes':sum(d['min_minutes'] if d.get('min_minutes') is not None else d['target_minutes'] for d in demands if d.get('unit','lessons')=='minutes'),
            'minute_mode_scheduled_minutes':sum(v['minutes_scheduled'] for v in coverage_by_demand if v['unit']=='minutes'),
            'demand_coverage':coverage_by_demand,
            'pending':pending,'assignments':output,'teacher_metrics':metrics,'profile':profile,
            'weights':weights,'conflicts':0,
            'scope':'Preview: uma organização, múltiplas escolas; API verifica RBAC; sem RLS validada/publicação/cross-tenant',
            'optimizer':'SciPy HiGHS MILP; substituição por CP-SAT ainda pendente',
            'metric_note':'Gaps são períodos vazios disponíveis intraturno; additional_shifts é proxy de espera, NÃO minutos reais.'}

def validate_solution(data,assigned):
    """Verificação independente das regras implementadas, inclusive capacidade e deslocamento."""
    errors=[]
    by_cls=defaultdict(list);by_teacher=defaultdict(list);by_resource=defaultdict(list);by_demand=defaultdict(int)
    students=data['classes']; resources=data.get('resources',{}); travel=data.get('travel_minutes',{})
    # Verificação independente: uma aula deve corresponder exatamente a uma
    # atribuição cadastrada (turma, disciplina, docente e recurso obrigatório).
    # Sem esta barreira um horário sintético poderia passar nas checagens de
    # sobreposição mesmo sem atribuição docente válida.
    authorized_demand_keys={
        (d['class_id'], d['subject'], d['teacher_id'], d.get('resource_id'))
        for d in data['demands']
    }
    for a in assigned:
        cls=a['class_id'];t=a['teacher'];rid=a.get('resource_id')
        if cls not in students or t not in data['teachers']:
            errors.append('Professor/turma inexistente');continue
        school=students[cls]['school_id']
        if a['school_id']!=school:errors.append('Escola divergente')
        if (cls,a['subject'],t,rid) not in authorized_demand_keys:
            errors.append('Aula sem atribuição cadastrada para disciplina, professor e recurso')
        s,e=minute(a['start']),minute(a['end'])
        if not fits(a['day'],s,e,data['teachers'][t]['availability']):errors.append(f'Disponibilidade de {t}')
        original_slots=students[cls]['slots']
        if not any(q['day']==a['day'] and q['order']==a['order'] and q['start']==a['start'] and q['end']==a['end'] and q['shift']==a.get('shift') for q in original_slots):
            errors.append('Período não cadastrado')
        by_cls[(cls,a['day'])].append((s,e,a));by_teacher[(t,a['day'])].append((s,e,a))
        by_demand[(cls,a['subject'],t,rid)]+=1
        if rid:
            if rid not in resources or resources[rid]['school_id']!=school:
                errors.append('Recurso inválido')
            else:
                by_resource[(rid,a['day'])].append((s,e,a))
                if not fits(a['day'],s,e,resources[rid]['availability']):errors.append('Disponibilidade do recurso')
    for (cls,day),items in by_cls.items():
        for i,(s,e,a) in enumerate(items):
            for x,y,b in items[i+1:]:
                if s<y and x<e:errors.append(f'Sobreposição turma {cls} {day}')
        order=sorted((q for q in students[cls]['slots'] if q['day']==day),key=lambda x:x['order'])
        mapping={a['order']:a['subject'] for _,_,a in items}
        for subject in {d['subject'] for d in data['demands'] if d['class_id']==cls}:
            max_seq=min(d.get('max_consecutive',2) for d in data['demands'] if d['class_id']==cls and d['subject']==subject)
            for j in range(len(order)-max_seq):
                if all(mapping.get(q['order'])==subject for q in order[j:j+max_seq+1]):
                    errors.append(f'Aulas consecutivas {cls} {subject}')
    for (t,day),items in by_teacher.items():
        if len(items)>data['teachers'][t].get('daily_limits',{}).get(day,10**9):
            errors.append(f'Limite diário {t}')
        for i,(s,e,a) in enumerate(items):
            for x,y,b in items[i+1:]:
                if s<y and x<e:errors.append(f'Sobreposição professor {t}')
                elif a['school_id']!=b['school_id']:
                    first,second=((s,e,a),(x,y,b)) if s<=x else ((x,y,b),(s,e,a))
                    try:
                        travel_time=travel_minutes(travel,first[2]['school_id'],second[2]['school_id'])
                        if first[1]+travel_time>second[0]:errors.append(f'Deslocamento {t} {day}')
                    except ValueError:errors.append('Deslocamento ausente')
    for t,config in data['teachers'].items():
        if sum(1 for a in assigned if a['teacher']==t)>config['weekly_limit']:
            errors.append(f'Limite semanal {t}')
    for d in data['demands']:
        k=(d['class_id'],d['subject'],d['teacher_id'],d.get('resource_id'))
        if d.get('unit','lessons')=='minutes':
            total=sum(minute(a['end'])-minute(a['start']) for a in assigned
                      if (a['class_id'],a['subject'],a['teacher'],a.get('resource_id'))==k)
            if total>(d['max_minutes'] if d.get('max_minutes') is not None else d['target_minutes']):errors.append(f'Excedeu máximo de minutos {k}')
        elif by_demand[k]>d['lessons']:errors.append(f'Excedeu cota {k}')
    for (rid,day),items in by_resource.items():
        edges=sorted({v for s,e,a in items for v in [s,e]})
        for st,en in zip(edges,edges[1:]):
            used=[a for s,e,a in items if s<en and e>st]
            if len(used)>resources[rid]['max_groups']:errors.append(f'Turmas no recurso {rid}')
            if sum(students[a['class_id']]['students'] for a in used)>resources[rid]['max_students']:
                errors.append(f'Alunos no recurso {rid}')
    return errors

def main():
    p=argparse.ArgumentParser(description='Horário Inteligente PoC v0.2')
    p.add_argument('input',type=Path);p.add_argument('--out',type=Path,default=Path('resultado.json'))
    p.add_argument('--csv',type=Path,default=Path('grade.csv'))
    args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    result=all_grid(data)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with args.csv.open('w',newline='',encoding='utf-8-sig') as f:
        fields=['school_id','class_id','day','order','start','end','shift','subject','teacher','resource_id','students']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(result['assignments'])
    print(f"{result['result']}: {result['total_assigned']} aulas agendadas "
          f"({result['total_required']} exigidas por contagem); "
          f"{result.get('minute_mode_scheduled_minutes',0)}/{result.get('required_minutes',0)} "
          f"minutos em demandas por duração | {result.get('solver_status')}")
    print('Pendentes:',sum(v['missing'] for v in result['pending']))

if __name__=='__main__':main()
