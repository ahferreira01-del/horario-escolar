"use client";
import {useCallback,useEffect,useState} from "react";
import {api} from "./api";

type Proposal = {
 id:string;status:string;created_by:string;submitted_by:string|null;decided_by:string|null;
 result:string;solver_status:string;total_assigned:number;total_required:number;pending_count:number;
 created_at:string;justification:string|null;decision_note:string|null;published:boolean;
};

export default function ProposalsPanel({prefix,yearId,currentUserId,onChanged,csrf,canRead,canCreate,canSubmit,canApprove,profile}:{
 prefix:string;yearId:string;currentUserId:string;onChanged:()=>void;csrf:string;canRead:boolean;canCreate:boolean;canSubmit:boolean;canApprove:boolean;profile:string;
}) {
 const [items,setItems]=useState<Proposal[]>([]);
 const [reason,setReason]=useState("");
 const [note,setNote]=useState("");
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [busy,setBusy]=useState(false);
 const refresh=useCallback(async()=>{
   if(!yearId||!canRead){setItems([]);return;}
   setItems(await api<Proposal[]>(`${prefix}/proposals?academic_year_id=${encodeURIComponent(yearId)}`));
 },[prefix,yearId,canRead]);
 useEffect(()=>{void refresh().catch(e=>setError(String(e)))},[refresh]);
 async function action(url:string,payload:unknown){
   setBusy(true);setError("");setNotice("");
   try{await api(url,"POST",payload,csrf);await refresh();onChanged();setNotice("Operação registrada. A grade ainda NÃO está publicada.");}
   catch(e){setError(e instanceof Error?e.message:"Não foi possível concluir a operação.");}
   finally{setBusy(false);}
 }
 const statusLabels:Record<string,string>={draft:"Rascunho",submitted:"Aguardando aprovação",approved:"Aprovada (não publicada)",rejected:"Rejeitada"};
 return <section className="panel" style={{marginTop:0}} aria-label="Propostas para revisão">
   <h2>6. Propostas salvas e aprovação</h2>
   <p className="muted small">As propostas são instantâneos calculados no servidor, com histórico e auditoria. A aprovação NÃO equivale à publicação. O módulo de publicação exige verificação adicional e PostgreSQL seguro.</p>
   {error&&<div className="alert" role="alert">{error}</div>}
   {notice&&<div className="alert success" role="status">{notice}</div>}
   {canCreate&&<div className="row" style={{marginTop:12}}><button disabled={busy||!yearId} type="button" onClick={()=>void action(`${prefix}/proposals`,{academic_year_id:yearId,profile,time_limit:8})}>Gerar e salvar nova proposta</button><button className="secondary" type="button" disabled={busy} onClick={()=>void refresh().then(onChanged).catch(e=>setError(String(e)))}>Atualizar lista</button></div>}
   <p className="hint">O motor recalcula ao salvar. Uma proposta com aulas pendentes exigirá justificativa para submissão e permissão especial para aprovação. Alterações no cadastro exigem gerar nova proposta.</p>
   <div className="grid-2" style={{marginTop:12}}><div><label htmlFor="proposal-reason">Justificativa para proposta parcial</label><textarea id="proposal-reason" rows={2} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Obrigatória quando houver pendências"/></div><div><label htmlFor="proposal-note">Observação da decisão</label><textarea id="proposal-note" rows={2} maxLength={1000} value={note} onChange={e=>setNote(e.target.value)} placeholder="Obrigatória para rejeitar"/></div></div>
   {items.length===0?<div className="empty" style={{marginTop:12}}>Nenhuma proposta registrada neste ano letivo.</div>:
   <div className="planner-table-scroll" style={{marginTop:12}}><table className="data-table"><thead><tr><th>Data</th><th>Situação</th><th>Aulas</th><th>Pendências</th><th>Ações</th></tr></thead><tbody>
    {items.map(p=><tr key={p.id}>
     <td>{new Date(p.created_at).toLocaleString("pt-BR")}</td>
     <td><span className="tag">{statusLabels[p.status]??p.status}</span></td>
     <td>{p.total_assigned} / {p.total_required} <span className="muted small">({p.solver_status})</span></td>
     <td>{p.pending_count}</td>
     <td><div className="row" style={{gap:6,flexWrap:"wrap"}}>
      <a className="secondary" href={`${prefix}/proposals/${p.id}/export.csv`} download={`proposta-${p.id}.csv`}>CSV</a>
      {p.status==="draft"&&canSubmit&&<button type="button" className="secondary" disabled={busy} onClick={()=>void action(`${prefix}/proposals/${p.id}/submit`,{justification:reason||null})}>Enviar à revisão</button>}
      {p.status==="submitted"&&canApprove&&<>
       {p.created_by!==currentUserId&&p.submitted_by!==currentUserId?<button type="button" className="secondary" disabled={busy} onClick={()=>void action(`${prefix}/proposals/${p.id}/approve`,{note:note||null})}>Aprovar</button>:<span className="muted small" title="O criador ou remetente da proposta não pode aprová-la.">Aprovação exige outro usuário.</span>}
       <button type="button" className="ghost" disabled={busy||!note.trim()} onClick={()=>void action(`${prefix}/proposals/${p.id}/reject`,{note})}>Rejeitar</button>
      </>}
     </div></td>
    </tr>)}
   </tbody></table></div>}
   <p className="hint">Utilize a seção 7 para pré-validar e publicar. Não use a publicação com dados reais até concluir o ensaio de PostgreSQL e concorrência.</p>
 </section>;
}
