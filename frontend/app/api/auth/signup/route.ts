import { NextResponse } from "next/server";
import { z } from "zod";

import { publicBackendFetch, setSessionCookies } from "@/lib/backend-fetch";

const bodySchema = z.object({
  orgName: z.string().min(1).max(255),
  adminEmail: z.string().email(),
  adminPassword: z.string().min(8).max(128),
});

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }

  const signupRes = await publicBackendFetch("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify({
      org_name: parsed.data.orgName,
      admin_email: parsed.data.adminEmail,
      admin_password: parsed.data.adminPassword,
    }),
  });

  if (!signupRes.ok) {
    const body = await signupRes.json().catch(() => ({ detail: "Signup failed." }));
    return NextResponse.json(body, { status: signupRes.status });
  }

  // Auto-login right after signup so the new admin lands straight in the app.
  const loginRes = await publicBackendFetch("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: parsed.data.adminEmail, password: parsed.data.adminPassword }),
  });
  if (!loginRes.ok) {
    return NextResponse.json({ ok: true, autoLoginFailed: true }, { status: 201 });
  }
  const loginBody = (await loginRes.json()) as { access_token: string; refresh_token: string };
  await setSessionCookies(loginBody.access_token, loginBody.refresh_token);
  return NextResponse.json({ ok: true });
}
