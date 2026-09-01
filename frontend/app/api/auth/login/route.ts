import { NextResponse } from "next/server";
import { z } from "zod";

import { publicBackendFetch, setSessionCookies } from "@/lib/backend-fetch";

const bodySchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }

  const res = await publicBackendFetch("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(parsed.data),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Login failed." }));
    return NextResponse.json(body, { status: res.status });
  }

  const body = (await res.json()) as { access_token: string; refresh_token: string };
  await setSessionCookies(body.access_token, body.refresh_token);
  return NextResponse.json({ ok: true });
}
