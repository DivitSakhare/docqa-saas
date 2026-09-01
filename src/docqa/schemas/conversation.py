import uuid
from datetime import datetime

from pydantic import BaseModel

from docqa.schemas.chat import Citation


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] | None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
