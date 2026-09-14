"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Revision = { id: string; title: string; requested_change: string; deliverables: string[]; exclusions: string[]; assumptions: string[]; client_explanation: string; recipient_email: string; subject: string; plain_text_body: string; canonical_artifact_hash: string; approval_url: string };
type Order = { id: string; number: number; status: string; row_version: number; revision: Revision | null };
const lines = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);

export default function ProposalPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<Order | null>(null);
  const [form, setForm] = useState({ title: "", requested_change: "", deliverables: "", exclusions: "", assumptions: "", client_explanation: "", subject: "", plain_text_body: "" });
  const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const next = await api<Order>(`/api/v1/change-orders/${id}`); setOrder(next); if (next.revision) setForm({ title: next.revision.title, requested_change: next.revision.requested_change, deliverables: next.revision.deliverables.join("\n"), exclusions: next.revision.exclusions.join("\n"), assumptions: next.revision.assumptions.join("\n"), client_explanation: next.revision.client_explanation, subject: next.revision.subject, plain_text_body: next.revision.plain_text_body }); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load proposal"); }
  }, [id]);
  useEffect(() => { queueMicrotask(() => { void load(); }); }, [load]);
  const update = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));
  async function save() {
    if (!order) return; setBusy(true); setError(""); setMessage("");
    try { await api<Order>(`/api/v1/change-orders/${id}/revisions`, { method: "POST", body: JSON.stringify({ ...form, deliverables: lines(form.deliverables), exclusions: lines(form.exclusions), assumptions: lines(form.assumptions) }) }); await load(); setMessage("Saved as a new immutable revision."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to save revision"); } finally { setBusy(false); }
  }
  async function send() {
    if (!order?.revision) return; setBusy(true); setError(""); setMessage("");
    try { const next = await api<Order>(`/api/v1/change-orders/${id}/approve`, { method: "POST", body: JSON.stringify({ expected_row_version: order.row_version, revision_id: order.revision.id, content_hash: order.revision.canonical_artifact_hash }) }); setOrder(next); setMessage("Proposal approved and queued for the connected Gmail account."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to queue proposal"); } finally { setBusy(false); }
  }
  if (error && !order) return <div className="stack"><p className="error">{error}</p><Link href="/proposals">Back to proposals</Link></div>;
  if (!order) return <p className="muted">Loading proposal…</p>;
  const disabled = busy || !order.revision || ["SEND_PENDING", "AWAITING_CLIENT_APPROVAL", "CLIENT_ACCEPTED", "WITHDRAWN"].includes(order.status);
  return <div className="stack"><p><Link href="/proposals">Back to proposals</Link></p><p className="eyebrow muted">Proposal #{order.number}</p><h1>Edit and send proposal</h1><p className="lede">Status: {order.status}. Recipient: {order.revision?.recipient_email ?? "unknown"}</p>{error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}<section className="card stack"><label>Title<input value={form.title} onChange={(e) => update("title", e.target.value)} /></label><label>Requested change<textarea rows={4} value={form.requested_change} onChange={(e) => update("requested_change", e.target.value)} /></label><label>Deliverables (one per line)<textarea rows={4} value={form.deliverables} onChange={(e) => update("deliverables", e.target.value)} /></label><label>Exclusions (one per line)<textarea rows={3} value={form.exclusions} onChange={(e) => update("exclusions", e.target.value)} /></label><label>Assumptions (one per line)<textarea rows={3} value={form.assumptions} onChange={(e) => update("assumptions", e.target.value)} /></label><label>Client explanation<textarea rows={4} value={form.client_explanation} onChange={(e) => update("client_explanation", e.target.value)} /></label><label>Subject<input value={form.subject} onChange={(e) => update("subject", e.target.value)} /></label><label>Plain-text email body<textarea rows={10} value={form.plain_text_body} onChange={(e) => update("plain_text_body", e.target.value)} /></label><div className="row"><button disabled={busy} onClick={() => void save()}>Save revision</button><button disabled={disabled} onClick={() => void send()}>{order.status === "SEND_PENDING" ? "Queued" : "Approve and send via Gmail"}</button></div></section>{order.revision?.approval_url && <section className="card"><h2>Client approval link</h2><p><a href={order.revision.approval_url} target="_blank" rel="noreferrer">Open approval link</a></p></section>}</div>;
}
