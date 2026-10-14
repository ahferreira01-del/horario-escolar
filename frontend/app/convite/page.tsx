"use client";
import { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { api } from "../api";
export default function InvitePage() {
  const [tenant,setTenant]=useState(""); const [token,setToken]=useState("");
  const [name,setName]=useState(""); const [password,setPassword]=useState("");
  const [message,setMessage]=useState(""); const [error,setError]=useState(""); const [loading,setLoading]=useState(false);
  useEffect(()=>{const p=new URLSearchParams(window.location.search);setTenant(p.get("tenant")??"");setToken(p.get("token")??"")},[]);
  return <div className="auth-wrap"><div className="auth-card"><div className="auth-brand"><span className="brand-mark"><CalendarDays size={22}/></span> Horário Inteligente</div>
    <span className="eyebrow">Convite seguro</span><h1>Ativar seu acesso</h1><p className="muted">Defina seus dados para aceitar o convite. Se já possuir uma conta, entre primeiro pelo painel.</p>
    {error&&<div className="alert">{error}</div>}{message&&<div className="alert success">{message} <a href="/">Ir para o painel</a></div>}
    <form onSubmit={async e=>{e.preventDefault();setLoading(true);setError("");try{await api("/api/auth/accept-invitation","POST",{tenant_id:tenant,token,name,password:password||null});setMessage("Acesso ativado com sucesso.");setPassword("");}catch(e){setError(e instanceof Error?e.message:"Erro ao ativar.")}finally{setLoading(false)}}}>
      <div className="field"><label>Seu nome</label><input required value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="field"><label>Defina sua senha (mínimo de 12 caracteres)</label><input type="password" minLength={12} value={password} onChange={e=>setPassword(e.target.value)} placeholder="Senha forte"/></div>
      <button type="submit" disabled={!tenant||!token||loading}>{loading?"Ativando…":"Aceitar convite"}</button>
    </form><p className="hint" style={{marginTop:18}}>Convites são de uso único e expiram em 48 horas. Para contas já existentes, o sistema exigirá login antes de aceitar o vínculo.</p>
  </div></div>;
}
