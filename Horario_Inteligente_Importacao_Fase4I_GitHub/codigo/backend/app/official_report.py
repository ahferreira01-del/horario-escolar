"""Exportação em PDF A4 paisagem para grades oficiais autorizadas.

Os dados chegam APÓS verificação de 'grades.read' no endpoint de publicação.
Este arquivo não consulta outro tenant nem salva documentos permanentes.
"""
from __future__ import annotations
from collections import defaultdict
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak,
)

WEEKDAYS=('Seg','Ter','Qua','Qui','Sex','Sab','Dom')


def render_official_pdf(data: dict, school_name: str, class_names: dict[str, str],
                        teacher_names: dict[str, str]) -> bytes:
    buf=BytesIO()
    pagesize=landscape(A4)
    doc=SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=26, rightMargin=26,
                          topMargin=26, bottomMargin=28, title='Horário Inteligente - Grade oficial',
                          author='Horário Inteligente')
    usable_width=pagesize[0]-52
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='HI_Title',fontName='Helvetica-Bold',fontSize=17,leading=21,
                              textColor=colors.HexColor('#203047'),spaceAfter=6))
    styles.add(ParagraphStyle(name='HI_Sub',fontName='Helvetica',fontSize=9,leading=13,
                              textColor=colors.HexColor('#52616f')))
    styles.add(ParagraphStyle(name='HI_Cell',fontName='Helvetica',fontSize=8,leading=10.5,alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='HI_Head',fontName='Helvetica-Bold',fontSize=9,leading=11,
                              textColor=colors.white,alignment=TA_CENTER))
    story=[]
    is_partial=bool(data.get('partial'))
    by_class=defaultdict(list)
    for lesson in data.get('lessons',[]):
        by_class[str(lesson['class_id'])].append(lesson)
    classes=data.get('classes',[])
    for index,class_id in enumerate(classes):
        if index:story.append(PageBreak())
        story.append(Paragraph('HORÁRIO INTELIGENTE',styles['HI_Title']))
        school=escape(school_name or 'Escola')
        klass=escape(class_names.get(class_id,class_id))
        story.append(Paragraph(f'<b>{school}</b> &nbsp; | &nbsp; {klass}',styles['HI_Sub']))
        period=f"Vigência: {escape(data['valid_from'])} a {escape(data['valid_to'])}"
        status='PUBLICADA COM PENDÊNCIAS' if is_partial else 'GRADE OFICIAL'
        story.append(Paragraph(f'{period} &nbsp; | &nbsp; <b>{status}</b>',styles['HI_Sub']))
        story.append(Spacer(1,14))
        lessons=by_class.get(class_id,[])
        days=[d for d in WEEKDAYS if any(x['day']==d for x in lessons)]
        if not days:days=list(WEEKDAYS[:5])
        slots=sorted({int(x['period']) for x in lessons})
        if not slots:
            story.append(Paragraph('Nenhuma aula foi distribuída para esta turma.',styles['HI_Sub']))
        else:
            lookup={(int(x['period']),x['day']):x for x in lessons}
            body=[[Paragraph('Aula',styles['HI_Head'])]+[Paragraph(day,styles['HI_Head']) for day in days]]
            for slot in slots:
                row=[Paragraph(f'{slot}ª',styles['HI_Cell'])]
                for day in days:
                    lesson=lookup.get((slot,day))
                    if not lesson:
                        row.append('-')
                        continue
                    subject=escape(str(lesson['subject']))
                    teacher=escape(teacher_names.get(str(lesson['teacher_id']),str(lesson['teacher_id'])))
                    hhmm=f"{escape(str(lesson['start']))} - {escape(str(lesson['end']))}"
                    row.append(Paragraph(f'<b>{subject}</b><br/>{teacher}<br/>{hhmm}',styles['HI_Cell']))
                body.append(row)
            day_count=len(days)
            table=LongTable(body, colWidths=[50]+[(usable_width-50)/day_count]*day_count,
                            repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#263e55')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f1f5f9')]),
                ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#c9d2db')),
                ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),6),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ]))
            story.append(table)
        pend=[q for q in data.get('pending',[]) if str(q.get('class_id'))==class_id]
        if pend:
            story.append(Spacer(1,12))
            story.append(Paragraph('<b>ATENÇÃO: AULAS PENDENTES</b>',styles['HI_Sub']))
            for p in pend:
                name=escape(str(p.get('subject','Disciplina')))
                missing=escape(str(p.get('missing','-')))
                reason=escape(str(p.get('reason','Sem detalhamento')))
                story.append(Paragraph(f'{name}: {missing} pendente(s). {reason}',styles['HI_Sub']))
        story.append(Spacer(1,10))
        story.append(Paragraph('Documento gerado a partir da versão publicada. Consulte a vigência antes de utilizar.',styles['HI_Sub']))
    if not story:
        story.append(Paragraph('Não há turmas disponíveis nesta publicação.',styles['HI_Sub']))
    doc.build(story)
    return buf.getvalue()
