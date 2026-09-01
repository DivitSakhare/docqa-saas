import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Only the presence of a session is checked here — the refresh cookie is
// the longer-lived of the two, so it's the better proxy for "has a
// session at all". Actual token validity is enforced per-request by the
// backend itself (through the BFF route handlers), not here; a stale or
// invalid cookie just means the first API call the client makes gets a
// real 401, which the client treats as "go to /login".
const SESSION_COOKIE = "docqa_refresh";
const PUBLIC_PATHS = new Set(["/", "/login", "/signup"]);
const AUTH_ONLY_PATHS = new Set(["/login", "/signup"]);

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (hasSession && AUTH_ONLY_PATHS.has(pathname)) {
    return NextResponse.redirect(new URL("/documents", request.url));
  }

  if (!hasSession && !PUBLIC_PATHS.has(pathname) && !pathname.startsWith("/api")) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
