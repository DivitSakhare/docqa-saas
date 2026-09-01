import uuid

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    # Omit to start a new conversation; pass a prior response's
    # conversation_id to continue it — the caller's own turn history is
    # then replayed to the model as context (see config.chat_history_turns).
    conversation_id: uuid.UUID | None = None


class Citation(BaseModel):
    document_id: uuid.UUID
    filename: str
    page_number: int


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conversation_id: uuid.UUID
