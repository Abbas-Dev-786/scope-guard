"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

type Document = { id: string; object_key: string; status: string };
type Candidate = { id: string; item_key: string; item_type: string; extracted_text: string; corrected_text: string | null; status: string };
type Scope = { version: number; content_hash: string; items: { id: string; item_key: string; item_type: string; text: string }[] };
type Extraction = { status: "PENDING" | "READY"; reason: string | null; candidates: Candidate[] };

export default function ScopeReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [scope, setScope] = useState<Scope | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [extracting, setExtracting] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const items = await api<Document[]>(`/api/v1/projects/${id}/documents`);
    const groups = await Promise.all(items.map((item) => api<Candidate[]>(`/api/v1/documents/${item.id}/candidates`)));
    setDocuments(items); setCandidates(groups.flat());
    try { setScope(await api<Scope>(`/api/v1/projects/${id}/scope`)); } catch { setScope(null); }
  }

  useEffect(() => {
    let active = true;
    api<Document[]>(`/api/v1/projects/${id}/documents`).then(async (items) => {
      const groups = await Promise.all(items.map((item) => api<Candidate[]>(`/api/v1/documents/${item.id}/candidates`)));
      if (!active) return;
      setDocuments(items); setCandidates(groups.flat());
      try { setScope(await api<Scope>(`/api/v1/projects/${id}/scope`)); } catch { if (active) setScope(null); }
    }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load scope"); });
    return () => { active = false; };
  }, [id]);

  async function extract(documentId: string) {
    setExtracting(documentId); setError(""); setMessage("");
    try {
      const result = await api<Extraction>(`/api/v1/documents/${documentId}/extract-scope`, { method: "POST", body: "{}" });
      setMessage(result.status === "READY" ? `Extracted ${result.candidates.length} scope candidates.` : `Extraction pending: ${result.reason ?? "model unavailable"}`);
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to extract scope"); }
    finally { setExtracting(null); }
  }

  async function confirm() {
    try { const next = await api<Scope>(`/api/v1/projects/${id}/scope/confirm`, { method: "POST", body: JSON.stringify({ candidate_ids: selected }) }); setScope(next); setMessage(`Confirmed scope version ${next.version}.`); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to confirm scope"); }
  }

  return <div className="stack"><p><Link href={`/projects/${id}/contract`}>Back to documents</Link></p><p className="eyebrow muted">Human baseline</p><h1>Review confirmed scope</h1><p className="lede">Only selected candidates with exact source chunks can become an effective scope version.</p>{error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}<section className="card stack"><h2>Contract extraction</h2>{documents.length === 0 ? <p className="muted">No documents are available.</p> : documents.map((document) => <div className="listItem" key={document.id}><span><strong>{document.object_key}</strong><br /><small>{document.status}</small></span><button disabled={extracting !== null} onClick={() => extract(document.id)}>{extracting === document.id ? "Extracting..." : "Extract candidates"}</button></div>)}</section><section className="card stack"><h2>Extracted candidates</h2>{candidates.length === 0 ? <p className="muted">No candidates are available yet.</p> : candidates.map((candidate) => <label className="listItem" key={candidate.id}><span><input type="checkbox" checked={selected.includes(candidate.id)} onChange={(event) => setSelected(event.target.checked ? [...selected, candidate.id] : selected.filter((item) => item !== candidate.id))} /> <strong>{candidate.item_key}</strong> - {candidate.item_type}<br /><small>{candidate.corrected_text ?? candidate.extracted_text}</small></span><span className="muted">{candidate.status}</span></label>)}<button disabled={selected.length === 0} onClick={confirm}>Confirm selected scope</button></section>{scope && <section className="card"><h2>Effective version {scope.version}</h2><p className="muted">{scope.content_hash}</p><div className="list">{scope.items.map((item) => <div className="listItem" key={item.id}><span><strong>{item.item_key}</strong> - {item.item_type}</span><span>{item.text}</span></div>)}</div></section>}</div>;
}