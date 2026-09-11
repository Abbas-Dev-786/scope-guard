"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Client = { id:string; name:string; company:string|null; row_version:number };
type Page = { items:Client[]; next_cursor:string|null };

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setClients((await api<Page>("/api/v1/clients")).items); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load clients"); }
  }, []);
  useEffect(() => {
    let active = true;
    api<Page>("/api/v1/clients")
      .then((page) => { if (active) { setClients(page.items); setError(""); } })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load clients"); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api<Client>("/api/v1/clients", { method:"POST", body:JSON.stringify({name, company:company || null}) }); setName(""); setCompany(""); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to create client"); }
    finally { setBusy(false); }
  }

  return <>
    <p className="eyebrow muted">Relationships</p><h1>Clients</h1>
    <p className="lede">Client records stay inside the authenticated tenant. Add contacts after the client exists; shared contacts can later require an explicit project assignment.</p>
    {error && <p className="error">{error} <Link href="/sign-in">Open sign in</Link></p>}
    <form className="card row" onSubmit={submit}>
      <label>Name<input value={name} onChange={e=>setName(e.target.value)} required /></label>
      <label>Company<input value={company} onChange={e=>setCompany(e.target.value)} /></label>
      <button disabled={busy}>{busy ? "Saving…" : "Add client"}</button>
    </form>
    <div className="list" style={{marginTop:20}}>{clients.map(client=><Link className="listItem" href={`/clients/${client.id}`} key={client.id}><div><strong>{client.name}</strong><div className="muted">{client.company ?? "Independent client"}</div></div><span className="muted">Manage · v{client.row_version}</span></Link>)}{!error && clients.length===0 && <p className="muted">No clients yet.</p>}</div>
  </>;
}
