export type Membership = {tenant_id:string;tenant_name:string;tenant_status:string;school_id:string|null;school_name:string|null;role_code:string;role_name:string;permissions:string[]};
export type Me = {id:string;name:string;email:string;is_platform_admin:boolean;memberships:Membership[];csrf:string};
export type School = {id:string;name:string;timezone:string};
export type Teacher = {id:string;name:string;schools:string[]};
export type Role = {id:string;code:string;name:string;permissions:string[];is_system:boolean};
export type Availability = {weekday:number;start:string;end:string};
export type Tenant = {id:string;name:string;status:string;max_schools:number;max_teachers:number;max_users:number};

export async function api<T>(path:string, method="GET", body?:unknown, csrf?:string):Promise<T> {
  const headers:Record<string,string> = {};
  if (body !== undefined) headers["Content-Type"]="application/json";
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(path, {method, headers, credentials:"include", cache:"no-store", body: body===undefined ? undefined : JSON.stringify(body)});
  const raw = await res.json().catch(()=>null);
  if (!res.ok) throw new Error(typeof raw?.detail === "string" ? raw.detail : `Erro HTTP ${res.status}`);
  return raw as T;
}
