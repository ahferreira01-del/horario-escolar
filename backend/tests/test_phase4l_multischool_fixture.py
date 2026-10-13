"""Cenário sintético de múltiplas turmas, escolas, professor compartilhado e laboratório.

Não é teste de carga nem certificação de desempenho. Garante que o conjunto
de regras não se contradiz num cenário maior do que o mínimo escolar.
"""
from collections import Counter

from app.solver_preview import all_grid, validate_solution


def multischool_fixture():
    weekdays=['Seg','Ter','Qua','Qui']
    def slots(start,end):
        return [
            {'day':day,'order':1,'start':start,'end':end,'shift':'manha' if start<'12:00' else 'tarde'}
            for day in weekdays
        ]
    schools={sid:{'organization_id':'tenant'} for sid in ('Centro','Norte')}
    classes={}
    for school, names, st, en in [
        ('Centro',('C1','C2','C3'),'07:10','07:55'),
        ('Norte',('N1','N2','N3'),'13:00','13:45'),
    ]:
        for name in names:
            classes[name]={'school_id':school,'students':20,'slots':slots(st,en)}
    teachers={
        name:{
            'organization_id':'tenant',
            'availability':[{'day':day,'start':'07:00','end':'16:00'} for day in weekdays],
            'weekly_limit':3,'daily_limits':{day:2 for day in weekdays}
        }
        for name in ('ProfA','ProfB')
    }
    resources={'LabCentro':{
        'school_id':'Centro','max_groups':1,'max_students':25,
        'availability':[{'day':day,'start':'07:00','end':'12:00'} for day in weekdays]
    }}
    loads=[
        ('C1','ProfA','LabCentro'),
        ('C2','ProfB','LabCentro'),
        ('C3','ProfB',None),
        ('N1','ProfA',None),
        ('N2','ProfA',None),
        ('N3','ProfB',None),
    ]
    data={
        'organization_id':'tenant','mode':'lessons',
        'schools':schools,'classes':classes,'teachers':teachers,'resources':resources,
        'travel_minutes':{'Centro->Norte':35,'Norte->Centro':35},
        'demands':[
            {'class_id':cls,'subject':'Matematica','teacher_id':teacher,
             'lessons':1,'resource_id':resource,'max_consecutive':2}
            for cls,teacher,resource in loads
        ],
        'profile':'equilibrado','time_limit':5,
    }
    return data


def test_synthetic_two_schools_six_classes_shared_teachers_and_lab():
    data=multischool_fixture()
    result=all_grid(data)
    assert result['result']=='complete',result
    assert result['total_required']==result['total_assigned']==6
    assert result['conflicts']==0
    assert validate_solution(data,result['assignments'])==[]
    assert Counter(a['school_id'] for a in result['assignments'])=={'Centro':3,'Norte':3}
    assert {a['school_id'] for a in result['assignments'] if a['teacher']=='ProfA'}=={'Centro','Norte'}
    assert {a['school_id'] for a in result['assignments'] if a['teacher']=='ProfB'}=={'Centro','Norte'}
