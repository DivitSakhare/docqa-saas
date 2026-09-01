import uuid

from fastapi import APIRouter

from docqa.core.deps import CurrentUser, TenantDB
from docqa.schemas.conversation import ConversationDetail, ConversationSummary, MessageResponse
from docqa.services.conversation import get_conversation_detail, list_conversations

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_my_conversations(
    tenant_db: TenantDB, current_user: CurrentUser
) -> list[ConversationSummary]:
    """Lists the caller's own conversations, most recently active first —
    never another user's, even within the same tenant."""
    pairs = list_conversations(tenant_db, user_id=current_user.id)
    return [
        ConversationSummary(
            id=conversation.id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=message_count,
        )
        for conversation, message_count in pairs
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_my_conversation(
    tenant_db: TenantDB, current_user: CurrentUser, conversation_id: uuid.UUID
) -> ConversationDetail:
    """Raises 404 for a conversation that doesn't exist or belongs to
    another user — the two cases are indistinguishable in the response."""
    conversation, messages = get_conversation_detail(
        tenant_db, conversation_id=conversation_id, user_id=current_user.id
    )
    return ConversationDetail(
        id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                citations=message.citations,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
