"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Connection = {
  id: string;
  provider_account_id: string;
  account_email: string;
  status: string;
  committed_history_id: string | null;
  watch_expiry: string | null;
  last_success_at: string | null;
  sync_status: string;
  last_error: string | null;
  watch_expiry_warning: boolean;
  stale_sync_warning: boolean;
};

export default function IntegrationsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setConnections(await api<Connection[]>("/api/v1/integrations/health")); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load integrations"); }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function connect() {
    setBusy(true); setError("");
    try {
      const result = await api<{ authorization_url: string }>("/api/v1/integrations/gmail/connect", { method: "POST", body: "{}" });
      window.location.assign(result.authorization_url);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to start Gmail connection"); setBusy(false); }
  }

  async function disconnect(id: string) {
    setBusy(true); setError("");
    try { await api<Connection>(`/api/v1/integrations/gmail/${id}`, { method: "DELETE" }); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to disconnect Gmail"); }
    finally { setBusy(false); }
  }

  return <>
    <p className="eyebrow muted">Integrations</p><h1>Gmail</h1>
    <p className="lede">Connect one authorized mailbox for durable inbound routing and controlled outbound sends.</p>
    <p><button onClick={() => void connect()} disabled={busy}>Connect Gmail</button></p>
    {error && <p className="error">{error}</p>}
    <div className="stack">{connections.map((connection) => <section className="card stack" key={connection.id}>
      <div className="row"><strong>{connection.account_email}</strong><span className="muted">{connection.status}</span></div>
      <p className="muted">History checkpoint: {connection.committed_history_id ?? "not established"} · Sync: {connection.sync_status}</p>
      <p className="muted">Last success: {connection.last_success_at ? new Date(connection.last_success_at).toLocaleString() : "never"}</p>
      {connection.watch_expiry_warning && <p className="notice">Gmail watch expires within 24 hours.</p>}
      {connection.stale_sync_warning && <p className="notice">Sync is stale or has not completed yet.</p>}
      {connection.last_error && <p className="error">{connection.last_error}</p>}
      <p><button className="danger" onClick={() => void disconnect(connection.id)} disabled={busy || connection.status === "DISCONNECTED"}>Disconnect</button></p>
    </section>)}</div>
  </>;
}
