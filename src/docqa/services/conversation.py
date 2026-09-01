import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from docqa.config import get_settings
from docqa.exceptions import ConversationNotFoundError
from docqa.models.conversation import Conversation
from docqa.models.message import Message, MessageRole
from docqa.schemas.chat import Citation
from docqa.services.chat import answer_question


def _load_history(tenant_db: Session, *, conversation_id: uuid.UUID) -> list[tuple[str, str]]:
    max_messages = get_settings().chat_history_turns * 2
    rows = (
        tenant_db.query(Message.role, Message.content)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
        .all()
    )
    return [(role, content) for role, content in reversed(rows)]


def answer_within_conversation(
    tenant_db: Session,
    *,
    tenant_id: uuid.UUID,
    tenant_schema_name: str,
    user_id: uuid.UUID,
    question: str,
    conversation_id: uuid.UUID | None,
) -> tuple[Conversation, str, list[Citation]]:
    """Orchestrates one chat turn: resolves (or defers creating) the
    conversation, loads its prior turns as context, runs the RAG pipeline,
    and persists both sides of the new turn.

    Nothing is written to the database until generation actually succeeds —
    a brand-new conversation is only constructed in memory, not added to
    the session, until there's a real answer to attach to it. A failed
    generation attempt (NVIDIA NIM down, retrieval error) therefore leaves
    no orphaned empty conversation behind for the caller to never see
    again, since the exception means no conversation_id was ever returned
    to reference it by.
    """
    if conversation_id is not None:
        conversation = tenant_db.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise ConversationNotFoundError()
        history = _load_history(tenant_db, conversation_id=conversation.id)
    else:
        conversation = None
        history = []

    answer, citations = answer_question(
        tenant_db,
        tenant_id=tenant_id,
        tenant_schema_name=tenant_schema_name,
        question=question,
        history=history,
    )

    if conversation is None:
        conversation = Conversation(user_id=user_id)
        tenant_db.add(conversation)
        tenant_db.flush()

    tenant_db.add(
        Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=question)
    )
    tenant_db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT.value,
            content=answer,
            citations=[c.model_dump(mode="json") for c in citations] or None,
        )
    )
    conversation.updated_at = datetime.now(UTC)
    tenant_db.commit()
    tenant_db.refresh(conversation)

    return conversation, answer, citations


def list_conversations(tenant_db: Session, *, user_id: uuid.UUID) -> list[tuple[Conversation, int]]:
    """Returns (conversation, message_count) pairs, most recently active
    first — private to the caller, never another user's conversations even
    within the same tenant (see models/conversation.py)."""
    return (
        tenant_db.query(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user_id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


def get_conversation_detail(
    tenant_db: Session, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Conversation, list[Message]]:
    conversation = tenant_db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise ConversationNotFoundError()

    messages = (
        tenant_db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return conversation, messages
