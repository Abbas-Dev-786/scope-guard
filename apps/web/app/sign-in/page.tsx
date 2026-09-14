"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { clearAccessToken, saveAccessToken } from "@/lib/api";
import { beginCognitoSignIn, cognitoIsConfigured } from "@/lib/cognito";

function SignInContent() {
  const router = useRouter();
  const query = useSearchParams();
  const next = query.get("next") || "/onboarding";
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const configured = cognitoIsConfigured();
  const manualTokenEnabled = process.env.NEXT_PUBLIC_ALLOW_MANUAL_TOKEN === "true";

  function save(event: FormEvent) {
    event.preventDefault();
    saveAccessToken(token.trim());
    router.push(next);
  }

  async function signIn() {
    setError("");
    try { sessionStorage.setItem("scopeguard_after_signin", next); await beginCognitoSignIn(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to start sign-in"); }
  }

  return <>
    <p className="eyebrow muted">Authentication</p><h1>Sign in</h1>
    <p className="lede">Production sign-in uses Cognito authorization code flow with PKCE. The callback verifies state before exchanging the short-lived code.</p>
    {configured ? <p><button onClick={signIn}>Continue to Cognito</button></p> : <p className="notice">Cognito browser configuration is pending Phase 00 account deployment.</p>}
    {error && <p className="error">{error}</p>}
    {manualTokenEnabled && <form className="card stack" onSubmit={save}>
      <p className="muted">Local development only</p>
      <label>Development token<input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} required /></label>
      <div className="row"><button type="submit">Use token in this tab</button><button type="button" onClick={() => { clearAccessToken(); setMessage("Session token cleared."); }}>Clear</button></div>
      {message && <p className="success">{message}</p>}
    </form>}
    <p><Link href="/">Return to overview</Link></p>
  </>;
}
export default function SignInPage() {
  return <Suspense fallback={<><p className="eyebrow muted">Authentication</p><h1>Loading sign-in…</h1></>}><SignInContent /></Suspense>;
}