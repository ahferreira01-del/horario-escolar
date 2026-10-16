"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, LayoutDashboard, Building2, School, GraduationCap, MailPlus, ShieldCheck, ClipboardList, LogOut, Plus, Clock3, X, CheckCircle2, Users, RefreshCcw, Copy, KeyRound, UserRoundPlus, LockKeyhole } from "lucide-react";
import PlanningPanel from "./planning-panel";
import { api, type Me, type School as SchoolType, type Role, type Teacher, type Availability, type Tenant, type TenantUser } from "./api";

type Tab = "overview" | "organizations" | "schools" | "teachers" | "users" | "invites" | "roles" | "audit" | "requests" | "my-schedule" | "planning";
const weekdays = ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira","Sábado","Domingo"];
const initialAvailability: Availability = { weekday: 0, start: "07:00", end: "12:00" };

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [tenantId, setTenantId] = useState("");
  const [schools, setSchools] = useState<SchoolType[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [tenantUsers, setTenantUsers] = useState<TenantUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState("");
  const [organizations, setOrganizations] = useState<Tenant[]>([]);
  const [audit, setAudit] = useState<Array<{id:string;action:string;type:string;date:string;details:Record<string,unknown>}>>([]);
  const [requests, setRequests] = useState<Array<{id:string;teacher:string;weekday:number;start:string;end:string;reason:string;status:string}>>([]);
  const [ownTeacher, setOwnTeacher] = useState<{teacher:{id:string;name:string}|null;availability:Availability[]} | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [newOrg, setNewOrg] = useState({name:"", first_admin_name:"", first_admin_email:""});
  const [newUser, setNewUser] = useState({name:"",email:"",role_id:"",school_id:"",is_active:true});
  const [credential, setCredential] = useState<{email:string;password:string|null;expires:string|null;createdAccount:boolean;kind:"user"|"reset"|"organization";invitationUrl?:string|null;invitationSent?:boolean|null}|null>(null);
  const [copyNotice, setCopyNotice] = useState("");
  const [passwordNew, setPasswordNew] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [newSchool, setNewSchool] = useState({name:"",timezone:"America/Sao_Paulo"});
  const [newTeacher, setNewTeacher] = useState({name:"",school_id:""});
  const [newInvite, setNewInvite] = useState({email:"",role_id:"",school_id:"",teacher_id:""});
  const [newRole, setNewRole] = useState({name:"",code:"",permissions:[] as string[]});
  const [lastInvite, setLastInvite] = useState("");
  const [selectedTeacher, setSelectedTeacher] = useState<Teacher | null>(null);
  const [availability, setAvailability] = useState<Availability[]>([]);
  const [myRequest, setMyRequest] = useState({weekday:0,start:"07:00",end:"12:00",reason:""});
  const memberships = me?.memberships ?? [];
  const currentTenant = memberships.find(m => m.tenant_id === tenantId);
  const myPerms = useMemo(() => Array.from(new Set(memberships.filter(m => m.tenant_id === tenantId).flatMap(m => m.permissions))), [memberships, tenantId]);
  const can = useCallback((p:string) => myPerms.includes(p), [myPerms]);
  const teacherPortal = memberships.some(m=>m.tenant_id===tenantId && m.role_code==="teacher");
  const toast = (message:string) => { setNotice(message); setError(""); };
  const fail = (err:unknown) => { setError(err instanceof Error ? err.message : "Ocorreu um erro."); setNotice(""); };

  async function refreshMe() {
    try {
      const data = await api<Me>("/api/auth/me");
      setMe(data);
      setTenantId(current => (data.memberships.some(m=>m.tenant_id===current) ? current : data.memberships[0]?.tenant_id ?? ""));
    } catch { setMe(null); }
    finally { setChecking(false); }
  }
  useEffect(() => { void refreshMe(); }, []);
  const refreshData = useCallback(async () => {
    if (!me) return;
    if (me.is_platform_admin) {
      try {setOrganizations(await api<Tenant[]>("/api/platform/tenants"));} catch {/* scoped menus remain functional */}
    }
    if (!tenantId) return;
    const prefix = `/api/tenants/${tenantId}`;
    if (myPerms.includes("schools.read")) try {setSchools(await api<SchoolType[]>(prefix+"/schools"));} catch {setSchools([]);}
    if (myPerms.includes("roles.read")) try {setRoles(await api<Role[]>(prefix+"/roles"));} catch {setRoles([]);}
    if (myPerms.includes("teachers.read")) try {setTeachers(await api<Teacher[]>(prefix+"/teachers"));} catch {setTeachers([]);}
    if (myPerms.includes("users.invite")) {
      setUsersLoading(true);setUsersError("");setTenantUsers([]);
      try {setTenantUsers(await api<TenantUser[]>(prefix+"/users"));}
      catch (e) {setTenantUsers([]);setUsersError(e instanceof Error?e.message:"Não foi possível carregar os usuários.");}
      finally {setUsersLoading(false);}
    } else {setTenantUsers([]);setUsersError("");}
    if (myPerms.includes("audit.read")) try {setAudit(await api<typeof audit>(prefix+"/audit"));} catch {setAudit([]);}
    if (myPerms.includes("teachers.requests.read")) try {setRequests(await api<typeof requests>(prefix+"/availability-requests"));} catch {setRequests([]);}
    if (myPerms.includes("teachers.self")) try {setOwnTeacher(await api<typeof ownTeacher>(prefix+"/my-teacher"));} catch {setOwnTeacher(null);}
  }, [me,tenantId,myPerms]);
  useEffect(()=>{void refreshData()},[refreshData]);
  async function run(f:()=>Promise<void>) {setLoading(true);setError("");setNotice("");try{await f()}catch(e){fail(e)}finally{setLoading(false)}}
  const write = <T,>(path:string, data:unknown, method="POST") => api<T>(path, method, data, me?.csrf);
  const prefix = `/api/tenants/${tenantId}`;

  if (checking) return <div className="auth-wrap"><div className="auth-card skeleton">Carregando o Horário Inteligente…</div></div>;
  if (!me) return <div className="auth-wrap"><div className="auth-card">
    <div className="auth-brand"><span className="brand-mark"><CalendarDays size={22}/></span> Horário Inteligente</div>
    <span className="eyebrow">Acesso seguro</span><h1>Boas-vindas de volta</h1><p className="muted">Entre com o e-mail convidado pela sua organização.</p>
    {error && <div className="alert">{error}</div>}
    <form onSubmit={e=>{e.preventDefault();void run(async()=>{await api("/api/auth/login","POST",{email,password});setPassword("");await refreshMe();});}}>
      <div className="field"><label>E-mail</label><input type="email" required value={email} onChange={e=>setEmail(e.target.value)} placeholder="voce@escola.com.br"/></div>
      <div className="field"><label>Senha</label><input type="password" required value={password} onChange={e=>setPassword(e.target.value)} placeholder="Sua senha"/></div>
      <button disabled={loading} type="submit">{loading?"Entrando…":"Entrar na plataforma"}</button>
    </form><p className="hint" style={{marginTop:18}}>O cadastro de organizações é exclusivo da administração da plataforma. Não existe cadastro público.</p>
  </div></div>;

  if (me.must_change_password) return <div className="auth-wrap challenge-wrap">
    <section className="auth-card password-challenge">
      <div className="auth-brand"><span className="brand-mark"><LockKeyhole size={21}/></span> Horário Inteligente</div>
      <span className="eyebrow">Primeiro acesso · etapa obrigatória</span>
      <h1>Crie sua senha pessoal</h1>
      <p className="muted">A senha temporária já cumpriu seu papel. Defina uma nova senha para proteger sua conta antes de continuar.</p>
      <div className="security-note"><ShieldCheck size={18}/><span>Esta alteração protege sua conta em todas as organizações vinculadas a este e-mail.</span></div>
      {error && <div className="alert" data-testid="password-change-error" role="alert">{error}</div>}
      <form className="stack" onSubmit={e=>{e.preventDefault();if(passwordNew!==passwordConfirm){fail(new Error("As senhas informadas não são iguais."));return}void run(async()=>{const result=await api<{message:string;csrf:string}>("/api/auth/change-password","POST",{new_password:passwordNew,confirm_password:passwordConfirm},me.csrf);setMe({...me,csrf:result.csrf,must_change_password:false});setPasswordNew("");setPasswordConfirm("");setError("");setNotice("")})}}>
        <div><label htmlFor="new-password">Nova senha</label><input id="new-password" data-testid="new-password-input" type="password" autoComplete="new-password" required value={passwordNew} onChange={e=>setPasswordNew(e.target.value)} placeholder="Digite sua nova senha"/></div>
        <div><label htmlFor="confirm-password">Confirme a nova senha</label><input id="confirm-password" data-testid="confirm-password-input" type="password" autoComplete="new-password" required value={passwordConfirm} onChange={e=>setPasswordConfirm(e.target.value)} placeholder="Repita a nova senha"/></div>
        <button type="submit" data-testid="change-password-submit" disabled={loading||!passwordNew||!passwordConfirm}><LockKeyhole size={16}/>{loading?"Atualizando senha…":"Salvar e continuar"}</button>
      </form>
      <p className="hint" style={{marginTop:16}}>O painel ficará disponível somente depois que a atualização for confirmada.</p>
    </section>
  </div>;

  const hasTenant = tenantId.length > 0;
  const nav: {id:Tab; label:string; icon:typeof CalendarDays; show:boolean}[] = [
    {id:"overview",label:"Visão geral",icon:LayoutDashboard,show:true},
    {id:"organizations",label:"Organizações",icon:Building2,show:me.is_platform_admin},
    {id:"schools",label:"Escolas",icon:School,show:hasTenant&&can("schools.read")},
    {id:"teachers",label:"Professores",icon:GraduationCap,show:hasTenant&&can("teachers.read")},
    {id:"users",label:"Usuários",icon:Users,show:hasTenant&&can("users.invite")},
    {id:"planning",label:"Planejamento e grades",icon:CalendarDays,show:hasTenant&&can("planning.read")},
    {id:"invites",label:"Convidar usuários",icon:MailPlus,show:hasTenant&&can("users.invite")},
    {id:"roles",label:"Perfis e permissões",icon:ShieldCheck,show:hasTenant&&can("roles.read")},
    {id:"requests",label:"Solicitações",icon:ClipboardList,show:hasTenant&&can("teachers.requests.read")},
    {id:"my-schedule",label:"Meu acesso docente",icon:CalendarDays,show:hasTenant&&teacherPortal},
    {id:"audit",label:"Auditoria",icon:Clock3,show:hasTenant&&can("audit.read")}
  ];
  const visibleNav = nav.filter(x=>x.show);
  const heading = visibleNav.find(x=>x.id===tab)?.label ?? "Visão geral";
  const current = visibleNav.some(x=>x.id===tab) ? tab : "overview";

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><CalendarDays size={21}/></span><span className="brand-text">Horário Inteligente</span></div>
      <div className="side-label">Área de trabalho</div>
      {visibleNav.map(item=><button type="button" key={item.id} onClick={()=>{setTab(item.id);setNotice("");setError("")}} className={`nav-item ${current===item.id?"active":""}`}><item.icon size={19}/><span className="label">{item.label}</span></button>)}
      <div className="sidebar-footer">Cadastros pedagógicos · Fase 4H<br/>SaaS multiempresa</div>
    </aside>
    <main className="content-area">
      <header className="topbar">
        <div className="muted small">Painel / <strong style={{color:"var(--ink)"}}>{heading}</strong></div>
        <div className="topbar-right">
          {memberships.length>0 && <select aria-label="Organização" style={{maxWidth:220,minHeight:39}} value={tenantId} onChange={e=>{setTenantId(e.target.value);setSelectedTeacher(null);setTab("overview")}}>{[...new Map(memberships.map(m=>[m.tenant_id,m.tenant_name])).entries()].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select>}
          <span className="pill desktop-only">{me.name}</span>
          <button className="ghost" title="Sair" onClick={()=>void run(async()=>{await api("/api/auth/logout","POST",undefined,me.csrf);setMe(null)})}><LogOut size={18}/></button>
        </div>
      </header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">Horário Inteligente / Fase 4H</div><h1>{heading}</h1><div className="muted">{currentTenant ? `${currentTenant.tenant_name} · ${currentTenant.role_name}` : "Administração da plataforma"}</div></div><button className="secondary" onClick={()=>void refreshData()}><RefreshCcw size={16}/> Atualizar</button></div>
        {currentTenant?.tenant_status === "suspended" && <div className="alert">Esta organização está suspensa. O acesso pode estar limitado a consultas, ou bloqueado, conforme a política aplicada.</div>}
        {error && <div className="alert">{error}</div>}{notice && <div className="alert success">{notice}</div>}
        {current==="overview" && <><div className="cards">
          <div className="card"><h3>Escolas cadastradas</h3><div className="metric">{schools.length}</div><div className="sub">Unidades visíveis para seu perfil</div></div>
          <div className="card"><h3>Professores</h3><div className="metric">{teachers.length}</div><div className="sub">Cadastros autorizados para consulta</div></div>
          <div className="card"><h3>Organizações</h3><div className="metric">{me.is_platform_admin?organizations.length:[...new Set(memberships.map(m=>m.tenant_id))].length}</div><div className="sub">Acesso restrito por organização</div></div>
        </div><div className="panel"><h2>Aplicação em desenvolvimento — Fase 4H</h2><p className="muted">Esta versão permite criar organizações (administração da plataforma), escolas, professores, perfis e convites. Também cadastra a disponibilidade semanal exata dos professores, mantendo regras de escopo no servidor.</p><div className="row"><span className="tag">Autenticação por convite</span><span className="tag">Permissões por unidade</span><span className="tag">Auditoria</span></div><hr className="hr"/><p className="hint">O planejamento de turmas, disciplinas e períodos e a geração de PRÉVIAS experimentais estão disponíveis na aba Planejamento e grades. A aprovação e a publicação possuem testes integrados de API com PostgreSQL/RLS; o fluxo completo de publicação pelo navegador continua em homologação. Não utilize com dados escolares reais. Outras regras avançadas continuam em desenvolvimento.</p></div></>}
        {current==="planning" && <PlanningPanel key={tenantId} tenantId={tenantId} currentUserId={me.id} schools={schools} teachers={teachers} csrf={me.csrf} canRead={can("planning.read")} canWrite={can("planning.write")} canPreview={can("planning.preview")} canProposalsRead={can("grades.read")} canProposalsCreate={can("grades.create")} canProposalsSubmit={can("grades.submit")} canProposalsApprove={can("grades.approve")} canPublish={can("grades.publish")} />}
         {current==="organizations" && <><div className="panel"><h2>Cadastrar organização</h2><p className="muted">Disponível exclusivamente para a administração da plataforma. Uma senha temporária será exibida uma única vez quando uma nova conta for criada.</p>
            <form className="grid-3" onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await write<{name:string;first_admin:{email:string;created_account:boolean;temporary_password:string|null;temporary_password_expires_at:string|null};admin_invitation_sent?:boolean;dev_invitation_url?:string}>("/api/platform/tenants",newOrg);toast("Organização criada: "+r.name);setCredential({email:r.first_admin.email,password:r.first_admin.temporary_password,expires:r.first_admin.temporary_password_expires_at,createdAccount:r.first_admin.created_account,kind:"organization",invitationUrl:r.dev_invitation_url??null,invitationSent:r.admin_invitation_sent??false});setNewOrg({name:"",first_admin_name:"",first_admin_email:""});await refreshData()})}}>
            <div><label>Nome da organização</label><input required value={newOrg.name} onChange={e=>setNewOrg({...newOrg,name:e.target.value})}/></div>
            <div><label>Nome do administrador</label><input required value={newOrg.first_admin_name} onChange={e=>setNewOrg({...newOrg,first_admin_name:e.target.value})}/></div>
            <div><label>E-mail do administrador</label><input type="email" required value={newOrg.first_admin_email} onChange={e=>setNewOrg({...newOrg,first_admin_email:e.target.value})}/></div>
             <button disabled={loading} data-testid="create-organization-submit"><Plus size={16}/> Criar organização</button>
           </form>
        </div><div className="panel"><h2>Organizações</h2>{organizations.length?<table className="data-table"><thead><tr><th>Nome</th><th>Status</th><th>Limite de escolas</th></tr></thead><tbody>{organizations.map(x=><tr key={x.id}><td>{x.name}</td><td><span className="tag">{x.status}</span></td><td>{x.max_schools}</td></tr>)}</tbody></table>:<div className="empty">Nenhuma organização cadastrada.</div>}</div></>}
        {current==="schools" && <><div className="panel"><h2>Escolas da organização</h2>{can("schools.create")&&<form className="form-inline" onSubmit={e=>{e.preventDefault();void run(async()=>{await write(prefix+"/schools",newSchool);setNewSchool({name:"",timezone:"America/Sao_Paulo"});toast("Escola cadastrada.");await refreshData()})}}><div><label>Nome da escola</label><input required value={newSchool.name} onChange={e=>setNewSchool({...newSchool,name:e.target.value})}/></div><div><label>Fuso horário</label><input required value={newSchool.timezone} onChange={e=>setNewSchool({...newSchool,timezone:e.target.value})}/></div><button disabled={loading}><Plus size={16}/> Adicionar</button></form>}<hr className="hr"/>{schools.length?<table className="data-table"><thead><tr><th>Unidade</th><th>Fuso horário</th></tr></thead><tbody>{schools.map(s=><tr key={s.id}><td>{s.name}</td><td>{s.timezone}</td></tr>)}</tbody></table>:<div className="empty">Nenhuma unidade cadastrada ou autorizada.</div>}</div></>}
        {current==="teachers" && <><div className="panel"><h2>Professores</h2>{can("teachers.create")&&<form className="form-inline" onSubmit={e=>{e.preventDefault();void run(async()=>{await write(prefix+"/teachers",newTeacher);setNewTeacher({name:"",school_id:""});toast("Professor cadastrado.");await refreshData()})}}><div><label>Nome do professor</label><input value={newTeacher.name} onChange={e=>setNewTeacher({...newTeacher,name:e.target.value})} required/></div><div><label>Escola</label><select value={newTeacher.school_id} required onChange={e=>setNewTeacher({...newTeacher,school_id:e.target.value})}><option value="">Selecione</option>{schools.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div><button disabled={loading}><Plus size={16}/> Cadastrar</button></form>}<hr className="hr"/>{teachers.length?<table className="data-table"><thead><tr><th>Professor</th><th>Unidades vinculadas</th><th>Disponibilidade</th></tr></thead><tbody>{teachers.map(t=><tr key={t.id}><td>{t.name}</td><td>{t.schools.map(id=>schools.find(s=>s.id===id)?.name??"Unidade autorizada").join(", ")}</td><td><button className="secondary" onClick={()=>void run(async()=>{const a=await api<Availability[]>(prefix+`/teachers/${t.id}/availability`);setSelectedTeacher(t);setAvailability(a)})}>Visualizar / editar</button></td></tr>)}</tbody></table>:<div className="empty">Cadastre uma escola e depois um professor.</div>}</div>
          {selectedTeacher&&<div className="panel"><div className="panel-header"><div><h2>Disponibilidade de {selectedTeacher.name}</h2><p className="muted small">Faixas exatas de início e término; o motor jamais poderá agendar aulas fora delas.</p></div><button className="ghost" onClick={()=>setSelectedTeacher(null)}><X size={19}/></button></div>{availability.map((a,i)=><div className="av-grid" key={i}><div><label>Dia</label><select value={a.weekday} disabled={!can("teachers.availability")} onChange={e=>setAvailability(arr=>arr.map((v,j)=>i===j?{...v,weekday:+e.target.value}:v))}>{weekdays.map((day,d)=><option key={d} value={d}>{day}</option>)}</select></div><div><label>De</label><input type="time" value={a.start} disabled={!can("teachers.availability")} onChange={e=>setAvailability(arr=>arr.map((v,j)=>i===j?{...v,start:e.target.value}:v))}/></div><div><label>Até</label><input type="time" value={a.end} disabled={!can("teachers.availability")} onChange={e=>setAvailability(arr=>arr.map((v,j)=>i===j?{...v,end:e.target.value}:v))}/></div>{can("teachers.availability")&&<button type="button" className="ghost" onClick={()=>setAvailability(arr=>arr.filter((_,j)=>j!==i))}><X size={16}/> Remover</button>}</div>)}
          {can("teachers.availability")?<div className="row"><button className="secondary" type="button" onClick={()=>setAvailability([...availability,{...initialAvailability}])}><Plus size={16}/> Adicionar faixa</button><button disabled={loading} onClick={()=>void run(async()=>{await write(prefix+`/teachers/${selectedTeacher.id}/availability`,{intervals:availability},"PUT");toast("Disponibilidade registrada.");await refreshData()})}><CheckCircle2 size={16}/> Salvar disponibilidade</button></div>:<div className="hint">A alteração global da disponibilidade exige permissão central da organização.</div>}</div>}
        </>}
         {current==="users"&&<div className="users-page">
           <div className="users-intro"><div><span className="eyebrow">Acessos da organização</span><h2>Usuários e permissões</h2><p className="muted">Gerencie vínculos nesta organização. O status da senha pertence à conta e pode valer para outros acessos do mesmo e-mail.</p></div><span className="secure-chip"><ShieldCheck size={15}/> Acesso administrativo</span></div>
           <div className="panel user-create-panel"><div className="panel-header"><div><h3>Adicionar usuário</h3><p className="muted small">Não enviaremos convite por e-mail. Uma senha temporária será mostrada uma única vez se uma nova conta for criada.</p></div><UserRoundPlus size={22} className="accent-icon"/></div>
             <form className="user-create-form" onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await write<{user_id:string;name:string;email:string;membership_active:boolean;account_active:boolean;role_code:string;role_name:string;school_id:string|null;school_name:string|null;created_account:boolean;temporary_password:string|null;temporary_password_expires_at:string|null}>(prefix+"/users",{name:newUser.name,email:newUser.email,role_id:newUser.role_id,school_id:newUser.school_id||null,is_active:newUser.is_active});setNewUser({name:"",email:"",role_id:"",school_id:"",is_active:true});setCredential({email:r.email,password:r.temporary_password,expires:r.temporary_password_expires_at,createdAccount:r.created_account,kind:"user"});setTenantUsers(await api<TenantUser[]>(prefix+"/users"));toast("Vínculo de usuário criado.")})}}>
               <div><label htmlFor="user-name">Nome completo</label><input id="user-name" data-testid="user-name-input" required value={newUser.name} onChange={e=>setNewUser({...newUser,name:e.target.value})} placeholder="Nome do usuário"/></div>
               <div><label htmlFor="user-email">E-mail da conta</label><input id="user-email" data-testid="user-email-input" type="email" required value={newUser.email} onChange={e=>setNewUser({...newUser,email:e.target.value})} placeholder="nome@escola.com.br"/></div>
               <div><label htmlFor="user-role">Perfil nesta organização</label><select id="user-role" data-testid="user-role-select" required value={newUser.role_id} onChange={e=>setNewUser({...newUser,role_id:e.target.value})}><option value="">Selecione um perfil</option>{roles.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></div>
               <div><label htmlFor="user-school">Unidade (opcional)</label><select id="user-school" data-testid="user-school-select" value={newUser.school_id} onChange={e=>setNewUser({...newUser,school_id:e.target.value})}><option value="">Todas / sem unidade específica</option>{schools.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
               <label className="check-line"><input type="checkbox" data-testid="user-active-input" checked={newUser.is_active} onChange={e=>setNewUser({...newUser,is_active:e.target.checked})}/> Ativar vínculo assim que criado</label>
               <button type="submit" data-testid="create-user-submit" disabled={loading||!roles.length}><UserRoundPlus size={16}/>{loading?"Criando acesso…":"Criar acesso"}</button>
             </form>
           </div>
           <div className="panel"><div className="panel-header"><div><h3>Usuários vinculados</h3><p className="muted small">Ativação e suspensão abaixo afetam apenas o vínculo com esta organização.</p></div><div className="row"><span className="count-chip" data-testid="users-count">{tenantUsers.length} {tenantUsers.length===1?"usuário":"usuários"}</span><button type="button" className="ghost compact-button" data-testid="refresh-users" aria-label="Atualizar usuários" disabled={usersLoading} onClick={()=>void run(async()=>{setUsersLoading(true);setUsersError("");try{setTenantUsers(await api<TenantUser[]>(prefix+"/users"))}catch(e){setUsersError(e instanceof Error?e.message:"Não foi possível carregar os usuários.");throw e}finally{setUsersLoading(false)}})}><RefreshCcw size={15}/> Atualizar</button></div></div>
             {usersError&&<div className="alert" role="alert" data-testid="users-load-error">{usersError}</div>}
             {usersLoading?<div className="users-loading" data-testid="users-loading"><span/><span/><span/>Carregando vínculos...</div>:tenantUsers.length?<div className="table-scroll"><table className="data-table users-table"><thead><tr><th>Usuário</th><th>Perfil / unidade</th><th>Vínculo</th><th>Conta</th><th>Ações</th></tr></thead><tbody>{tenantUsers.map(u=><tr key={u.user_id}><td><strong>{u.name}</strong><span className="user-email">{u.email}</span></td><td>{u.role_name}<span className="user-email">{u.school_name??"Sem unidade específica"}</span></td><td><span className={`status-badge ${u.membership_active?"status-on":"status-off"}`} data-testid={`membership-status-${u.user_id}`}>{u.membership_active?"Ativo":"Suspenso"}</span></td><td><span className={`status-badge ${u.account_active?"status-on":"status-off"}`} data-testid={`account-status-${u.user_id}`}>{u.account_active?"Conta ativa":"Conta inativa"}</span><span className="user-email" data-testid={`password-status-${u.user_id}`}>{u.must_change_password?"Senha temporária pendente":"Senha pessoal definida"}{u.must_change_password&&u.temporary_password_expires_at?` · expira ${new Date(u.temporary_password_expires_at).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"})}`:""}</span></td><td><div className="user-actions"><button type="button" className="secondary compact-button" data-testid={`toggle-membership-${u.user_id}`} disabled={loading} onClick={()=>void run(async()=>{await write(prefix+`/users/${u.user_id}`,{is_active:!u.membership_active},"PATCH");setTenantUsers(await api<TenantUser[]>(prefix+"/users"));toast(u.membership_active?"Vínculo suspenso.":"Vínculo ativado.")})}>{u.membership_active?"Suspender":"Ativar"}</button><button type="button" className="ghost compact-button" data-testid={`reset-password-${u.user_id}`} disabled={loading} onClick={()=>void run(async()=>{const r=await write<{user_id:string;email:string;temporary_password:string;temporary_password_expires_at:string}>(prefix+`/users/${u.user_id}/reset-password`,{});setCredential({email:r.email,password:r.temporary_password,expires:r.temporary_password_expires_at,createdAccount:true,kind:"reset"});toast("Senha temporária redefinida.")})}><KeyRound size={15}/> Redefinir senha</button></div></td></tr>)}</tbody></table></div>:!usersError&&<div className="empty user-empty"><span className="empty-icon"><Users size={22}/></span><strong>Nenhum usuário vinculado</strong><span>Adicione o primeiro acesso administrativo ou escolar desta organização.</span></div>}
           </div>
         </div>}
         {current==="invites"&&<div className="panel"><h2>Convidar usuário</h2><p className="muted">Os convites expiram em 48 horas, são de uso único e permitem ao usuário criar sua própria senha. Convites para professores podem associar um cadastro docente existente.</p><form className="grid-2" onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await write<{dev_invitation_url?:string}>(prefix+"/invitations",{...newInvite,school_id:newInvite.school_id||null,teacher_id:newInvite.teacher_id||null});setLastInvite(r.dev_invitation_url??"");setNewInvite({email:"",role_id:"",school_id:"",teacher_id:""});toast("Convite criado.")})}}><div><label>E-mail</label><input type="email" required value={newInvite.email} onChange={e=>setNewInvite({...newInvite,email:e.target.value})}/></div><div><label>Perfil</label><select required value={newInvite.role_id} onChange={e=>setNewInvite({...newInvite,role_id:e.target.value})}><option value="">Selecione</option>{roles.filter(r=>r.code!=="org_admin").map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></div><div><label>Unidade</label><select required value={newInvite.school_id} onChange={e=>setNewInvite({...newInvite,school_id:e.target.value})}><option value="">Selecione</option>{schools.map(s=><option value={s.id} key={s.id}>{s.name}</option>)}</select></div><div><label>Vincular professor (opcional, apenas perfil Professor)</label><select value={newInvite.teacher_id} onChange={e=>setNewInvite({...newInvite,teacher_id:e.target.value})}><option value="">Sem vínculo</option>{teachers.filter(t=>t.schools.includes(newInvite.school_id)).map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></div><button disabled={loading}>Enviar convite</button></form>{lastInvite&&<div className="code-link"><b>Link apenas de desenvolvimento:</b><br/><a href={lastInvite}>{lastInvite}</a></div>}</div>}
        {current==="roles"&&<><div className="panel"><h2>Perfis e permissões</h2><p className="muted">Cada perfil aplica suas permissões apenas nas unidades autorizadas. Novos perfis não podem conceder privilégios superiores aos do administrador.</p>{roles.map(r=><div key={r.id} className="outline-card" style={{marginBottom:11}}><div className="row between"><strong>{r.name}</strong><span className="pill">{r.is_system?"Padrão":"Personalizado"}</span></div><div>{r.permissions.map(x=><span className="permission" key={x}>{x}</span>)}</div></div>)}</div>{can("roles.manage")&&<div className="panel"><h2>Criar perfil personalizado</h2><form className="stack" onSubmit={e=>{e.preventDefault();void run(async()=>{await write(prefix+"/roles",newRole);setNewRole({name:"",code:"",permissions:[]});toast("Perfil criado.");await refreshData()})}}><div className="grid-2"><div><label>Nome</label><input required value={newRole.name} onChange={e=>setNewRole({...newRole,name:e.target.value})}/></div><div><label>Código (minúsculo)</label><input required pattern="[a-z][a-z0-9_-]{2,40}" value={newRole.code} onChange={e=>setNewRole({...newRole,code:e.target.value})}/></div></div><div className="grid-3">{[...new Set(roles.flatMap(r=>r.permissions))].sort().map(p=><label key={p} style={{display:"flex",gap:7,alignItems:"center"}}><input type="checkbox" style={{width:16,minHeight:16}} checked={newRole.permissions.includes(p)} onChange={e=>setNewRole(x=>({...x,permissions:e.target.checked?[...x.permissions,p]:x.permissions.filter(v=>v!==p)}))}/>{p}</label>)}</div><button disabled={loading || !newRole.permissions.length} style={{alignSelf:"start"}}>Criar perfil</button></form></div>}</>}
        {current==="requests"&&<div className="panel"><h2>Solicitações de disponibilidade</h2><p className="muted">Aprovação e simulação de impacto serão integradas na próxima etapa. Pedidos não alteram a disponibilidade nem grades publicadas.</p>{requests.length?<table className="data-table"><thead><tr><th>Professor</th><th>Faixa solicitada</th><th>Justificativa</th><th>Status</th></tr></thead><tbody>{requests.map(r=><tr key={r.id}><td>{r.teacher}</td><td>{weekdays[r.weekday]} {r.start}–{r.end}</td><td>{r.reason}</td><td><span className="pill">{r.status}</span></td></tr>)}</tbody></table>:<div className="empty">Ainda não há solicitações registradas.</div>}</div>}
        {current==="my-schedule"&&<div className="panel"><h2>Meu cadastro docente</h2>{ownTeacher?.teacher?<><p>Professor: <strong>{ownTeacher.teacher.name}</strong></p>{ownTeacher.availability?.length?<table className="data-table"><thead><tr><th>Dia</th><th>Disponível das</th><th>Até</th></tr></thead><tbody>{ownTeacher.availability.map((v,i)=><tr key={i}><td>{weekdays[v.weekday]}</td><td>{v.start}</td><td>{v.end}</td></tr>)}</tbody></table>:<div className="empty">Disponibilidade ainda não cadastrada.</div>}<hr className="hr"/><h3>Solicitar nova faixa de disponibilidade</h3><form className="grid-2" onSubmit={e=>{e.preventDefault();void run(async()=>{await write(prefix+`/teachers/${ownTeacher.teacher?.id}/availability-requests`,myRequest);setMyRequest({...myRequest,reason:""});toast("Solicitação registrada para análise.")})}}><div><label>Dia da semana</label><select value={myRequest.weekday} onChange={e=>setMyRequest({...myRequest,weekday:+e.target.value})}>{weekdays.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></div><div className="grid-2"><div><label>Início</label><input type="time" value={myRequest.start} onChange={e=>setMyRequest({...myRequest,start:e.target.value})}/></div><div><label>Fim</label><input type="time" value={myRequest.end} onChange={e=>setMyRequest({...myRequest,end:e.target.value})}/></div></div><div><label>Motivo</label><input required minLength={5} maxLength={600} value={myRequest.reason} onChange={e=>setMyRequest({...myRequest,reason:e.target.value})}/></div><div style={{display:"flex",alignItems:"end"}}><button disabled={loading} style={{width:"100%"}}>Enviar solicitação</button></div></form></>:<div className="empty">Sua conta ainda não foi vinculada a um cadastro de professor da organização.</div>}</div>}
        {current==="audit"&&<div className="panel"><h2>Últimas ações administrativas</h2>{audit.length?<table className="data-table"><thead><tr><th>Data</th><th>Ação</th><th>Objeto</th></tr></thead><tbody>{audit.map(x=><tr key={x.id}><td>{new Date(x.date).toLocaleString("pt-BR")}</td><td>{x.action}</td><td>{x.type}</td></tr>)}</tbody></table>:<div className="empty">Nenhum evento registrado.</div>}</div>}
      </div>
       <nav className="mobile-nav">{visibleNav.slice(0,4).map(item=><button key={item.id} onClick={()=>setTab(item.id)}><item.icon size={20}/>{item.label.split(" ")[0]}</button>)}</nav>
     </main>
     {credential&&<div className="modal-backdrop" role="presentation">
       <section className="credential-dialog" role="dialog" aria-modal="true" aria-labelledby="credential-title" data-testid="credential-dialog">
         <button type="button" className="ghost dialog-close" data-testid="credential-close" aria-label="Fechar e limpar credencial" onClick={()=>{setCredential(null);setCopyNotice("")}}><X size={19}/></button>
         <div className="credential-mark"><KeyRound size={22}/></div>
         <span className="eyebrow">{credential.kind==="reset"?"Redefinição de acesso":credential.kind==="organization"?"Primeiro administrador":"Novo acesso"}</span>
          <h2 id="credential-title">{credential.invitationUrl?"Convite de acesso para o primeiro administrador":credential.invitationSent?"Convite enviado para o primeiro administrador":credential.createdAccount?"Conta criada com senha temporária":"Vínculo criado para conta existente"}</h2>
          <p className="muted">{credential.invitationUrl?"Link de homologação deste ambiente; nenhum e-mail real foi enviado.":credential.invitationSent?"O convite foi enviado para o e-mail cadastrado; a pessoa criará sua própria senha.":credential.createdAccount?"Compartilhe esta credencial com segurança. Ela será exibida somente agora e deverá ser substituída no primeiro acesso.":"A conta já existia. A senha atual foi preservada; nenhum convite foi enviado."}</p>
         <div className="credential-email"><span>E-mail</span><strong>{credential.email}</strong></div>
          {credential.invitationUrl&&<div className="code-link" data-testid="dev-invitation-link"><a href={credential.invitationUrl} target="_blank" rel="noreferrer">Ativar acesso ao Horário Inteligente</a></div>}
          {credential.invitationSent&&!credential.invitationUrl&&<div className="copy-feedback" role="status" data-testid="invitation-sent-status">Convite enviado por e-mail.</div>}
          {credential.password?<><div className="secret-label">Senha temporária · visível uma única vez</div><div className="secret-value" data-testid="temporary-password-value">{credential.password}</div><button type="button" className="copy-button" data-testid="copy-temporary-password" onClick={async()=>{try{await navigator.clipboard.writeText(credential.password??"");setCopyNotice("Senha copiada para a área de transferência.")}catch{setCopyNotice("Não foi possível copiar automaticamente. Copie a senha exibida com cuidado.")}}}><Copy size={16}/> Copiar senha</button>{copyNotice&&<div className="copy-feedback" role="status" data-testid="copy-status">{copyNotice}</div>}{credential.expires&&<p className="credential-expiry" data-testid="temporary-password-expiry">Expira em {new Date(credential.expires).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"})}.</p>}</>:credential.invitationUrl||credential.invitationSent?null:<div className="existing-account-note" data-testid="existing-account-note"><ShieldCheck size={17}/><span>Senha existente mantida. O usuário seguirá usando a senha já cadastrada.</span></div>}
         <button type="button" className="dialog-done" data-testid="credential-done" onClick={()=>{setCredential(null);setCopyNotice("")}}>Entendi e fechar</button>
          <p className="hint credential-warning">Depois de fechar, esta credencial não será mostrada novamente. A senha de uma conta já existente permanece inalterada.</p>
       </section>
     </div>}
  </div>;
}
