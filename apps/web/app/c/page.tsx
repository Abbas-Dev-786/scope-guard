"use client";

import { useEffect, useState } from "react";

type Review = {
  change_order_id: string; revision_id: string; revision_number: number; status: string; title: string;
  requested_change: string; deliverables: string[]; exclusions: string[]; assumptions: string[];
  client_explanation: string; recipient_email: string; subject: string; plain_text_body: string;
  html_body: string; terms: Record<string, unknown>; row_version?: number; content_hash?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
async function readApiResponse<T extends Record<string, unknown> = Record<string, unknown>>(response: Response): Promise<T & { message?: string; raw?: string }> {
  const raw = await response.text();
  if (!raw) return {} as T & { message?: string; raw?: string };
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return { ...parsed, raw } as T & { message?: string; raw?: string };
  } catch {
    return { raw } as T & { message?: string; raw?: string };
  }
}

export default function ClientReviewPage() {
  const [review, setReview] = useState<Review | null>(null);
  const [csrf, setCsrf] = useState("");
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [paymentLink, setPaymentLink] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("t");
    if (!token) { queueMicrotask(() => setError("This approval link is missing its capability token.")); return; }
    window.history.replaceState(null, "", window.location.pathname);
    void (async () => {
      try {
        const exchanged = await fetch(`${API_BASE}/public/v1/capabilities/exchange`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
        const exchangeBody = await readApiResponse<{ csrf_token: string; change_order_id: string }>(exchanged);
        if (!exchanged.ok) throw new Error(exchangeBody.message ?? exchangeBody.raw ?? `Approval exchange failed (${exchanged.status}).`);
        setCsrf(exchangeBody.csrf_token);
        const response = await fetch(`${API_BASE}/public/v1/change-orders/${exchangeBody.change_order_id}`, { credentials: "include", cache: "no-store" });
        const body = await readApiResponse<Review>(response);
        if (!response.ok) throw new Error(body.message ?? body.raw ?? `The proposal could not be loaded (${response.status}).`);
        setReview(body);
      } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load this proposal."); }
    })();
  }, []);

  async function pollReceipt() {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, attempt < 20 ? 3000 : 15000));
      const response = await fetch(`${API_BASE}/public/v1/change-orders/${review?.change_order_id}/receipt`, { credentials: "include", cache: "no-store" });
      if (!response.ok) continue;
      const receipt = await response.json() as { payment_status?: string; payment_link_url?: string | null };
      if (receipt.payment_link_url) setPaymentLink(receipt.payment_link_url);
      setMessage(`Approved. Receipt status: ${receipt.payment_status ?? "CREATION_PENDING"}.`);
      if (receipt.payment_status && receipt.payment_status !== "CREATION_PENDING") return;
    }
  }

  async function decide(path: "approve" | "request-changes" | "reject") {
    if (!review) return;
    setBusy(true); setError("");
    try {
      const body = path === "approve"
        ? { expected_row_version: review.row_version ?? 0, revision_id: review.revision_id, content_hash: review.content_hash ?? "" }
        : { expected_row_version: review.row_version ?? 0, revision_id: review.revision_id, content_hash: review.content_hash ?? "", comment };
      const response = await fetch(`${API_BASE}/public/v1/change-orders/${review.change_order_id}/${path}`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      const result = await readApiResponse<{ status: string }>(response);
      if (!response.ok) throw new Error(result.message ?? result.raw ?? `The proposal action failed (${response.status}).`);
      setMessage(path === "approve" ? "Approved. Your receipt is being prepared." : path === "reject" ? "The proposal was declined." : "Changes requested. The freelancer will review them.");
      if (path === "approve") void pollReceipt();
      setReview({ ...review, status: result.status });
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The proposal action failed."); }
    finally { setBusy(false); }
  }

  if (error) return <><p className="eyebrow muted">Client review</p><h1>Approval link unavailable</h1><p className="error">{error}</p></>;
  if (!review) return <><p className="eyebrow muted">Client review</p><h1>Loading proposal…</h1><p className="lede">Verifying this one-time approval link.</p></>;

  const terminal = review.status !== "AWAITING_CLIENT_APPROVAL";
  return <><p className="eyebrow muted">Client review · revision {review.revision_number}</p><h1>{review.title}</h1>
    <p className="lede">{review.client_explanation}</p>
    <section className="card stack"><h2>Requested change</h2><p>{review.requested_change}</p><h2>Deliverables</h2><ul>{review.deliverables.map((item) => <li key={item}>{item}</li>)}</ul>
      <h2>Proposal message</h2><pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{review.plain_text_body}</pre>
      <p className="muted">Total: {String(review.terms.total_minor ?? "—")} {String(review.terms.currency ?? "INR")}</p>
    </section>
    {!terminal && <section className="card stack"><label>Comment (optional)<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={4} /></label>
      <div className="row"><button disabled={busy} onClick={() => void decide("approve")}>Approve proposal</button><button disabled={busy} onClick={() => void decide("request-changes")}>Request changes</button><button className="danger" disabled={busy} onClick={() => void decide("reject")}>Decline</button></div>
    </section>}
    {message && <p className="success">{message}</p>}
    {paymentLink && <section className="card stack"><h2>Payment link</h2><p>Your payment link is ready.</p><a className="button" href={paymentLink} target="_blank" rel="noreferrer">Open payment link</a></section>}
  </>;
}
