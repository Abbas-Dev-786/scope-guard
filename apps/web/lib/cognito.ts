import { saveAccessToken } from "@/lib/api";

const STATE_KEY = "scopeguard_oauth_state";
const VERIFIER_KEY = "scopeguard_pkce_verifier";
const PENDING_ACCESS_KEY = "scopeguard_pending_access_token";

function base64Url(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function configuration() {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI;
  if (!domain || !clientId || !redirectUri) throw new Error("Cognito browser configuration is incomplete.");
  return { domain: domain.replace(/\/$/, ""), clientId, redirectUri };
}

export function cognitoIsConfigured() {
  return Boolean(process.env.NEXT_PUBLIC_COGNITO_DOMAIN && process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID && process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI);
}

export async function beginCognitoSignIn() {
  const config = configuration();
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(64)));
  const state = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = base64Url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const url = new URL(`${config.domain}/oauth2/authorize`);
  url.search = new URLSearchParams({ response_type: "code", client_id: config.clientId, redirect_uri: config.redirectUri, scope: "openid email profile", state, code_challenge: challenge, code_challenge_method: "S256" }).toString();
  window.location.assign(url);
}

export async function completeCognitoSignIn(code: string, returnedState: string) {
  const config = configuration();
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  if (!expectedState || !verifier || returnedState !== expectedState) throw new Error("The sign-in response could not be verified. Start sign-in again.");
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "authorization_code", client_id: config.clientId, code, code_verifier: verifier, redirect_uri: config.redirectUri }),
  });
  const tokens = await response.json() as { id_token?: unknown; access_token?: unknown; error_description?: unknown };
  if (!response.ok || typeof tokens.id_token !== "string" || typeof tokens.access_token !== "string") {
    throw new Error(typeof tokens.error_description === "string" ? tokens.error_description : "Cognito did not return valid tokens.");
  }
  saveAccessToken(tokens.id_token);
  sessionStorage.setItem(PENDING_ACCESS_KEY, tokens.access_token);
}

export function activateCognitoAccessToken() {
  const token = sessionStorage.getItem(PENDING_ACCESS_KEY);
  if (token) {
    saveAccessToken(token);
    sessionStorage.removeItem(PENDING_ACCESS_KEY);
  }
}
