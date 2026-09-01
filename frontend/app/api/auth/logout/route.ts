import { NextResponse } from "next/server";

import { clearSessionCookies, getRefreshToken, publicBackendFetch } from "@/lib/backend-fetch";

export async function POST() {
  const refreshToken = await getRefreshToken();
  if (refreshToken) {
    await publicBackendFetch("/api/v1/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => undefined);
  }
  await clearSessionCookies();
  return NextResponse.json({ ok: true });
}
