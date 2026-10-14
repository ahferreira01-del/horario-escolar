"""Fase 4L: o validador do gerador não deve aceitar aulas fabricadas.

Este teste usa a função pura (sem dependência de banco) e não altera
cadastros, dados reais ou workflow CI.
"""
import copy
from app.solver_preview import validate_solution


def fixture():
    data={
        'organization_id':'org', 'mode':'lessons',
        'schools':{'Centro':{'organization_id':'org'}},
        'classes':{'6A':{'school_id':'Centro','students':25,'slots':[
            {'day':'Seg','order':1,'start':'07:10','end':'07:55','shift':'manha'}
        ]}},
        'teachers':{'P':{'organization_id':'org','availability':[
            {'day':'Seg','start':'07:00','end':'12:00'}
        ],'weekly_limit':2}},
        'resources':{},'travel_minutes':{},
        'demands':[{'class_id':'6A','subject':'Matematica','teacher_id':'P','lessons':1}]
    }
    assignment={'class_id':'6A','school_id':'Centro','subject':'Matematica',
        'teacher':'P','day':'Seg','order':1,'start':'07:10','end':'07:55',
        'shift':'manha','resource_id':None,'students':25}
    return data, assignment


def test_valid_assignment_is_accepted():
    data, assignment=fixture()
    assert validate_solution(data,[assignment]) == []


def test_unknown_subject_is_rejected_even_without_collision():
    data, assignment=fixture()
    assignment['subject']='Disciplina inventada'
    assert any('atribuição cadastrada' in msg for msg in validate_solution(data,[assignment]))


def test_different_teacher_is_not_a_valid_assignment():
    data, assignment=fixture()
    data['teachers']['Q']=copy.deepcopy(data['teachers']['P'])
    assignment['teacher']='Q'
    assert any('atribuição cadastrada' in msg for msg in validate_solution(data,[assignment]))


def test_wrong_shift_is_rejected_for_same_class_period():
    data, assignment=fixture()
    assignment['shift']='tarde'
    assert any('Período não cadastrado' in msg for msg in validate_solution(data,[assignment]))


def test_required_resource_must_match_the_assignment():
    data, assignment=fixture()
    data['resources']['LAB']={
        'school_id':'Centro','max_groups':1,'max_students':30,
        'availability':[{'day':'Seg','start':'07:00','end':'12:00'}]
    }
    data['demands'][0]['resource_id']='LAB'
    assert any('atribuição cadastrada' in msg for msg in validate_solution(data,[assignment]))
