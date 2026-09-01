import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/backend-fetch";
import type { ConversationDetail, Message } from "@/lib/types";

interface BackendCitation {
  document_id: string;
  filename: string;
  page_number: number;
}

interface BackendMessage {
  id: string;
  role: string;
  content: string;
  citations: BackendCitation[] | null;
  created_at: string;
}

interface BackendConversationDetail {
  id: string;
  created_at: string;
  updated_at: string;
  messages: BackendMessage[];
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await backendFetch(`/api/v1/conversations/${id}`);
  if (!res.ok) {
    return NextResponse.json({ detail: "Conversation not found." }, { status: res.status });
  }
  const body: BackendConversationDetail = await res.json();

  const messages: Message[] = body.messages.map((m) => ({
    id: m.id,
    role: m.role as Message["role"],
    content: m.content,
    citations: m.citations
      ? m.citations.map((c) => ({
          documentId: c.document_id,
          filename: c.filename,
          pageNumber: c.page_number,
        }))
      : null,
    createdAt: m.created_at,
  }));

  const detail: ConversationDetail = {
    id: body.id,
    createdAt: body.created_at,
    updatedAt: body.updated_at,
    messages,
  };
  return NextResponse.json(detail);
}
