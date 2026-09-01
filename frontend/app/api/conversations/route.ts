import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/backend-fetch";
import type { ConversationSummary } from "@/lib/types";

interface BackendConversationSummary {
  id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export async function GET() {
  const res = await backendFetch("/api/v1/conversations");
  if (!res.ok) {
    return NextResponse.json({ detail: "Could not load conversations." }, { status: res.status });
  }
  const body: BackendConversationSummary[] = await res.json();

  const conversations: ConversationSummary[] = body.map((c) => ({
    id: c.id,
    createdAt: c.created_at,
    updatedAt: c.updated_at,
    messageCount: c.message_count,
  }));
  return NextResponse.json(conversations);
}
