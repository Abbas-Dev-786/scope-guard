"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Decision = { id: string; project_id: string; status: string; title: string; summary: string; created_at: string };
type Order = { id: string; number: number; status: string };

export default function ProposalsPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [orders, setOrders] = useState<Record<string, Order>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    api<Decision[]>("/api/v1/decisions?limit=100").then(setDecisions).catch((e) => setError(e instanceof Error ? e.message : "Unable to load decisions"));
  }, []);
  async function assemble(id: string) {
    setBusy(id); setError("");
    try {
      const order = await api<Order>(`/api/v1/decisions/${id}/change-order`, { method: "POST", body: "{}" });
      setOrders((old) => ({ ...old, [id]: order }));
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to assemble proposal"); }
    finally { setBusy(null); }
  }
  return <div className="stack"><p className="eyebrow muted">Proposals</p><h1>Prepare a client proposal</h1><p className="lede">Assemble an evidence-backed proposal, edit it, and send it through the connected Gmail account.</p>{error && <p className="error">{error}</p>}{decisions.length === 0 ? <section className="card"><p className="muted">No analysis decisions are available yet. Complete contract intake, scope confirmation, and analysis first.</p></section> : <div className="list">{decisions.map((decision) => <section className="card stack" key={decision.id}><div className="row"><strong>{decision.title}</strong><span className="muted">{decision.status}</span></div><p>{decision.summary}</p><small className="muted">Project {decision.project_id} · {new Date(decision.created_at).toLocaleString()}</small>{orders[decision.id] ? <Link className="button" href={`/proposals/${orders[decision.id].id}`}>Open proposal #{orders[decision.id].number}</Link> : <button disabled={busy === decision.id} onClick={() => void assemble(decision.id)}>{busy === decision.id ? "Assembling…" : "Assemble proposal"}</button>}</section>)}</div>}</div>;
}
