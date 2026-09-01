import "server-only";
import { cookies } from "next/headers";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

const ACCESS_COOKIE = "docqa_access";
const REFRESH_COOKIE = "docqa_refresh";

// Matches the backend's own token lifetimes closely enough to avoid the
// browser holding onto a cookie long after the token inside it is dead;
// the backend's own expiry is still what's actually enforced.
const ACCESS_MAX_AGE_SECONDS = 60 * 60; // config.access_token_expire_minutes default (60m)
const REFRESH_MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // config.refresh_token_expire_days default (30d)

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}

export async function setSessionCookies(accessToken: string, refreshToken: string) {
  const store = await cookies();
  store.set(ACCESS_COOKIE, accessToken, cookieOptions(ACCESS_MAX_AGE_SECONDS));
  store.set(REFRESH_COOKIE, refreshToken, cookieOptions(REFRESH_MAX_AGE_SECONDS));
}

export async function clearSessionCookies() {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

export async function getRefreshToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value;
}

export class BackendError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

/** Unauthenticated call to FastAPI — used by login/signup/refresh themselves. */
export async function publicBackendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { headers, body, ...rest } = init;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  return fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    body,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    cache: "no-store",
  });
}

async function tryRefresh(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  const res = await publicBackendFetch("/api/v1/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    await clearSessionCookies();
    return null;
  }
  const body = (await res.json()) as { access_token: string; refresh_token: string };
  await setSessionCookies(body.access_token, body.refresh_token);
  return body.access_token;
}

/**
 * Authenticated call to FastAPI from a Route Handler. Attaches the
 * access-token cookie, and on a 401 attempts exactly one `/auth/refresh`
 * (rotating both cookies) before retrying once.
 *
 * Each request here is its own isolated invocation (no shared in-process
 * state), so there's no promise-lock needed the way a client-side SPA
 * would need one — the one edge case worth naming: two genuinely
 * concurrent requests that both hit an expired access token at once can
 * race, and the second's refresh loses because the single-use refresh
 * token was already rotated by the first. Rare, and it self-heals on the
 * next request or login rather than something worth handling here.
 */
export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const store = await cookies();
  const accessToken = store.get(ACCESS_COOKIE)?.value;

  const { headers, body, ...rest } = init;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  const call = (token: string | undefined) =>
    fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      body,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      cache: "no-store",
    });

  let res = await call(accessToken);

  if (res.status === 401) {
    const refreshedToken = await tryRefresh();
    if (refreshedToken) {
      res = await call(refreshedToken);
    }
  }

  return res;
}

export async function backendFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await backendFetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new BackendError(res.status, body.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
