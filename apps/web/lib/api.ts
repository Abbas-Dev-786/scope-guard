"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function saveAccessToken(token: string) {
  sessionStorage.setItem("scopeguard_access_token", token);
}

export function clearAccessToken() {
  sessionStorage.removeItem("scopeguard_access_token");
}

export function hasAccessToken() {
  return Boolean(sessionStorage.getItem("scopeguard_access_token"));
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem("scopeguard_access_token");
  if (!token) throw new Error("Sign in before loading workspace data.");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", crypto.randomUUID());
  if (init.method && init.method !== "GET") headers.set("Idempotency-Key", crypto.randomUUID());
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message ?? `Request failed (${response.status})`);
  return body as T;
}


export async function uploadPresigned(url: string, fields: Record<string, string>, file: File): Promise<void> {
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => form.append(key, value));
  form.append("file", file);
  const response = await fetch(url, { method: "POST", body: form });
  if (!response.ok) throw new Error(`Private object upload failed (${response.status})`);
}
