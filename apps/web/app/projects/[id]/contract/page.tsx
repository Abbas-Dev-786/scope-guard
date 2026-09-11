"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, uploadPresigned } from "@/lib/api";

type Document = { id: string; object_key: string; status: string; mime_type: string; size_bytes: number; rejection_reason: string | null };
type Grant = { document_id: string; upload_token: string; upload_url: string | null; upload_fields: Record<string, string> | null };

function toBase64(bytes: Uint8Array) {
  let output = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) output += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(output);
}

export default function ContractDocumentsPage() {
  const { id } = useParams<{ id: string }>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const refresh = useCallback(async () => setDocuments(await api<Document[]>(`/api/v1/projects/${id}/documents`)), [id]);

  useEffect(() => {
    let active = true;
    api<Document[]>(`/api/v1/projects/${id}/documents`)
      .then((next) => { if (active) setDocuments(next); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load documents"); });
    return () => { active = false; };
  }, [id]);

  async function upload() {
    if (!file) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const mimeType = file.type || "application/octet-stream";
      const grant = await api<Grant>(`/api/v1/projects/${id}/documents`, { method: "POST", body: JSON.stringify({ object_key: `contracts/${file.name}`, mime_type: mimeType, expected_size_bytes: file.size }) });
      const bytes = new Uint8Array(await file.arrayBuffer());
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const hash = Array.from(new Uint8Array(digest)).map((value) => value.toString(16).padStart(2, "0")).join("");
      if (grant.upload_url && grant.upload_fields) {
        await uploadPresigned(grant.upload_url, grant.upload_fields, file);
        await api<Document>(`/api/v1/documents/${grant.document_id}/complete-upload`, { method: "POST", body: JSON.stringify({ upload_token: grant.upload_token, sha256: hash, mime_type: mimeType }) });
      } else {
        await api<Document>(`/api/v1/documents/${grant.document_id}/complete-upload`, { method: "POST", body: JSON.stringify({ upload_token: grant.upload_token, content_base64: toBase64(bytes), sha256: hash, mime_type: mimeType }) });
      }
      setMessage("Document verified. Review its scope candidates next."); setFile(null); await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Upload failed"); }
    finally { setBusy(false); }
  }

  return <div className="stack"><p><Link href={`/projects/${id}`}>Back to project</Link></p><p className="eyebrow muted">Contract intake</p><h1>Documents and extraction</h1><p className="lede">Uploads are checksum-verified and kept separate from confirmed scope.</p>{error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}<section className="card stack"><label>Contract file<input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} /></label><button disabled={!file || busy} onClick={upload}>{busy ? "Verifying..." : "Upload and extract"}</button></section><section className="card stack"><div className="row"><h2>Document history</h2><Link className="button" href={`/projects/${id}/scope`}>Review scope</Link></div>{documents.length === 0 ? <p className="muted">No contract versions uploaded.</p> : <div className="list">{documents.map((document) => <div className="listItem" key={document.id}><span><strong>{document.object_key}</strong><br /><small>{document.mime_type} - {document.size_bytes} bytes</small></span><span className={document.status === "REJECTED" ? "error" : "notice"}>{document.status.replaceAll("_", " ")}{document.rejection_reason ? ` - ${document.rejection_reason}` : ""}</span></div>)}</div>}</section></div>;
}