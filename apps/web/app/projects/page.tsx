"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Client = { id:string; name:string };
type Project = { id:string; name:string; status:string; timezone:string; base_contract_value_minor:number; row_version:number };
type Page<T> = { items:T[]; next_cursor:string|null };

export default function ProjectsPage() {
  const [clients,setClients]=useState<Client[]>([]); const [projects,setProjects]=useState<Project[]>([]);
  const [clientId,setClientId]=useState(""); const [name,setName]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  const load=useCallback(async()=>{try{const [clientPage,projectPage]=await Promise.all([api<Page<Client>>("/api/v1/clients"),api<Page<Project>>("/api/v1/projects")]);setClients(clientPage.items);setProjects(projectPage.items);setClientId(current=>current||clientPage.items[0]?.id||"");setError("");}catch(caught){setError(caught instanceof Error?caught.message:"Unable to load projects");}},[]);
  useEffect(() => {
    let active = true;
    Promise.all([api<Page<Client>>("/api/v1/clients"), api<Page<Project>>("/api/v1/projects")])
      .then(([clientPage, projectPage]) => {
        if (active) {
          setClients(clientPage.items); setProjects(projectPage.items);
          setClientId(clientPage.items[0]?.id ?? ""); setError("");
        }
      })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load projects"); });
    return () => { active = false; };
  }, []);
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{await api<Project>("/api/v1/projects",{method:"POST",body:JSON.stringify({client_id:clientId,name,base_contract_value_minor:30000000,timezone:"Asia/Kolkata",weekdays:[0,1,2,3,4],holiday_dates:[],confirmed_daily_capacity_hours:"7",target_date:null})});setName("");await load();}catch(caught){setError(caught instanceof Error?caught.message:"Unable to create project");}finally{setBusy(false);}}
  return <>
    <p className="eyebrow muted">Delivery boundaries</p><h1>Projects</h1>
    <p className="lede">Every project starts paused. Contract confirmation in Phase 03 is the only path to active monitoring and analysis.</p>
    {error&&<p className="error">{error} <Link href="/sign-in">Open sign in</Link></p>}
    <form className="card row" onSubmit={submit}><label>Client<select value={clientId} onChange={e=>setClientId(e.target.value)} required><option value="">Choose a client</option>{clients.map(client=><option key={client.id} value={client.id}>{client.name}</option>)}</select></label><label>Project name<input value={name} onChange={e=>setName(e.target.value)} required /></label><button disabled={busy||!clientId}>{busy?"Saving…":"Create paused project"}</button></form>
    <div className="list" style={{marginTop:20}}>{projects.map(project=><Link className="listItem" href={`/projects/${project.id}`} key={project.id}><div><strong>{project.name}</strong><div className="muted">{project.timezone} · ₹{(project.base_contract_value_minor/100).toLocaleString("en-IN")}</div></div><span className="notice">{project.status.replaceAll("_"," ")}</span></Link>)}{!error&&projects.length===0&&<p className="muted">No projects yet.</p>}</div>
  </>;
}
