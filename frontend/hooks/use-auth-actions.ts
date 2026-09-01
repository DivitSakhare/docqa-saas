"use client";

import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { LoginInput, SignupInput } from "@/lib/types";

// These opt out of the QueryClient's global 401->redirect handling (see
// app/providers.tsx) — a wrong password or duplicate signup email is an
// expected failure to show inline on the form, not a dead session.
const AUTH_MUTATION_META = { skipAuthRedirect: true };

export function useLogin() {
  return useMutation({
    mutationFn: (input: LoginInput) =>
      apiFetch<{ ok: true }>("/api/auth/login", { method: "POST", body: JSON.stringify(input) }),
    meta: AUTH_MUTATION_META,
  });
}

export function useSignup() {
  return useMutation({
    mutationFn: (input: SignupInput) =>
      apiFetch<{ ok: true }>("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    meta: AUTH_MUTATION_META,
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/auth/logout", { method: "POST" }),
    meta: AUTH_MUTATION_META,
  });
}

export function useLogoutAll() {
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/auth/logout-all", { method: "POST" }),
    meta: AUTH_MUTATION_META,
  });
}
