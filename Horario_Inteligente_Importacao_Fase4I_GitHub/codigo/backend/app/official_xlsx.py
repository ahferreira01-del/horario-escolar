"""Exportação XLSX oficial sem macros e sem fórmulas, somente dados já publicados.

Open Packaging Conventions + SpreadsheetML (ISO/IEC 29500). Todas as células
são explicitamente inlineStr: nomes livres nunca são executados como fórmulas.
Não persiste dados nem chama sistemas externos.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PN = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
DAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
ET.register_namespace("", NS)
ET.register_namespace("r", RNS)
FORBIDDEN = re.compile(r"[\\/*?:\[\]]")
ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _safe_text(value) -> str:
    return ILLEGAL_XML.sub("", str(value) if value is not None else "")[:30000]


def _sheet_name(raw: str, used: set[str]) -> str:
    name = FORBIDDEN.sub("-", _safe_text(raw)).strip().strip("'")[:31] or "Turma"
    base = name
    i = 2
    while name.casefold() in used:
        suffix = f" ({i})"
        name = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(name.casefold())
    return name


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _worksheet(rows: list[list[str]], day_columns: int, grid_header: int | None = None,
               grid_rows: set[int] | None = None) -> bytes:
    ws = ET.Element(f"{{{NS}}}worksheet")
    views = ET.SubElement(ws, f"{{{NS}}}sheetViews")
    view = ET.SubElement(views, f"{{{NS}}}sheetView", {"workbookViewId": "0"})
    if grid_header is not None:
        ET.SubElement(view, f"{{{NS}}}pane", {
            "xSplit": "1", "ySplit": str(grid_header), "topLeftCell": f"B{grid_header + 1}",
            "activePane": "bottomRight", "state": "frozen",
        })
    ET.SubElement(ws, f"{{{NS}}}sheetFormatPr", {"defaultRowHeight":"15"})
    col_specs = ET.SubElement(ws, f"{{{NS}}}cols")
    ET.SubElement(col_specs, f"{{{NS}}}col", {"min": "1", "max": "1", "width": "17", "customWidth": "1"})
    ET.SubElement(col_specs, f"{{{NS}}}col", {"min": "2", "max": str(max(day_columns, 2)), "width": "27", "customWidth": "1"})
    data = ET.SubElement(ws, f"{{{NS}}}sheetData")
    for rownum, rowdata in enumerate(rows, 1):
        rowattr = {"r": str(rownum)}
        if rownum == 1: rowattr.update({"ht": "30", "customHeight": "1"})
        elif grid_rows and rownum in grid_rows: rowattr.update({"ht": "62", "customHeight": "1"})
        r = ET.SubElement(data, f"{{{NS}}}row", rowattr)
        for colnum, value in enumerate(rowdata, 1):
            if value is None: continue
            style = 1 if rownum == 1 else 2 if rownum == grid_header else 3 if (grid_rows and rownum in grid_rows) else 0
            cell = ET.SubElement(r, f"{{{NS}}}c", {"r": f"{_col(colnum)}{rownum}", "t": "inlineStr", "s": str(style)})
            inline = ET.SubElement(cell, f"{{{NS}}}is")
            textnode = ET.SubElement(inline, f"{{{NS}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
            textnode.text = _safe_text(value)
    ET.SubElement(ws, f"{{{NS}}}pageMargins", {"left":"0.25","right":"0.25","top":"0.45","bottom":"0.45","header":"0.2","footer":"0.2"})
    ET.SubElement(ws, f"{{{NS}}}pageSetup", {"paperSize": "9", "orientation": "landscape", "fitToWidth": "1", "fitToHeight": "1"})
    return ET.tostring(ws, encoding="utf-8", xml_declaration=True)


def _styles() -> bytes:
    root = ET.Element(f"{{{NS}}}styleSheet")
    fonts = ET.SubElement(root, f"{{{NS}}}fonts", {"count":"2"})
    f0=ET.SubElement(fonts,f"{{{NS}}}font")
    ET.SubElement(f0,f"{{{NS}}}sz", {"val":"10"})
    ET.SubElement(f0,f"{{{NS}}}name", {"val":"Calibri"})
    f1=ET.SubElement(fonts,f"{{{NS}}}font")
    ET.SubElement(f1,f"{{{NS}}}b")
    ET.SubElement(f1,f"{{{NS}}}sz", {"val":"11"})
    ET.SubElement(f1,f"{{{NS}}}color", {"rgb":"FFFFFFFF"})
    ET.SubElement(f1,f"{{{NS}}}name", {"val":"Calibri"})
    fills=ET.SubElement(root,f"{{{NS}}}fills",{"count":"3"})
    for kind in ("none", "gray125"):
        ET.SubElement(ET.SubElement(fills,f"{{{NS}}}fill"),f"{{{NS}}}patternFill", {"patternType":kind})
    fill=ET.SubElement(fills,f"{{{NS}}}fill")
    pat=ET.SubElement(fill,f"{{{NS}}}patternFill", {"patternType":"solid"})
    ET.SubElement(pat,f"{{{NS}}}fgColor", {"rgb":"FF263E55"})
    ET.SubElement(pat,f"{{{NS}}}bgColor", {"indexed":"64"})
    borders=ET.SubElement(root,f"{{{NS}}}borders", {"count":"1"})
    border=ET.SubElement(borders,f"{{{NS}}}border")
    for side in ("left","right","top","bottom","diagonal"):
        ET.SubElement(border,f"{{{NS}}}{side}")
    ET.SubElement(root,f"{{{NS}}}cellStyleXfs",{"count":"1"}).append(ET.Element(f"{{{NS}}}xf",{"numFmtId":"0","fontId":"0","fillId":"0","borderId":"0"}))
    cxf=ET.SubElement(root,f"{{{NS}}}cellXfs",{"count":"4"})
    for font, fill, center, wrap in [(0,0,False,False),(1,2,False,True),(1,2,True,True),(0,0,False,True)]:
        xf=ET.SubElement(cxf,f"{{{NS}}}xf",{"numFmtId":"0","fontId":str(font),"fillId":str(fill),"borderId":"0","xfId":"0","applyAlignment":"1"})
        ET.SubElement(xf,f"{{{NS}}}alignment",{"vertical":"center","horizontal":"center" if center else "left","wrapText":"1" if wrap else "0"})
    ET.SubElement(root,f"{{{NS}}}cellStyles",{"count":"1"}).append(ET.Element(f"{{{NS}}}cellStyle", {"name":"Normal","xfId":"0"}))
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)


def _plain_default_ns(xml: bytes) -> bytes:
    """Serializa namespace OPC padrão sem prefixo para compatibilidade."""
    return xml.replace(b"<ns0:",b"<").replace(b"</ns0:",b"</").replace(b"xmlns:ns0=",b"xmlns=")


def render_official_xlsx(data: dict, school_name: str,
                         class_names: dict[str,str], teacher_names: dict[str,str]) -> bytes:
    """Cria Resumo e uma aba por turma, sem fórmulas e sem links externos."""
    by_class: dict[str,list[dict]] = defaultdict(list)
    for lesson in data.get("lessons", []):
        by_class[str(lesson["class_id"])].append(lesson)
    pending = data.get("pending", [])
    classes = list(dict.fromkeys(str(x) for x in data.get("classes", [])))
    status = "PUBLICADA COM PENDÊNCIAS" if data.get("partial") else "OFICIAL COMPLETA"
    summary = [
        ["HORÁRIO INTELIGENTE — GRADE OFICIAL"],
        ["Escola", school_name], ["Vigência", f"{data['valid_from']} a {data['valid_to']}"],
        ["Situação", status], ["Publicação", data.get("id", "")],
        ["Turmas", str(len(classes))], ["Aulas semanais", str(len(data.get("lessons", [])))],
        ["Pendências", str(len(pending))],
        ["Aviso", "Consulte a vigência antes de utilizar. Exportação de versão oficial imutável."],
    ]
    if data.get('justification'):
        summary.append(["Justificativa de exceção", data['justification']])
    sheets: list[tuple[str,list[list[str]],int,int|None,set[int]|None]] = [("Resumo",summary,2,None,None)]
    used = {"resumo"}
    # Visão panorâmica, próxima ao modelo original da planilha enviada.
    # Grupos de até seis turmas preservam a legibilidade em impressão A4.
    # AVISO: período ordinal igual não implica horas idênticas entre turmas.
    for offset in range(0,len(classes),6):
        group=classes[offset:offset+6]
        all_lessons=[r for cid in group for r in by_class.get(cid,[])]
        used_days=[d for d in DAYS if any(r.get('day')==d for r in all_lessons)] or list(DAYS[:5])
        maximum=max((int(r['period']) for r in all_lessons),default=0)
        periods=list(range(1, min(maximum,30)+1))
        table=[["QUADRO GERAL — GRADES OFICIAIS"],
               ["Escola",school_name,"Vigência",f"{data['valid_from']} a {data['valid_to']}"],
               ["Observação","Aulas na mesma posição podem ter horários diferentes conforme a turma."],
               ["Dia","Aula",*[class_names.get(cid,cid) for cid in group]]]
        gl={(str(l['class_id']),str(l['day']),int(l['period'])):l for l in all_lessons}
        for day in used_days:
            for period in periods:
                row=[day,f"{period}ª aula"]
                for cid in group:
                    l=gl.get((cid,day,period))
                    row.append((f"{l['subject']}\n{teacher_names.get(str(l['teacher_id']),str(l['teacher_id']))}\n{l['start']}–{l['end']}") if l else "—")
                table.append(row)
        if not periods: table.append(["Nenhuma aula distribuída",""])
        name=_sheet_name("Quadro Geral" if offset==0 else f"Quadro Geral {offset//6+1}", used)
        sheets.append((name,table,2+len(group),4,set(range(5,5+len(periods)*len(used_days)))))
    for class_id in classes:
        name=_sheet_name(class_names.get(class_id, class_id),used)
        lessons=by_class.get(class_id,[])
        days=[d for d in DAYS if any(l.get("day")==d for l in lessons)] or list(DAYS[:5])
        periods=sorted({int(l["period"]) for l in lessons})
        lookup={(int(l["period"]),l["day"]):l for l in lessons}
        # Cabeçalho da grade na linha 4, um registro por período com quebras de linha.
        rows: list[list[str]]=[
            ["HORÁRIO INTELIGENTE — GRADE OFICIAL"],
            ["Escola", school_name, "Turma", class_names.get(class_id,class_id)],
            ["Vigência", f"{data['valid_from']} a {data['valid_to']}", "Situação", status],
            ["Aula", *days],
        ]
        for period in periods:
            row=[f"{period}ª aula"]
            for day in days:
                lesson=lookup.get((period,day))
                if not lesson:
                    row.append("—")
                    continue
                row.append(f"{lesson['subject']}\n{teacher_names.get(str(lesson['teacher_id']),str(lesson['teacher_id']))}\n{lesson['start']}–{lesson['end']}")
            rows.append(row)
        class_pending=[x for x in pending if str(x.get("class_id"))==class_id]
        if class_pending:
            rows.extend([[""],["AULAS PENDENTES"],["Disciplina","Quantidade","Motivo"]])
            for p in class_pending:
                rows.append([p.get('subject',''),str(p.get('missing','')),p.get('reason','')])
        elif not periods:
            rows.append(["Sem aulas distribuídas para esta turma"])
        sheets.append((name,rows,len(days)+1,4,set(range(5,5+len(periods)))))
    root = ET.Element(f"{{{NS}}}workbook", {f"{{{RNS}}}dummy": "unused"})
    root.attrib.pop(f"{{{RNS}}}dummy")
    all_sheets=ET.SubElement(root,f"{{{NS}}}sheets")
    for i,(name,_,_,_,_) in enumerate(sheets,1):
        ET.SubElement(all_sheets,f"{{{NS}}}sheet",{"name":name,"sheetId":str(i),f"{{{RNS}}}id":f"rId{i}"})
    props=ET.Element(f"{{{CONTENT_NS}}}Types")
    ET.SubElement(props,f"{{{CONTENT_NS}}}Default",{"Extension":"rels","ContentType":"application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(props,f"{{{CONTENT_NS}}}Default",{"Extension":"xml","ContentType":"application/xml"})
    ET.SubElement(props,f"{{{CONTENT_NS}}}Override",{"PartName":"/xl/workbook.xml","ContentType":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    ET.SubElement(props,f"{{{CONTENT_NS}}}Override",{"PartName":"/xl/styles.xml","ContentType":"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
    for i in range(1,len(sheets)+1):
        ET.SubElement(props,f"{{{CONTENT_NS}}}Override",{"PartName":f"/xl/worksheets/sheet{i}.xml","ContentType":"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
    relationships=ET.Element(f"{{{PN}}}Relationships")
    ET.SubElement(relationships,f"{{{PN}}}Relationship",{"Id":"rId1","Type":"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument","Target":"xl/workbook.xml"})
    wb_rels=ET.Element(f"{{{PN}}}Relationships")
    for i in range(1,len(sheets)+1):
        ET.SubElement(wb_rels,f"{{{PN}}}Relationship",{"Id":f"rId{i}","Type":"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet","Target":f"worksheets/sheet{i}.xml"})
    ET.SubElement(wb_rels,f"{{{PN}}}Relationship",{"Id":f"rId{len(sheets)+1}","Type":"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles","Target":"styles.xml"})
    buf=BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('[Content_Types].xml',_plain_default_ns(ET.tostring(props,encoding='utf-8',xml_declaration=True)))
        z.writestr('_rels/.rels',_plain_default_ns(ET.tostring(relationships,encoding='utf-8',xml_declaration=True)))
        z.writestr('xl/workbook.xml',ET.tostring(root,encoding='utf-8',xml_declaration=True))
        z.writestr('xl/_rels/workbook.xml.rels',_plain_default_ns(ET.tostring(wb_rels,encoding='utf-8',xml_declaration=True)))
        z.writestr('xl/styles.xml',_styles())
        for i,(_,rows,ncol,header,gridrows) in enumerate(sheets,1):
            z.writestr(f'xl/worksheets/sheet{i}.xml',_worksheet(rows,ncol,header,gridrows))
    return buf.getvalue()
