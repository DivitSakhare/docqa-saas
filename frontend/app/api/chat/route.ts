import { NextResponse } from "next/server";
import { z } from "zod";

import { backendFetch } from "@/lib/backend-fetch";
import type { ChatResult } from "@/lib/types";

const bodySchema = z.object({
  question: z.string().min(1),
  conversationId: z.string().uuid().optional(),
});

interface BackendCitation {
  document_id: string;
  filename: string;
  page_number: number;
}

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }

  const res = await backendFetch("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({
      question: parsed.data.question,
      conversation_id: parsed.data.conversationId ?? null,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "The chat service is unavailable." }));
    return NextResponse.json(body, { status: res.status });
  }

  const body = await res.json();
  const result: ChatResult = {
    answer: body.answer,
    citations: (body.citations as BackendCitation[]).map((c) => ({
      documentId: c.document_id,
      filename: c.filename,
      pageNumber: c.page_number,
    })),
    conversationId: body.conversation_id,
  };
  return NextResponse.json(result);
}
