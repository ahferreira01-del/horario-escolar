"""Fase 4E — exportação oficial Excel, estrutura, autorização e injeção."""
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from datetime import datetime

from sqlalchemy import select

from app.official_xlsx import render_official_xlsx, NS
from app.models import (
    PublishedGrade, PublishedClass, PublishedLesson, TeachingAssignment, GradeProposal,
)
from test_app import context, tenant_with_admin
from test_publication import approved, uri


def _sheet_text(xlsx: bytes):
    with ZipFile(BytesIO(xlsx)) as z:
        assert z.testzip() is None
        assert '[Content_Types].xml' in z.namelist()
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        names=[s.attrib['name'] for s in workbook.findall(f'.//{{{NS}}}sheet')]
        sheet_xml=[ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')) for i in range(1,len(names)+1)]
        texts=['\n'.join((t.text or '') for t in root.findall(f'.//{{{NS}}}t')) for root in sheet_xml]
        return names,texts,sheet_xml


def test_render_excel_named_sheets_and_pending_are_safe():
    xlsx=render_official_xlsx(
        {'id':'export-123','valid_from':'2027-02-01','valid_to':'2027-05-30',
         'classes':['c1','c2','c3'],'partial':True,'justification':'Pendências justificadas',
         'lessons':[{'class_id':'c1','day':'Seg','period':1,'subject':'=HYPERLINK("https://invalido","clique")',
                     'teacher_id':'t1','start':'07:10','end':'07:55'}],
         'pending':[{'class_id':'c1','subject':'Matemática','missing':2,'reason':'Disponibilidade insuficiente'}]},
        'Escola A',{'c1':'7º A / Teste','c2':'7º A : Teste','c3':'Turma? [] \\ muito longa muito longa'},
        {'t1':'Professor Teste'})
    names,texts,roots=_sheet_text(xlsx)
    assert names[0]=='Resumo'
    assert len(names)==len(set(n.casefold() for n in names))==5
    assert all(len(n)<=31 and not any(c in n for c in '/\\:*?[]') for n in names)
    assert any('AULAS PENDENTES' in t and 'Matemática' in t for t in texts)
    assert 'PUBLICADA COM PENDÊNCIAS' in texts[0]
    assert 'HYPERLINK' in '\n'.join(texts)
    # FÓRMULAS são proibidas: os campos controlados por escolas são somente texto.
    assert all(not root.findall(f'.//{{{NS}}}f') for root in roots)
    assert all(c.attrib.get('t')=='inlineStr' for root in roots for c in root.findall(f'.//{{{NS}}}c'))
    assert all(root.find(f'{{{NS}}}pageSetup').attrib['orientation']=='landscape' for root in roots)


def test_excel_export_requires_school_permission(context):
    client,Session=context
    tid,sid,year,_,_,body=approved(client,'excel-access')
    proposal_id=body['parts'][0]['proposal_id']
    cls_id=body['parts'][0]['class_ids'][0]
    with Session() as db:
        teacher=db.scalar(select(TeachingAssignment.teacher_id).where(
            TeachingAssignment.tenant_id==tid, TeachingAssignment.class_id==cls_id))
        owner=db.scalar(select(GradeProposal.created_by).where(GradeProposal.id==proposal_id))
        pub=PublishedGrade(tenant_id=tid,school_id=sid,academic_year_id=year,
            proposal_id=proposal_id,batch_id='batch-excel-test',
            valid_from=datetime(2027,2,1),valid_to=datetime(2027,2,5),
            partial=False,published_by=owner)
        db.add(pub);db.flush()
        db.add(PublishedClass(tenant_id=tid,school_id=sid,publication_id=pub.id,class_id=cls_id))
        db.add(PublishedLesson(tenant_id=tid,school_id=sid,publication_id=pub.id,
            class_id=cls_id,teacher_id=teacher,subject='Matemática',weekday=0,
            period_position=1,start_minute=430,end_minute=475,students=25))
        db.commit(); pub_id=pub.id
    authorized=client.get(uri(tid)+f'/{pub_id}/export.xlsx')
    assert authorized.status_code==200,authorized.text[:100] if authorized.status_code!=200 else ''
    assert authorized.headers['content-type']=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    names,texts,roots=_sheet_text(authorized.content)
    assert len(names)==3 and 'Matemática' in texts[1] and 'Matemática' in texts[2]
    tenant_with_admin(client,'other-excel-organization')
    denied=client.get(uri(tid)+f'/{pub_id}/export.xlsx')
    assert denied.status_code==403
