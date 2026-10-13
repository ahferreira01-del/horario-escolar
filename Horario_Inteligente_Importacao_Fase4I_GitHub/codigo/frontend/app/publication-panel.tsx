"use client";
import {useCallback,useEffect,useState} from "react";
import {api} from "./api";

type Proposal={id:string;status:string;total_assigned:number;total_required:number;pending_count:number;created_at:string};
type ClassItem={id:string;name:string};
type Published={id:string;batch_id:string;valid_from:string;valid_to:string;partial:boolean;published_at:string};
type Preflight={eligible:boolean;lessons:number;dated_occurrences:number;partial:boolean;schools:number;existing_occurrences_compared:number;warning:string};

export default function PublicationPanel({tenantId,schoolId,yearId,csrf,canPublish,canRead}: {
 tenantId:string;schoolId:string;yearId:string;csrf:string;canPublish:boolean;canRead:boolean;
}){
 const [proposals,setProposals]=useState<Proposal[]>([]);
 const [classes,setClasses]=useState<ClassItem[]>([]);
 const [selected,setSelected]=useState<string[]>([]);
 const [proposalId,setProposalId]=useState("");
 const [from,setFrom]=useState(""); const [to,setTo]=useState("");
 const [justification,setJustification]=useState("");
 const [confirmed,setConfirmed]=useState(false);
 const [preflight,setPreflight]=useState<Preflight|null>(null);
 const [published,setPublished]=useState<Published[]>([]);
 const [error,setError]=useState("");const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);
 const base=`/api/tenants/${tenantId}`;
 const schoolBase=`${base}/schools/${schoolId}`;
 const update=useCallback(async()=>{
  if(!schoolId||!yearId||!canRead)return;
  const [p,c,official]=await Promise.all([
   api<Proposal[]>(`${schoolBase}/proposals?academic_year_id=${encodeURIComponent(yearId)}`),
   api<ClassItem[]>(`${schoolBase}/classes?academic_year_id=${encodeURIComponent(yearId)}`),
   api<Published[]>(`${base}/publications?school_id=${schoolId}`)
  ]);
  setProposals(p);setClasses(c);setPublished(official);
 },[base,schoolBase,schoolId,yearId,canRead]);
 useEffect(()=>{setSelected([]);setProposalId("");setPreflight(null);setConfirmed(false);void update().catch(e=>setError(String(e)))},[update]);
 const body=()=>({parts:[{school_id:schoolId,proposal_id:proposalId,class_ids:selected}],valid_from:from,valid_to:to,exceptional_justification:justification.trim()||null});
 async function action(publish:boolean){
  setBusy(true);setError("");setNotice("");
  try{
   if(publish){
    if(!preflight?.eligible||!confirmed)throw new Error("Confirme a pré-validação e sua aprovação da publicação.");
    await api(`${base}/publications/publish`,"POST",body(),csrf);
    setNotice("Lote publicado; consulte seu período de vigência no histórico.");setPreflight(null);setConfirmed(false);
   }else{
    const response=await api<Preflight>(`${base}/publications/preflight`,"POST",body());
    setPreflight(response);setConfirmed(false);setNotice("Pré-validação concluída; nenhuma grade foi alterada.");
   }
   await update();
  }catch(e){setError(e instanceof Error?e.message:"Não foi possível validar a publicação.");setPreflight(null);setConfirmed(false)}
  finally{setBusy(false)}
 }
 const approved=proposals.filter(p=>p.status==="approved");
 return <section className="panel" aria-label="Publicação oficial" style={{marginTop:0}}>
  <h2>7. Validar e publicar grades oficiais</h2>
  <p className="muted small">A publicação é independente da aprovação. Exige PostgreSQL com isolamento validado, rechecagem transacional e vigência por datas. Esta interface é experimental; não utilize com dados de uma escola real antes dos testes integrados.</p>
  {error&&<div className="alert" role="alert">{error}</div>}
  {notice&&<div className="alert success" role="status">{notice}</div>}
  {canPublish?<>
   <div className="grid-2">
    <div><label htmlFor="pub-proposal">Proposta aprovada</label><select id="pub-proposal" value={proposalId} onChange={e=>{setProposalId(e.target.value);setPreflight(null);setConfirmed(false)}}><option value="">Selecione</option>{approved.map(p=><option key={p.id} value={p.id}>{new Date(p.created_at).toLocaleDateString("pt-BR")} — {p.total_assigned}/{p.total_required} aulas {p.pending_count?`(${p.pending_count} pendências)`:""}</option>)}</select></div>
    <div><label>Turmas do grupo</label><div style={{maxHeight:160,overflowY:"auto",border:"1px solid var(--border)",borderRadius:8,padding:10}}>{classes.map(c=><label key={c.id} style={{display:"flex",alignItems:"center",gap:8,marginBottom:7}}><input type="checkbox" checked={selected.includes(c.id)} onChange={e=>{setSelected(v=>e.target.checked?[...v,c.id]:v.filter(id=>id!==c.id));setPreflight(null);setConfirmed(false)}}/>{c.name}</label>)}</div></div>
    <div><label htmlFor="pub-from">Início de vigência</label><input id="pub-from" type="date" value={from} onChange={e=>{setFrom(e.target.value);setPreflight(null);setConfirmed(false)}}/></div>
    <div><label htmlFor="pub-to">Fim de vigência</label><input id="pub-to" type="date" value={to} onChange={e=>{setTo(e.target.value);setPreflight(null);setConfirmed(false)}}/></div>
   </div>
   <div style={{marginTop:12}}><label htmlFor="pub-reason">Justificativa para publicação excepcional de grade parcial</label><textarea id="pub-reason" maxLength={1000} rows={2} value={justification} onChange={e=>{setJustification(e.target.value);setPreflight(null);setConfirmed(false)}} placeholder="Obrigatória quando existirem aulas pendentes nas turmas selecionadas"/></div>
   <div className="row" style={{marginTop:12}}><button type="button" className="secondary" disabled={busy||!proposalId||!from||!to||!selected.length} onClick={()=>void action(false)}>Pré-validar publicação</button><button type="button" className="secondary" disabled={busy} onClick={()=>void update()}>Atualizar histórico</button></div>
   {preflight&&<div className="panel" style={{marginTop:14}}>
     <h3>Resultado da pré-validação</h3><p>{preflight.lessons} aulas semanais • {preflight.dated_occurrences} ocorrências no período • {preflight.schools} unidade(s)</p>
     {preflight.partial&&<p className="alert">Esta publicação é parcial e permanecerá identificada com pendências.</p>}
     <p className="hint">{preflight.warning}</p>
     <label style={{display:"flex",alignItems:"center",gap:8}}><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Confirmo que revisei a vigência, a seleção e a autorização da publicação.</label>
     <button type="button" style={{marginTop:12}} disabled={!confirmed||busy} onClick={()=>void action(true)}>Publicar oficialmente (PostgreSQL)</button>
   </div>}
  </>:<p className="hint">Sua conta não possui permissão para publicação oficial.</p>}
  <h3 style={{marginTop:18}}>Histórico de versões publicadas</h3>
  {published.length?<div className="planner-table-scroll"><table className="data-table"><thead><tr><th>Vigência</th><th>Situação</th><th>Lote</th></tr></thead><tbody>{published.map(p=><tr key={p.id}><td>{p.valid_from} a {p.valid_to}</td><td>{p.partial?"Publicada com pendências":"Completa"}</td><td title={p.batch_id}><a href={`${base}/publications/${p.id}/export.csv`} download={`grade-oficial-${p.id}.csv`}>CSV</a>{" · "}<a href={`${base}/publications/${p.id}/export.pdf`} download={`grade-oficial-${p.id}.pdf`}>PDF A4</a>{" · "}<a href={`${base}/publications/${p.id}/export.xlsx`} download={`grade-oficial-${p.id}.xlsx`}>Excel</a></td></tr>)}</tbody></table></div>:<div className="empty">Nenhuma grade oficial publicada nesta escola.</div>}
 </section>
}
