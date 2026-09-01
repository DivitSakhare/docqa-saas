// Mirrors docqa's Pydantic schemas 1:1 (src/docqa/schemas/*.py). Kept
// hand-written rather than generated — small enough surface that a
// generation step isn't worth the extra moving part.

export type UserRole = "admin" | "member";

export interface SignupInput {
  orgName: string;
  adminEmail: string;
  adminPassword: string;
}

export interface SignupResult {
  tenantId: string;
  tenantName: string;
  userId: string;
  email: string;
  role: UserRole;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface CurrentUser {
  userId: string;
  tenantId: string;
  email: string;
  role: UserRole;
}

export type DocumentStatus = "pending" | "ready" | "failed";

export interface DocumentSummary {
  id: string;
  filename: string;
  docType: string;
  status: DocumentStatus;
  pageCount: number | null;
  uploadedAt: string;
}

export interface DocumentUploadResult {
  documentId: string;
  jobId: string;
  filename: string;
  status: DocumentStatus;
}

export interface Citation {
  documentId: string;
  filename: string;
  pageNumber: number;
}

export interface ChatInput {
  question: string;
  conversationId?: string;
}

export interface ChatResult {
  answer: string;
  citations: Citation[];
  conversationId: string;
}

export type MessageRole = "user" | "assistant";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[] | null;
  createdAt: string;
}

export interface ConversationSummary {
  id: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

export interface ConversationDetail {
  id: string;
  createdAt: string;
  updatedAt: string;
  messages: Message[];
}

export interface TeamMemberInput {
  email: string;
  password: string;
  role: UserRole;
}

export interface TeamMember {
  userId: string;
  email: string;
  role: UserRole;
  createdAt: string;
}

export interface ApiErrorBody {
  detail: string;
}
