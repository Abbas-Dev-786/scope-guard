"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

type Decision = { id: string; status: string; precedence: string; candidate_projects: string[]; evidence: { resource_type?: string; resource_id?: string; source_version?: string }[]; selected_project_id: string | null };

export default function RoutingDiagnosticsPage() {
  const { id } = useParams<{ id: string }>();
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Decision[]>("/api/v1/routing-decisions")
      .then((items) => { if (active) setDecisions(items.filter((item) => item.candidate_projects.includes(id) || item.selected_project_id === id)); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load routing decisions"); });
    return () => { active = false; };
  }, [id]);
  return <div className="stack"><p><Link href={`/projects/${id}`}>Back to project</Link></p><p className="eyebrow muted">Routing diagnostics</p><h1>Unresolved integration mappings</h1><p className="lede">Ambiguous provider events stay visible until an operator assigns the correct project.</p>{error && <p className="error">{error}</p>}{decisions.length === 0 ? <section className="card"><p className="muted">No routing decisions involve this project.</p></section> : <div className="list">{decisions.map((decision) => <section className="card stack" key={decision.id}><div className="row"><strong>{decision.status}</strong><span className="muted">Precedence: {decision.precedence}</span></div><p className="muted">Candidates: {decision.candidate_projects.join(", ") || "none"}</p>{decision.evidence.map((item, index) => <small key={`${decision.id}-${index}`}>{item.resource_type ?? "resource"}: {item.resource_id ?? "unknown"} ({item.source_version ?? "no source version"})</small>)}</section>)}</div>}</div>;
}