import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/backend-fetch";
import type { CurrentUser } from "@/lib/types";

export async function GET() {
  const res = await backendFetch("/api/v1/auth/me");
  if (!res.ok) {
    return NextResponse.json({ detail: "Not authenticated." }, { status: res.status });
  }
  const body = await res.json();
  const user: CurrentUser = {
    userId: body.user_id,
    tenantId: body.tenant_id,
    email: body.email,
    role: body.role,
  };
  return NextResponse.json(user);
}
