"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearAccessToken, hasAccessToken } from "@/lib/api";

export default function SessionControls() {
  const router = useRouter();
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => { queueMicrotask(() => setSignedIn(hasAccessToken())); }, []);
  if (!signedIn) return null;
  return <button className="secondaryButton" onClick={() => { clearAccessToken(); setSignedIn(false); router.replace("/sign-in"); }}>Sign out</button>;
}
