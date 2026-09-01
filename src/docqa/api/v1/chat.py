from fastapi import APIRouter

from docqa.core.deps import CurrentTenant, CurrentUser, TenantDB
from docqa.schemas.chat import ChatRequest, ChatResponse
from docqa.services.conversation import answer_within_conversation

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    tenant_db: TenantDB, tenant: CurrentTenant, current_user: CurrentUser, body: ChatRequest
) -> ChatResponse:
    """Answers a question grounded in the caller's own tenant documents:
    retrieval happens against that tenant's Pinecone namespace only, and
    citations resolve against that tenant's Postgres schema only.

    Pass `conversation_id` from a prior response to continue that
    conversation — omit it to start a new one. Either way, the turn is
    persisted and only ever visible to the user who asked it.
    """
    conversation, answer, citations = answer_within_conversation(
        tenant_db,
        tenant_id=tenant.id,
        tenant_schema_name=tenant.schema_name,
        user_id=current_user.id,
        question=body.question,
        conversation_id=body.conversation_id,
    )
    return ChatResponse(answer=answer, citations=citations, conversation_id=conversation.id)
