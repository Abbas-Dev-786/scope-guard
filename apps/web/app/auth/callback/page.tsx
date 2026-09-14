"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { completeCognitoSignIn } from "@/lib/cognito";

function Callback() {
  const query = useSearchParams();
  const router = useRouter();
  const code = query.get("code");
  const state = query.get("state");
  const inputError = query.get("error_description") ?? query.get("error") ?? (!code || !state ? "The sign-in response is incomplete." : "");
  const [exchangeError, setExchangeError] = useState("");
  useEffect(() => {
    if (inputError || !code || !state) return;
    completeCognitoSignIn(code, state)
      .then(() => { const next = sessionStorage.getItem("scopeguard_after_signin") || "/onboarding"; sessionStorage.removeItem("scopeguard_after_signin"); router.replace(next); })
      .catch((caught) => setExchangeError(caught instanceof Error ? caught.message : "Unable to complete sign-in"));
  }, [code, inputError, router, state]);
  const error = inputError || exchangeError;
  return error ? <><h1>Sign-in failed</h1><p className="error">{error}</p><Link href="/sign-in">Try again</Link></> : <><h1>Completing sign-in</h1><p className="lede">Verifying the authorization response and preparing your workspace.</p></>;
}

export default function CallbackPage() {
  return <Suspense fallback={<p>Completing sign-in…</p>}><Callback /></Suspense>;
}
