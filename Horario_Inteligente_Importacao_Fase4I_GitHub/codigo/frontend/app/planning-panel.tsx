"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type School, type Teacher } from "./api";
import Phase3Controls from "./phase3-controls";
import ProposalsPanel from "./proposals-panel";
import PublicationPanel from "./publication-panel";

type Year = {id:string;year:number;label:string};
type Subject = {id:string;name:string};
type Class = {id:string;name:string;students:number;academic_year_id:string};
type Period = {weekday:number;position:number;start:string;end:string;shift:string};
type Assignment = {id:string;subject_id:string;teacher_id:string;lessons:number;max_consecutive:number;load_mode:string;target_minutes:number|null;min_minutes:number|null;max_minutes:number|null;resource_id:string|null};
type Resource = {id:string;name:string;max_groups:number;max_students:number};
type GradeRow = {class_id:string;class_name:string;school_id:string;teacher:string;teacher_name:string;subject:string;day:string;order:number;start:string;end:string};
type Pending = {class_id:string;class_name:string;teacher_name:string;subject:string;missing:number;unit?:string;reason:string};
type Preview = {result:string;solver_status:string;total_required:number;total_assigned:number;total_assigned_minutes?:number;required_minutes?:number;minute_mode_scheduled_minutes?:number;conflicts:number;pending:Pending[];assignments:GradeRow[];safety_notice:string;teacher_metrics:Record<string,{lessons:number;working_days:number;gap_periods:number}>};
const days=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"];
const newPeriod=():Period=>({weekday:0,position:1,start:"07:10",end:"07:55",shift:"manha"});

