"use client";
import { useEffect, useState } from "react";
import { api, type Teacher } from "./api";

type Resource = {id:string;name:string;max_groups:number;max_students:number};
type Interval = {weekday:number;start:string;end:string};
const dayNames=["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"];
const weekdays=[0,1,2,3,4];
const defaultIntervals=():Interval[]=>weekdays.map(weekday=>({weekday,start:"07:00",end:"12:30"}));

export default function Phase3Controls({prefix,teachers,resources,reload,csrf,canWrite}:
  {prefix:string;teachers:Teacher[];resources:Resource[];reload:()=>Promise<void>;csrf:string;canWrite:boolean}) {
  const [resourceInput,setResourceInput]=useState({name:"",max_groups:1,max_students:30});
  const [rid,setRid]=useState("");const [intervals,setIntervals]=useState<Interval[]>(defaultIntervals());
  const [tid,setTid]=useState("");const [weekly,setWeekly]=useState(30);
  const [limits,setLimits]=useState<Record<string,number>>({0:6,1:6,2:6,3:6,4:6});
  const [notice,setNotice]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const execute=async(fn:()=>Promise<void>)=>{setBusy(true);setError("");setNotice("");try{await fn()}catch(e){setError(e instanceof Error?e.message:"Falha inesperada") }finally{setBusy(false)}};
  useEffect(()=>{setRid(v=>resources.some(r=>r.id===v)?v:resources[0]?.id??"")},[resources]);
  useEffect(()=>{setTid(v=>teachers.some(t=>t.id===v)?v:teachers[0]?.id??"")},[teachers]);
  useEffect(()=>{if(!rid)return;void api<Interval[]>(`${prefix}/resources/${rid}/availability`)
    .then(rows=>setIntervals(rows.length?rows:defaultIntervals())).catch(e=>setError(String(e)))},[rid,prefix]);
  useEffect(()=>{if(!tid)return;void api<{weekly:number|null;daily:Record<string,number>}>(`${prefix}/teacher-limits/${tid}`)
    .then(result=>{setWeekly(result.weekly??30);setLimits({0:6,1:6,2:6,3:6,4:6,...result.daily})})
    .catch(e=>setError(String(e)))},[tid,prefix]);
  if(!canWrite)return <div className="panel"><h2>Recursos e limites</h2><p className="muted small">Consulta disponível; para editar, solicite permissão de planejamento.</p></div>;
  return <div className="panel" style={{marginTop:0}}>
    <h2>Recursos especiais e limites docentes</h2>
    <p className="muted small">O gerador trata capacidade de alunos e grupos como limites independentes. Intervalos dos recursos são obrigatórios quando o recurso é exigido por uma aula.</p>
    {error&&<div className="alert" role="alert">{error}</div>}
    {notice&&<div className="alert success" role="status">{notice}</div>}
    <form className="grid-3" onSubmit={e=>{e.preventDefault();void execute(async()=>{
      await api(`${prefix}/resources`,"POST",resourceInput,csrf);setResourceInput({name:"",max_groups:1,max_students:30});await reload();setNotice("Recurso cadastrado.")
    })}}>
      <div><label>Novo recurso</label><input required minLength={2} value={resourceInput.name} onChange={e=>setResourceInput(v=>({...v,name:e.target.value}))} placeholder="Laboratório"/></div>
      <div><label>Turmas simultâneas</label><input type="number" min={1} max={50} value={resourceInput.max_groups} onChange={e=>setResourceInput(v=>({...v,max_groups:Number(e.target.value)}))}/></div>
      <div><label>Capacidade de alunos</label><input type="number" min={1} max={5000} value={resourceInput.max_students} onChange={e=>setResourceInput(v=>({...v,max_students:Number(e.target.value)}))}/></div>
      <div><button disabled={busy}>Adicionar recurso</button></div>
    </form>
    {!!resources.length&&<div style={{marginTop:14}}>
      <label>Disponibilidade do recurso</label>
      <select value={rid} onChange={e=>setRid(e.target.value)}>{resources.map(r=><option key={r.id} value={r.id}>{r.name} — até {r.max_groups} turma(s), {r.max_students} alunos</option>)}</select>
      <div className="planner-table-scroll" style={{marginTop:10}}><table className="data-table"><thead><tr><th>Dia</th><th>Início</th><th>Fim</th><th></th></tr></thead><tbody>
        {intervals.map((it,i)=><tr key={i}>
          <td><select aria-label={`Dia do recurso ${i+1}`} value={it.weekday} onChange={e=>setIntervals(a=>a.map((v,j)=>i===j?{...v,weekday:Number(e.target.value)}:v))}>{dayNames.map((d,j)=><option key={j} value={j}>{d}</option>)}</select></td>
          <td><input aria-label={`Início do recurso ${i+1}`} type="time" value={it.start} onChange={e=>setIntervals(a=>a.map((v,j)=>i===j?{...v,start:e.target.value}:v))}/></td>
          <td><input aria-label={`Fim do recurso ${i+1}`} type="time" value={it.end} onChange={e=>setIntervals(a=>a.map((v,j)=>i===j?{...v,end:e.target.value}:v))}/></td>
          <td><button type="button" className="ghost" aria-label="Remover intervalo" onClick={()=>setIntervals(a=>a.filter((_,j)=>j!==i))}>×</button></td>
        </tr>)}
      </tbody></table></div>
      <div className="row" style={{marginTop:10}}><button className="secondary" type="button" onClick={()=>setIntervals(a=>[...a,{weekday:0,start:"07:00",end:"12:30"}])}>+ Intervalo</button>
      <button type="button" disabled={busy||!intervals.length} onClick={()=>void execute(async()=>{await api(`${prefix}/resources/${rid}/availability`,"PUT",{intervals},csrf);setNotice("Disponibilidade do recurso salva.")})}>Salvar disponibilidade</button></div>
    </div>}
    {!!teachers.length&&<div style={{marginTop:20}}>
      <h3>Limites máximos de aulas do professor</h3>
      <p className="muted small">Os limites são globais para o professor na organização. Apenas administradores autorizados da organização podem alterá-los.</p>
      <label>Professor</label><select value={tid} onChange={e=>setTid(e.target.value)}>{teachers.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select>
      <div className="grid-3" style={{marginTop:10}}>
        <div><label>Máximo semanal</label><input type="number" min={0} max={150} value={weekly} onChange={e=>setWeekly(Number(e.target.value))}/></div>
        {weekdays.map(d=><div key={d}><label>{dayNames[d]} — máximo</label><input type="number" min={0} max={30} value={limits[String(d)]??6} onChange={e=>setLimits(v=>({...v,[d]:Number(e.target.value)}))}/></div>)}
      </div>
      <button type="button" style={{marginTop:10}} disabled={busy||!tid} onClick={()=>void execute(async()=>{await api(`${prefix}/teacher-limits/${tid}`,"PUT",{weekly,daily:limits},csrf);setNotice("Limites salvos.")})}>Salvar limites</button>
    </div>}
  </div>;
}
