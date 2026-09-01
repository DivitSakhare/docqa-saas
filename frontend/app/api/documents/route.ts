import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/backend-fetch";
import type { DocumentSummary, DocumentUploadResult } from "@/lib/types";

interface BackendDocument {
  id: string;
  filename: string;
  doc_type: string;
  status: string;
  page_count: number | null;
  uploaded_at: string;
}

export async function GET() {
  const res = await backendFetch("/api/v1/documents");
  if (!res.ok) {
    return NextResponse.json({ detail: "Could not load documents." }, { status: res.status });
  }
  const body: BackendDocument[] = await res.json();

  const documents: DocumentSummary[] = body.map((doc) => ({
    id: doc.id,
    filename: doc.filename,
    docType: doc.doc_type,
    status: doc.status as DocumentSummary["status"],
    pageCount: doc.page_count,
    uploadedAt: doc.uploaded_at,
  }));
  return NextResponse.json(documents);
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const res = await backendFetch("/api/v1/documents", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Upload failed." }));
    return NextResponse.json(body, { status: res.status });
  }

  const body = await res.json();
  const result: DocumentUploadResult = {
    documentId: body.document_id,
    jobId: body.job_id,
    filename: body.filename,
    status: body.status,
  };
  return NextResponse.json(result, { status: 202 });
}