export default function PlanningPanel({tenantId,schools,teachers,csrf,canRead,canWrite,canPreview,canProposalsRead,canProposalsCreate,canProposalsSubmit,canProposalsApprove,canPublish}:{tenantId:string;schools:School[];teachers:Teacher[];csrf:string;canRead:boolean;canWrite:boolean;canPreview:boolean;canProposalsRead:boolean;canProposalsCreate:boolean;canProposalsSubmit:boolean;canProposalsApprove:boolean;canPublish:boolean}) {
  const [schoolId,setSchoolId]=useState("");const [yearId,setYearId]=useState("");const [classId,setClassId]=useState("");
  const [years,setYears]=useState<Year[]>([]);const [subjects,setSubjects]=useState<Subject[]>([]);const [classes,setClasses]=useState<Class[]>([]);const [resources,setResources]=useState<Resource[]>([]);
  const [periods,setPeriods]=useState<Period[]>([newPeriod()]);const [assignments,setAssignments]=useState<Assignment[]>([]);
  const [yearInput,setYearInput]=useState({year:new Date().getFullYear()+1,label:"Ano letivo"});
  const [subjectInput,setSubjectInput]=useState("");const [classInput,setClassInput]=useState({name:"",students:25});
  const [assignmentInput,setAssignmentInput]=useState({subject_id:"",teacher_id:"",lessons:2,max_consecutive:2,load_mode:"lessons",target_minutes:250,min_minutes:250,max_minutes:250,resource_id:""});
  const [profile,setProfile]=useState("equilibrado");const [preview,setPreview]=useState<Preview|null>(null);
  const [message,setMessage]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const prefix=`/api/tenants/${tenantId}/schools/${schoolId}`;
  const schoolTeachers=teachers.filter(t=>t.schools.includes(schoolId));
  const execute=async(action:()=>Promise<void>)=>{setBusy(true);setError("");setMessage("");try{await action()}catch(e){setError(e instanceof Error?e.message:"Não foi possível concluir a ação.")}finally{setBusy(false)}};
  const post=<T,>(path:string,payload:unknown,method="POST")=>api<T>(path,method,payload,csrf);
  useEffect(()=>{setSchoolId(v=>schools.some(s=>s.id===v)?v:schools[0]?.id??"")},[schools]);
  const refreshSchool=useCallback(async()=>{
    if(!schoolId||!tenantId||!canRead)return;
    const [ys,ss,rr]=await Promise.all([api<Year[]>(prefix+"/years"),api<Subject[]>(prefix+"/subjects"),api<Resource[]>(prefix+"/resources")]);
    setYears(ys);setSubjects(ss);setResources(rr);setYearId(old=>ys.some(x=>x.id===old)?old:ys[0]?.id??"");
  },[schoolId,tenantId,canRead,prefix]);
  useEffect(()=>{setPreview(null);setYears([]);setSubjects([]);setResources([]);setClasses([]);setClassId("");setYearId("");void refreshSchool().catch(e=>setError(String(e)))},[refreshSchool]);
  const refreshClasses=useCallback(async()=>{
    if(!yearId||!schoolId){setClasses([]);return;}
    const rows=await api<Class[]>(`${prefix}/classes?academic_year_id=${encodeURIComponent(yearId)}`);
    setClasses(rows);setClassId(old=>rows.some(x=>x.id===old)?old:rows[0]?.id??"");
  },[yearId,schoolId,prefix]);
  useEffect(()=>{setPreview(null);void refreshClasses().catch(e=>setError(String(e)))},[refreshClasses]);
  const refreshClass=useCallback(async()=>{
    if(!classId||!schoolId){setPeriods([newPeriod()]);setAssignments([]);return;}
    const base=`${prefix}/classes/${classId}`;
    const [p,a]=await Promise.all([api<Period[]>(base+"/periods"),api<Assignment[]>(base+"/assignments")]);
    setPeriods(p.length?p:[newPeriod()]);setAssignments(a);
  },[classId,schoolId,prefix]);
  useEffect(()=>{void refreshClass().catch(e=>setError(String(e)))},[refreshClass]);

  if(!canRead)return <div className="panel">Você não possui permissão de consulta ao planejamento.</div>;
  if(!schools.length)return <div className="panel"><h2>Planejamento escolar</h2><p className="muted">Cadastre uma escola ou solicite acesso a uma unidade para começar.</p></div>;
  return <div className="stack">
    <div className="panel" style={{marginTop:0}}>
      <h2>1. Selecione a escola e o ano letivo</h2>
      <p className="muted small">O planejamento é isolado por organização, unidade e ano letivo.</p>
      {error&&<div className="alert" role="alert">{error}</div>}{message&&<div className="alert success" role="status">{message}</div>}
      <div className="grid-2"><div><label>Escola</label><select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div><div><label>Ano letivo</label><select value={yearId} onChange={e=>setYearId(e.target.value)}><option value="">Selecione</option>{years.map(y=><option key={y.id} value={y.id}>{y.year} — {y.label}</option>)}</select></div></div>
      {canWrite&&<form className="grid-3" style={{marginTop:14}} onSubmit={e=>{e.preventDefault();void execute(async()=>{await post(prefix+"/years",yearInput);setMessage("Ano letivo cadastrado.");await refreshSchool()})}}><div><label>Novo ano</label><input type="number" min={2000} max={2200} value={yearInput.year} onChange={e=>setYearInput(v=>({...v,year:Number(e.target.value)}))}/></div><div><label>Identificação</label><input required minLength={2} value={yearInput.label} onChange={e=>setYearInput(v=>({...v,label:e.target.value}))}/></div><div style={{alignSelf:"end"}}><button type="submit" disabled={busy}>Adicionar ano</button></div></form>}
    </div>
    {yearId&&<>
      <div className="panel" style={{marginTop:0}}><h2>2. Disciplinas e turmas</h2>
        {canWrite&&<form className="form-inline" onSubmit={e=>{e.preventDefault();void execute(async()=>{await post(prefix+"/subjects",{name:subjectInput});setSubjectInput("");setMessage("Disciplina cadastrada.");await refreshSchool()})}}><div><label>Nova disciplina</label><input required minLength={2} placeholder="Ex.: Matemática" value={subjectInput} onChange={e=>setSubjectInput(e.target.value)}/></div><button disabled={busy}>Adicionar disciplina</button></form>}
        <p className="muted small" style={{marginTop:10}}>Disciplinas: {subjects.map(s=>s.name).join(" · ")||"Nenhuma cadastrada"}</p>
        {canWrite&&<form className="form-inline" style={{marginTop:16}} onSubmit={e=>{e.preventDefault();void execute(async()=>{await post(prefix+"/classes",{...classInput,academic_year_id:yearId});setClassInput({name:"",students:25});setMessage("Turma cadastrada.");await refreshClasses()})}}><div><label>Nova turma</label><input minLength={2} required placeholder="Ex.: 6º Ano A" value={classInput.name} onChange={e=>setClassInput(v=>({...v,name:e.target.value}))}/></div><div><label>Nº de alunos</label><input type="number" min={1} max={500} value={classInput.students} onChange={e=>setClassInput(v=>({...v,students:Number(e.target.value)}))}/></div><button disabled={busy}>Adicionar turma</button></form>}
        <div style={{marginTop:16}}><label>Turma para configurar</label><select value={classId} onChange={e=>{setClassId(e.target.value);setPreview(null)}}><option value="">Selecione</option>{classes.map(c=><option key={c.id} value={c.id}>{c.name} ({c.students} alunos)</option>)}</select></div>
      </div>
      <Phase3Controls prefix={prefix} teachers={schoolTeachers} resources={resources} reload={refreshSchool} csrf={csrf} canWrite={canWrite}/>
      {classId&&<><div className="panel" style={{marginTop:0}}><h2>3. Horários de aula — {classes.find(c=>c.id===classId)?.name}</h2>
        <p className="muted small">Defina os períodos com início e fim exatos. O recreio é identificado pela diferença entre horários; não quebra a contagem de aulas consecutivas.</p>
        <div className="planner-table-scroll"><table className="data-table"><thead><tr><th>Dia</th><th>Ordem</th><th>Início</th><th>Fim</th><th>Turno</th><th></th></tr></thead><tbody>{periods.map((p,i)=><tr key={i}><td><select aria-label={`Dia ${i+1}`} disabled={!canWrite} value={p.weekday} onChange={e=>setPeriods(a=>a.map((v,j)=>j===i?{...v,weekday:Number(e.target.value)}:v))}>{days.map((d,j)=><option key={d} value={j}>{d}</option>)}</select></td><td><input aria-label={`Ordem ${i+1}`} disabled={!canWrite} style={{minWidth:67}} type="number" min={1} max={30} value={p.position} onChange={e=>setPeriods(a=>a.map((v,j)=>j===i?{...v,position:Number(e.target.value)}:v))}/></td><td><input aria-label={`Início ${i+1}`} disabled={!canWrite} type="time" value={p.start} onChange={e=>setPeriods(a=>a.map((v,j)=>j===i?{...v,start:e.target.value}:v))}/></td><td><input aria-label={`Fim ${i+1}`} disabled={!canWrite} type="time" value={p.end} onChange={e=>setPeriods(a=>a.map((v,j)=>j===i?{...v,end:e.target.value}:v))}/></td><td><input aria-label={`Turno ${i+1}`} disabled={!canWrite} value={p.shift} onChange={e=>setPeriods(a=>a.map((v,j)=>j===i?{...v,shift:e.target.value}:v))}/></td><td>{canWrite&&<button type="button" className="ghost" aria-label={`Remover período ${i+1}`} onClick={()=>setPeriods(a=>a.filter((_,j)=>j!==i))}>×</button>}</td></tr>)}</tbody></table></div>
        {canWrite&&<div className="row" style={{marginTop:12}}><button type="button" className="secondary" onClick={()=>setPeriods(v=>[...v,{...newPeriod(),weekday:v[v.length-1]?.weekday??0,position:(v[v.length-1]?.position??0)+1}])}>+ Período</button><button type="button" className="secondary" onClick={()=>setPeriods(v=>{const monday=v.filter(p=>p.weekday===0);return monday.length?[...v.filter(p=>p.weekday>4),...monday,...[1,2,3,4].flatMap(d=>monday.map(p=>({...p,weekday:d})))]:v})}>Copiar segunda para 2ª–6ª</button><button disabled={busy||!periods.length} onClick={()=>void execute(async()=>{await post(`${prefix}/classes/${classId}/periods`,{periods},"PUT");await refreshClass();setMessage("Períodos salvos.")})}>Salvar períodos</button></div>}
      </div><div className="panel" style={{marginTop:0}}><h2>4. Atribuir aulas semanais</h2><p className="muted small">Uma mesma disciplina pode ser dividida entre professores, mas somente pela atribuição explícita cadastrada aqui.</p>
        {canWrite&&<form className="grid-3" onSubmit={e=>{e.preventDefault();void execute(async()=>{await post(`${prefix}/classes/${classId}/assignments`,{
          subject_id:assignmentInput.subject_id,teacher_id:assignmentInput.teacher_id,
          max_consecutive:assignmentInput.max_consecutive,load_mode:assignmentInput.load_mode,
          lessons:assignmentInput.load_mode==="minutes"?1:assignmentInput.lessons,
          ...(assignmentInput.load_mode==="minutes"?{
            target_minutes:assignmentInput.target_minutes,min_minutes:assignmentInput.min_minutes,max_minutes:assignmentInput.max_minutes}:{}),
          resource_id:assignmentInput.resource_id||null
        });setMessage("Aulas atribuídas.");await refreshClass()})}}><div><label>Disciplina</label><select required value={assignmentInput.subject_id} onChange={e=>setAssignmentInput(v=>({...v,subject_id:e.target.value}))}><option value="">Selecione</option>{subjects.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div><div><label>Professor vinculado</label><select required value={assignmentInput.teacher_id} onChange={e=>setAssignmentInput(v=>({...v,teacher_id:e.target.value}))}><option value="">Selecione</option>{schoolTeachers.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></div><div><label>Unidade de carga</label><select value={assignmentInput.load_mode} onChange={e=>setAssignmentInput(v=>({...v,load_mode:e.target.value}))}><option value="lessons">Número de aulas</option><option value="minutes">Minutos semanais</option></select></div>
        {assignmentInput.load_mode==="lessons"?<div><label>Aulas por semana</label><input type="number" min={1} max={50} value={assignmentInput.lessons} onChange={e=>setAssignmentInput(v=>({...v,lessons:Number(e.target.value)}))}/></div>:<>
        <div><label>Minutos-alvo</label><input type="number" min={1} max={2000} value={assignmentInput.target_minutes} onChange={e=>setAssignmentInput(v=>({...v,target_minutes:Number(e.target.value)}))}/></div>
        <div><label>Mínimo permitido</label><input type="number" min={1} max={2000} value={assignmentInput.min_minutes} onChange={e=>setAssignmentInput(v=>({...v,min_minutes:Number(e.target.value)}))}/></div>
        <div><label>Máximo permitido</label><input type="number" min={1} max={2000} value={assignmentInput.max_minutes} onChange={e=>setAssignmentInput(v=>({...v,max_minutes:Number(e.target.value)}))}/></div></>}
        <div><label>Espaço obrigatório (opcional)</label><select value={assignmentInput.resource_id} onChange={e=>setAssignmentInput(v=>({...v,resource_id:e.target.value}))}><option value="">Sem espaço obrigatório</option>{resources.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></div><div><label>Máximo de aulas consecutivas</label><select value={assignmentInput.max_consecutive} onChange={e=>setAssignmentInput(v=>({...v,max_consecutive:Number(e.target.value)}))}><option value={1}>1</option><option value={2}>2</option></select></div><div style={{alignSelf:"end"}}><button disabled={busy}>Vincular carga horária</button></div></form>}
        <div className="planner-table-scroll" style={{marginTop:12}}>{assignments.length?<table className="data-table"><thead><tr><th>Disciplina</th><th>Professor</th><th>Carga semanal</th><th>Espaço</th><th>Máx. seguidas</th><th></th></tr></thead><tbody>{assignments.map(a=><tr key={a.id}><td>{subjects.find(s=>s.id===a.subject_id)?.name??"—"}</td><td>{teachers.find(t=>t.id===a.teacher_id)?.name??"—"}</td><td>{a.load_mode==="minutes"?`${a.target_minutes} min (limites ${a.min_minutes??a.target_minutes}–${a.max_minutes??a.target_minutes})`:`${a.lessons} aulas`}</td><td>{resources.find(r=>r.id===a.resource_id)?.name??"—"}</td><td>{a.max_consecutive}</td><td>{canWrite&&<button type="button" className="ghost" disabled={busy} onClick={()=>void execute(async()=>{await api(`${prefix}/classes/${classId}/assignments/${a.id}`,"DELETE",undefined,csrf);await refreshClass();setMessage("Atribuição excluída.")})}>Remover</button>}</td></tr>)}</tbody></table>:<div className="empty">Nenhuma carga horária atribuída para esta turma.</div>}</div>
      </div></>}
      <div className="panel" style={{marginTop:0}}><h2>5. Gerar prévia de horário</h2><p className="muted small">Prévia experimental por escola/ano. Não grava nem publica a grade. O sistema bloqueia períodos fora da disponibilidade cadastrada dos professores.</p>
        <div className="grid-2"><div><label>Perfil de otimização</label><select value={profile} onChange={e=>setProfile(e.target.value)}><option value="equilibrado">Equilibrado</option><option value="menos_janelas">Menos janelas</option><option value="menos_dias">Menos dias</option></select></div><div style={{alignSelf:"end"}}><button disabled={!canPreview||busy||!classes.length} onClick={()=>void execute(async()=>{const r=await post<Preview>(prefix+"/preview",{academic_year_id:yearId,profile,time_limit:8});setPreview(r);setMessage("Prévia calculada. Verifique pendências e limitações abaixo.")})}>{busy?"Calculando…":"Gerar prévia experimental"}</button></div></div>
        <p className="hint" style={{marginTop:12}}>Já considera limites docentes, recursos e cargas em minutos desta escola. Ainda não valida publicação oficial, conflitos com outras escolas, deslocamentos, bloqueios fixos ou vigência. As funcionalidades serão integradas em fases seguintes.</p>
        {preview&&<div style={{marginTop:15}}><div className="cards"><div className="card"><h3>Aulas distribuídas</h3><div className="metric">{preview.total_assigned} aulas</div><p className="muted small">Meta por contagem: {preview.total_required} aulas</p>{(preview.required_minutes??0)>0&&<p className="muted small">Demandas em minutos: {preview.minute_mode_scheduled_minutes} / {preview.required_minutes} min mínimos (somente cargas em minutos)</p>}</div><div className="card"><h3>Conflitos verificados</h3><div className="metric">{preview.conflicts}</div></div><div className="card"><h3>Estado do otimizador</h3><div style={{fontSize:16,fontWeight:750}}>{preview.solver_status}</div><span className="tag">{preview.result==="complete"?"Cobertura completa":preview.result==="partial"?"Grade parcial":"Não resolvido"}</span></div></div>
          <div className="alert" style={{marginTop:14}}>{preview.safety_notice}</div>
          {preview.pending.length>0&&<><h3>Pendências</h3><div className="planner-table-scroll"><table className="data-table"><thead><tr><th>Turma</th><th>Disciplina</th><th>Professor</th><th>Faltam</th><th>Diagnóstico</th></tr></thead><tbody>{preview.pending.map((p,i)=><tr key={i}><td>{p.class_name}</td><td>{p.subject}</td><td>{p.teacher_name}</td><td>{p.missing} {p.unit==="minutes"?"min":"aulas"}</td><td>{p.reason}</td></tr>)}</tbody></table></div></>}
          <h3 style={{marginTop:20}}>Aulas encontradas</h3><div className="planner-table-scroll"><table className="data-table"><thead><tr><th>Turma</th><th>Dia</th><th>Aula</th><th>Horário</th><th>Disciplina</th><th>Professor</th></tr></thead><tbody>{preview.assignments.map((a,i)=><tr key={i}><td>{a.class_name}</td><td>{a.day}</td><td>{a.order}ª</td><td>{a.start}–{a.end}</td><td>{a.subject}</td><td>{a.teacher_name}</td></tr>)}</tbody></table></div>
        </div>}
      </div>
      {canProposalsRead&&<ProposalsPanel prefix={prefix} yearId={yearId} csrf={csrf} profile={profile} canRead={canProposalsRead} canCreate={canProposalsCreate} canSubmit={canProposalsSubmit} canApprove={canProposalsApprove}/>}
      {canProposalsRead&&<PublicationPanel tenantId={tenantId} schoolId={schoolId} yearId={yearId} csrf={csrf} canRead={canProposalsRead} canPublish={canPublish}/>}
    </>}
  </div>
}
