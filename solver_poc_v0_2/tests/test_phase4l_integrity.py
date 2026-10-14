"""Fase 4L — verificação independente do protótipo legado.

O validador não pode aceitar aulas que não fazem parte das demandas,
nem a troca silenciosa do turno do período.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from solver import validate_solution


def example():
    data={'organization_id':'org', 'mode':'lessons',
        'schools':{'Centro':{'organization_id':'org'}},
        'classes':{'A':{'school_id':'Centro','students':25,'slots':[
            dict(day='Seg',order=1,start='07:10',end='07:55',shift='manha')]}},
        'teachers':{'P':{'organization_id':'org',
            'availability':[dict(day='Seg',start='07:00',end='12:00')], 'weekly_limit':2}},
        'resources':{},'travel_minutes':{},
        'demands':[dict(class_id='A',subject='Matematica',teacher_id='P',lessons=1)]}
    row=dict(class_id='A',school_id='Centro',subject='Matematica',teacher='P',
             day='Seg',order=1,start='07:10',end='07:55',shift='manha',
             resource_id=None,students=25)
    return data,row


def test_legitimate_row_passes():
    data,row=example()
    assert validate_solution(data,[row]) == []


def test_invented_subject_is_rejected():
    data,row=example()
    row['subject']='Inventada'
    assert any('atribuição cadastrada' in x for x in validate_solution(data,[row]))


def test_teacher_swap_is_rejected():
    data,row=example()
    data['teachers']['Q']=copy.deepcopy(data['teachers']['P'])
    row['teacher']='Q'
    assert any('atribuição cadastrada' in x for x in validate_solution(data,[row]))


def test_wrong_shift_cannot_pass_as_valid_slot():
    data,row=example()
    row['shift']='noturno'
    assert any('Período não cadastrado' in x for x in validate_solution(data,[row]))


def test_required_resource_cannot_be_dropped():
    data,row=example()
    data['resources']['Lab']=dict(school_id='Centro',max_groups=1,max_students=30,
        availability=[dict(day='Seg',start='07:00',end='12:00')])
    data['demands'][0]['resource_id']='Lab'
    assert any('atribuição cadastrada' in x for x in validate_solution(data,[row]))
