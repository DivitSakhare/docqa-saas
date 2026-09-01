"use client";

import type { ApiErrorBody } from "./types";

export class ClientApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

/** Calls this app's own Route Handlers (never the FastAPI backend directly). */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;

  const res = await fetch(path, {
    ...init,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });

  if (!res.ok) {
    const body: ApiErrorBody = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ClientApiError(res.status, body.detail || "Something went wrong.");
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
