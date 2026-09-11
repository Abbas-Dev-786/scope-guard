"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { activateCognitoAccessToken } from "@/lib/cognito";

type OnboardingResult = { user: { id: string; verified_email: string }; preference: { version: number } };

export default function OnboardingPage() {
  const router = useRouter();
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata");
  const [rate, setRate] = useState("100000");
  const [minimum, setMinimum] = useState("1500000");
  const [increment, setIncrement] = useState("50000");
  const [style, setStyle] = useState("professional");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api<OnboardingResult>("/api/v1/onboarding", { method: "POST", body: JSON.stringify({ timezone, rate_minor: Number(rate), minimum_minor: Number(minimum), increment_minor: Number(increment), communication_style: style, reminder_policy: { approval_required: true, steps_days: [3, 7, 14] } }) });
      activateCognitoAccessToken();
      router.push("/projects");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create workspace");
    } finally { setBusy(false); }
  }

  return <>
    <p className="eyebrow muted">First-time setup</p><h1>Confirm your workspace</h1>
    <p className="lede">Your verified Cognito address becomes the notification identity. Amounts below are integer paise: ₹1,000/hour is 100000 and ₹15,000 is 1500000.</p>
    {error && <p className="error">{error} <Link href="/sign-in">Return to sign in</Link></p>}
    <form className="card stack" onSubmit={submit}>
      <label>IANA timezone<input value={timezone} onChange={(event) => setTimezone(event.target.value)} required /></label>
      <div className="row">
        <label>Hourly rate (paise)<input type="number" min="1" max="100000000" value={rate} onChange={(event) => setRate(event.target.value)} required /></label>
        <label>Minimum fee (paise)<input type="number" min="1" max="100000000" value={minimum} onChange={(event) => setMinimum(event.target.value)} required /></label>
        <label>Rounding increment (paise)<input type="number" min="1" max="100000000" value={increment} onChange={(event) => setIncrement(event.target.value)} required /></label>
      </div>
      <label>Communication style<select value={style} onChange={(event) => setStyle(event.target.value)}><option value="professional">Professional</option><option value="concise">Concise</option><option value="warm">Warm</option></select></label>
      <button disabled={busy}>{busy ? "Creating workspace…" : "Create workspace"}</button>
    </form>
  </>;
}
