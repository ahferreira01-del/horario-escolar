import copy
import json
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from solver import all_grid, validate_solution

def full():
    return json.loads((ROOT/'exemplo_duas_escolas.json').read_text(encoding='utf-8'))

def one_slot(st='08:00', en='08:45', school='Centro',students=20):
    return dict(school_id=school,students=students,slots=[dict(day='Seg',order=1,start=st,end=en,shift='manha')])

def mini_two_schools(a_end='08:45', b_start='08:55', minutes=20):
    data=dict(mode='lessons',organization_id='org',profile='equilibrado',time_limit=3,
        schools={'Centro':{'organization_id':'org'},'Norte':{'organization_id':'org'}},
        classes={'A':one_slot('08:00',a_end), 'B':one_slot(b_start,'09:40',school='Norte')},
        teachers={'P':{'organization_id':'org','availability':[dict(day='Seg',start='07:00',end='12:00')], 'weekly_limit':2}},
        resources={},travel_minutes={'Centro->Norte':minutes,'Norte->Centro':minutes},
        demands=[dict(class_id='A',subject='Mat',teacher_id='P',lessons=1),
                 dict(class_id='B',subject='Mat',teacher_id='P',lessons=1)])
    return data

def mini_resource(max_groups=2,max_students=50,ns=(20,20)):
    school={'organization_id':'org'}
    data={'organization_id':'org','mode':'lessons','profile':'equilibrado', 'time_limit':3,
          'schools':{'Centro':school},
          'classes':{'A':one_slot(students=ns[0]),'B':one_slot(students=ns[1])},
          'teachers':{'P':{'organization_id':'org','availability':[dict(day='Seg',start='07:00',end='12:00')],'weekly_limit':1},
                      'Q':{'organization_id':'org','availability':[dict(day='Seg',start='07:00',end='12:00')],'weekly_limit':1}},
          'resources':{'LAB':{'school_id':'Centro','max_groups':max_groups,'max_students':max_students,'availability':[dict(day='Seg',start='07:00',end='12:00')]}},
          'demands':[dict(class_id='A',subject='Ciencias',teacher_id='P',lessons=1,resource_id='LAB'),
                     dict(class_id='B',subject='Ciencias',teacher_id='Q',lessons=1,resource_id='LAB')]}
    return data

def test_cenario_completo_duas_escolas_professor_compartilhado():
    data=full();r=all_grid(data)
    assert (r['total_assigned'],r['total_required'])==(28,28)
    assert r['result']=='complete' and r['coverage_proven_optimal']
    assert r['teacher_metrics']['Paulo']['lessons']==11
    assert set(a['school_id'] for a in r['assignments'] if a['teacher']=='Paulo')=={'Centro','Norte'}
    assert validate_solution(data,r['assignments'])==[]

def test_parcial_disponibilidade_real_1045_1200():
    data=json.loads((ROOT/'exemplo_disponibilidade_incompativel.json').read_text(encoding='utf-8'))
    r=all_grid(data)
    assert r['result']=='partial' and r['total_assigned']==17 and r['total_required']==28
    assert sum(p['missing'] for p in r['pending'])==11
    assert all(p['teacher']=='Paulo' for p in r['pending'])

def test_deslocamento_rejeita_dez_minutos_quando_precisa_vinte():
    data=mini_two_schools();r=all_grid(data)
    assert r['total_assigned']==1 and r['coverage_proven_optimal']

def test_deslocamento_permite_quando_gap_e_suficiente():
    data=mini_two_schools(b_start='09:05');r=all_grid(data)
    assert r['total_assigned']==2

def test_deslocamento_direcional_nao_configurado_nao_e_zero():
    data=mini_two_schools();del data['travel_minutes']['Norte->Centro']
    with pytest.raises(ValueError,match='Deslocamento não configurado'):all_grid(data)

def test_limite_turmas_recurso():
    data=mini_resource(max_groups=1,max_students=99)
    assert all_grid(data)['total_assigned']==1

def test_limite_alunos_recurso_mesmo_com_duas_turmas_permitidas():
    data=mini_resource(max_groups=2,max_students=30,ns=(20,20))
    assert all_grid(data)['total_assigned']==1

def test_recurso_permite_dois_quando_ambos_limites_sao_suficientes():
    data=mini_resource(max_groups=2,max_students=50)
    assert all_grid(data)['total_assigned']==2

def test_disponibilidade_recurso_bloqueia_periodo():
    data=mini_resource(max_groups=2,max_students=50)
    data['resources']['LAB']['availability']=[dict(day='Seg',start='10:45',end='12:00')]
    assert all_grid(data)['total_assigned']==0

def test_segregacao_nao_aceita_dados_de_outro_tenant():
    data=full();data['schools']['Norte']['organization_id']='outra'
    with pytest.raises(ValueError,match='outra organização'):all_grid(data)

def test_autenticidade_pesos_personalizados():
    data=full();data['profile']='personalizado'
    data['weights']={'gaps':20,'days':60,'pedagogy':10,'shifts':10}
    r=all_grid(data)
    assert r['total_assigned']==28 and r['weights']['days']==60
    data['weights']['days']=50
    with pytest.raises(ValueError,match='somando 100'):all_grid(data)

def test_limite_diario_estrito():
    data=mini_resource(max_groups=2,max_students=50)
    data['teachers']['P']['daily_limits']={'Seg':0}
    r=all_grid(data)
    assert r['total_assigned']==1

def test_recreio_nao_quebra_sequencia():
    d=mini_resource(max_groups=2,max_students=50)
    d['classes']={'A':{'school_id':'Centro','students':20,'slots':[
       dict(day='Seg',order=1,start='07:10',end='07:55',shift='manha'),
       dict(day='Seg',order=2,start='07:55',end='08:40',shift='manha'),
       dict(day='Seg',order=3,start='09:00',end='09:45',shift='manha')]}}
    d['demands']=[dict(class_id='A',subject='Mat',teacher_id='P',lessons=3,max_consecutive=2)]
    d['teachers']['P']['weekly_limit']=3
    assert all_grid(d)['total_assigned']==2

def test_validador_independente_detecta_sobreposicao_professor():
    data=mini_resource(max_groups=2,max_students=50)
    d1=all_grid(data)['assignments']
    d2=copy.deepcopy(d1)
    d2[1]['teacher']=d2[0]['teacher']
    assert any('Sobreposição professor' in x for x in validate_solution(data,d2))

def test_validador_independente_detecta_capacidade_alunos():
    d=mini_resource(max_groups=2,max_students=50)
    assigned=all_grid(d)['assignments']
    d['resources']['LAB']['max_students']=30
    assert any('Alunos no recurso' in x for x in validate_solution(d,assigned))

def test_sem_disponibilidade_nenhuma_nao_explode():
    d=mini_resource();d['teachers']['P']['availability']=[];d['teachers']['Q']['availability']=[]
    r=all_grid(d)
    assert r['result']=='partial' and r['total_assigned']==0 and sum(p['missing'] for p in r['pending'])==2
