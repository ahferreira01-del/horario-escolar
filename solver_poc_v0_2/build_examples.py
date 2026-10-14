import copy,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
DAYS=['Seg','Ter','Qua','Qui','Sex']
def slots(times,shift):
    return [dict(day=d,order=j+1,start=s,end=e,shift=shift) for d in DAYS for j,(s,e) in enumerate(times)]
morning=[('07:10','07:55'),('07:55','08:40'),('09:00','09:45'),('09:55','10:40')]
afternoon=[('13:00','13:45'),('13:45','14:30'),('14:50','15:35'),('15:45','16:30')]
def availability(start,end):return [dict(day=d,start=start,end=end) for d in DAYS]
data={
 'mode':'lessons','organization_id':'RedeAlfa', 'profile':'equilibrado','time_limit':10,
 'schools':{'Centro':{'organization_id':'RedeAlfa'},'Norte':{'organization_id':'RedeAlfa'}},
 'classes':{
    '6A':{'school_id':'Centro','students':25,'slots':slots(morning,'manha')},
    '6B':{'school_id':'Centro','students':26,'slots':slots(morning,'manha')},
    '7A':{'school_id':'Norte','students':27,'slots':slots(afternoon,'tarde')}
 },
 'teachers':{
    'Paulo':{'organization_id':'RedeAlfa','availability':availability('07:00','17:30'), 'weekly_limit':12,'daily_limits':{d:5 for d in DAYS}},
    'Luiza':{'organization_id':'RedeAlfa','availability':availability('07:00','10:40'), 'weekly_limit':8,'daily_limits':{d:3 for d in DAYS}},
    'Clara':{'organization_id':'RedeAlfa','availability':availability('07:00','10:40'), 'weekly_limit':6,'daily_limits':{d:3 for d in DAYS}},
    'Ana':{'organization_id':'RedeAlfa','availability':availability('13:00','16:30'), 'weekly_limit':6,'daily_limits':{d:3 for d in DAYS}},
    'Beto':{'organization_id':'RedeAlfa','availability':availability('13:00','16:30'), 'weekly_limit':4,'daily_limits':{d:2 for d in DAYS}}
 },
 'resources':{
    'LabCentro':{'school_id':'Centro','max_groups':1,'max_students':30,'availability':availability('07:00','10:40')},
    'LabNorte':{'school_id':'Norte','max_groups':1,'max_students':30,'availability':availability('13:00','16:30')}
 },
 'travel_minutes':{'Centro->Norte':25,'Norte->Centro':35},
 'demands':[
    {'class_id':'6A','subject':'Matemática','teacher_id':'Paulo','lessons':4,'max_consecutive':2},
    {'class_id':'6A','subject':'Português','teacher_id':'Luiza','lessons':4,'max_consecutive':2},
    {'class_id':'6A','subject':'Ciências','teacher_id':'Clara','lessons':2,'max_consecutive':1,'resource_id':'LabCentro'},
    {'class_id':'6B','subject':'Matemática','teacher_id':'Paulo','lessons':3,'max_consecutive':2},
    {'class_id':'6B','subject':'Português','teacher_id':'Luiza','lessons':3,'max_consecutive':2},
    {'class_id':'6B','subject':'Ciências','teacher_id':'Clara','lessons':2,'max_consecutive':1,'resource_id':'LabCentro'},
    {'class_id':'7A','subject':'Matemática','teacher_id':'Paulo','lessons':4,'max_consecutive':2},
    {'class_id':'7A','subject':'Português','teacher_id':'Ana','lessons':4,'max_consecutive':2,'avoid_days':['Sex']},
    {'class_id':'7A','subject':'Ciências','teacher_id':'Beto','lessons':2,'max_consecutive':1,'resource_id':'LabNorte'}
 ]
}
(BASE/'exemplo_duas_escolas.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
partial=copy.deepcopy(data)
partial['teachers']['Paulo']['availability']=[{'day':'Ter','start':'10:45','end':'12:00'}]
(BASE/'exemplo_disponibilidade_incompativel.json').write_text(json.dumps(partial,ensure_ascii=False,indent=2),encoding='utf-8')
