import { NextResponse } from "next/server";
import { z } from "zod";

import { backendFetch } from "@/lib/backend-fetch";
import type { TeamMember } from "@/lib/types";

const bodySchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(128),
  role: z.enum(["admin", "member"]),
});

interface BackendTeamMember {
  user_id: string;
  email: string;
  role: string;
  created_at: string;
}

function mapMember(m: BackendTeamMember): TeamMember {
  return { userId: m.user_id, email: m.email, role: m.role as TeamMember["role"], createdAt: m.created_at };
}

export async function GET() {
  const res = await backendFetch("/api/v1/team/members");
  if (!res.ok) {
    return NextResponse.json({ detail: "Could not load team." }, { status: res.status });
  }
  const body: BackendTeamMember[] = await res.json();
  return NextResponse.json(body.map(mapMember));
}

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }

  const res = await backendFetch("/api/v1/team/members", {
    method: "POST",
    body: JSON.stringify(parsed.data),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Could not add teammate." }));
    return NextResponse.json(body, { status: res.status });
  }

  const body: BackendTeamMember = await res.json();
  return NextResponse.json(mapMember(body), { status: 201 });
}
