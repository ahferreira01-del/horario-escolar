"""Gera relatórios HTML locais estáticos a partir do resultado da PoC."""
import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from solver import DAYS

def esc(s): return html.escape(str(s),quote=True)

def generate_report(data,result,title):
    classes=data['classes'];assignments=result['assignments']
    by_slot={(a['class_id'],a['day'],a['order']):a for a in assignments}
    pending=result.get('pending',[])
    h=['''<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Horário Inteligente — Prova de conceito</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#152235;background:#f7f9fc;}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 64px}
h1{font-size:clamp(24px,4vw,38px);margin:12px 0 6px}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.15em;font-weight:750;color:#42617e}
p.lead{color:#4b5b6f;margin:0 0 24px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px}
.card,.panel{background:white;border:1px solid #e0e6ef;border-radius:13px;padding:18px}.card small{display:block;color:#627389;font-size:12px}.card b{font-size:26px;display:block;margin-top:6px}
.panel{margin-top:18px;overflow:hidden}.title{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:14px}
h2{font-size:19px;margin:0}table{width:100%;border-collapse:collapse;min-width:660px}th,td{border:1px solid #e4e9f1;text-align:left;padding:10px;vertical-align:top;font-size:13px}
th{background:#eff4fa;color:#43576d;font-weight:700}td.period{background:#f7f9fc;font-size:12px;color:#61738a;width:108px}
.inner{overflow-x:auto}.item b{display:block;font-size:12px}.item small{display:block;color:#64758a;margin-top:4px}
.empty{font-size:12px;color:#a0abb8}.pill{padding:5px 9px;border-radius:999px;background:#edf7f0;color:#26603d;font-weight:700;font-size:12px}
.pill.warn{background:#fff0e8;color:#9d4a20}ol{padding-left:22px}li{margin:8px 0}footer{margin-top:22px;color:#67768a;font-size:12px;line-height:1.6}
@media(max-width:660px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:12px}.card b{font-size:22px}.panel{padding:12px}}
</style></head><body><main class="wrap">''']
    h.append(f'<div class="eyebrow">Horário Inteligente • POC v0.2 • dados fictícios</div><h1>{esc(title)}</h1>')
    h.append('<p class="lead">Protótipo matemático local, sem usuários, backend, publicação ou banco de dados.</p>')
    h.append('<section class="cards">')
    for label,value in [('Aulas distribuídas',f"{result['total_assigned']}/{result['total_required']}"),('Escolas',str(len(data['schools']))),('Janelas intraturno',str(sum(x['gap_periods'] for x in result['teacher_metrics'].values()))),('Aulas pendentes',str(sum(p['missing'] for p in pending)))]:
        h.append(f'<div class="card"><small>{esc(label)}</small><b>{esc(value)}</b></div>')
    h.append('</section>')
    for cls,cfg in classes.items():
        days=[d for d in DAYS if any(s['day']==d for s in cfg['slots'])]
        orders=sorted(set(s['order'] for s in cfg['slots']))
        h.append(f'<section class="panel"><div class="title"><h2>{esc(cfg["school_id"])} · Turma {esc(cls)}</h2><span class="pill">{len([a for a in assignments if a["class_id"]==cls])} aulas distribuídas</span></div>')
        h.append('<div class="inner"><table><thead><tr><th>Aula</th>'+''.join(f'<th>{esc(day)}</th>' for day in days)+'</tr></thead><tbody>')
        for order in orders:
            h.append(f'<tr><td class="period"><strong>{order}ª aula</strong></td>')
            for day in days:
                slot=next((s for s in cfg['slots'] if s['day']==day and s['order']==order),None)
                if not slot:
                    h.append('<td><span class="empty">—</span></td>');continue
                a=by_slot.get((cls,day,order))
                if a:
                    res=(f' · {esc(a["resource_id"])}' if a.get('resource_id') else '')
                    content=f'<div class="item"><b>{esc(a["subject"])}</b><small>{esc(a["teacher"])}{res}</small></div>'
                else:content='<span class="empty">Sem aula</span>'
                h.append(f'<td>{content}<div class="empty">{esc(slot["start"])}–{esc(slot["end"])}</div></td>')
            h.append('</tr>')
        h.append('</tbody></table></div></section>')
    h.append('<section class="panel"><h2 style="margin-bottom:12px">Indicadores por professor</h2><div class="inner"><table><thead><tr><th>Professor</th><th>Aulas</th><th>Dias trabalhados</th><th>Janelas disponíveis*</th><th>Turnos adicionais*</th></tr></thead><tbody>')
    for t,x in result['teacher_metrics'].items():
        h.append(f'<tr><td>{esc(t)}</td><td>{x["lessons"]}</td><td>{x["working_days"]}</td><td>{x["gap_periods"]}</td><td>{x["additional_shifts"]}</td></tr>')
    h.append('</tbody></table></div></section>')
    if pending:
        h.append('<section class="panel"><div class="title"><h2>Pendências identificadas</h2><span class="pill warn">Grade parcial</span></div><ol>')
        for x in pending:
            h.append(f'<li><b>{esc(x["school_id"])} · {esc(x["class_id"])} · {esc(x["subject"])}</b> — {x["missing"]} aulas de {esc(x["teacher"])}. {esc(x["reason"])}</li>')
        h.append('</ol></section>')
    h.append(f'''<footer>Resultado: {esc(result['result'])} · cobertura ótima comprovada: {esc(result['coverage_proven_optimal'])} · status: {esc(result['solver_status'])}.
    * Indicadores aproximados no protótipo; turnos adicionais não equivalem a minutos de espera. O cenário não valida autenticação, autorização, RLS, publicação nem todas as regras funcionais aprovadas.</footer></main></body></html>''')
    return '\n'.join(h)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('input',type=Path);ap.add_argument('result',type=Path);ap.add_argument('--out',required=True,type=Path);ap.add_argument('--title',default='Grade escolar')
    args=ap.parse_args();d=json.loads(args.input.read_text(encoding='utf-8'));r=json.loads(args.result.read_text(encoding='utf-8'))
    args.out.write_text(generate_report(d,r,args.title),encoding='utf-8')
if __name__=='__main__':main()
