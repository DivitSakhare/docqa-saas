import { NextResponse } from "next/server";

import { backendFetch, clearSessionCookies } from "@/lib/backend-fetch";

export async function POST() {
  await backendFetch("/api/v1/auth/logout-all", { method: "POST" }).catch(() => undefined);
  await clearSessionCookies();
  return NextResponse.json({ ok: true });
}
