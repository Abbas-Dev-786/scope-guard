"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearAccessToken, hasAccessToken } from "@/lib/api";

const publicPaths = ["/sign-in", "/auth/callback", "/c"];

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const isPublic = publicPaths.some((path) => pathname === path || pathname.startsWith(path + "/"));

  useEffect(() => {
    if (isPublic) { queueMicrotask(() => setReady(true)); return; }
    if (!hasAccessToken()) {
      router.replace("/sign-in?next=" + encodeURIComponent(pathname));
      return;
    }
    queueMicrotask(() => setReady(true));
  }, [isPublic, pathname, router]);

  if (isPublic || ready) return <>{children}</>;
  return <section className="card stack" aria-live="polite"><h1>Checking your session…</h1><p className="muted">Verifying your secure workspace session.</p><button onClick={() => { clearAccessToken(); router.replace("/sign-in"); }}>Sign in</button></section>;
}
