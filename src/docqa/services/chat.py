import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from docqa.config import get_settings
from docqa.core.chat_model import get_chat_client
from docqa.core.embeddings import get_embeddings_client
from docqa.core.vector_store import query_chunk_vectors
from docqa.exceptions import ChatGenerationError, ExternalServiceNotConfiguredError
from docqa.models.document import Document
from docqa.models.document_chunk import DocumentChunk
from docqa.schemas.chat import Citation

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a document Q&A assistant. Answer the question using ONLY the "
    "numbered context sources below — never use outside knowledge, even for "
    "things that seem like common or general knowledge (e.g. how to write "
    "standard code, well-known facts, or definitions not actually stated in "
    "the sources). Cite the sources you used inline like [1], [2]. "
    "If the question has multiple parts, evaluate each part independently: "
    "answer only the parts the sources actually support, and for any part "
    "they don't cover, say plainly that the uploaded documents don't cover "
    "it — do not fill that gap from your own knowledge. If none of the "
    "sources contain enough information to answer the question at all, "
    "respond with exactly: "
    '"I don\'t have enough information in the uploaded documents to answer that." '
    "Earlier turns of the conversation may be included for context; only the "
    "numbered sources for the *current* question are grounds for citation."
)

_NO_MATCH_ANSWER = "I don't have enough information in the uploaded documents to answer that."


def answer_question(
    tenant_db: Session,
    *,
    tenant_id: uuid.UUID,
    tenant_schema_name: str,
    question: str,
    history: list[tuple[str, str]] | None = None,
) -> tuple[str, list[Citation]]:
    """Runs the full RAG pipeline for one question, scoped to one tenant's
    Pinecone namespace and Postgres schema: embed -> retrieve -> resolve
    citations from Postgres -> generate a grounded answer.

    Matches below `chat_score_threshold` are dropped before the LLM ever
    sees them, so an unrelated question can't retrieve a citation to a
    document that wasn't actually a good match (see
    docs/ARCHITECTURE.md, acceptance criteria).

    `history` is `(role, content)` pairs from earlier turns of the same
    conversation, oldest first — see services/conversation.py, which is
    what loads it from Postgres and bounds it to `chat_history_turns`.
    Retrieval still embeds only the current `question`; history is replayed
    to the model purely so it can resolve references like "it" or "that
    one" in its own answer, not to improve what gets retrieved (no query
    rewriting — see docs/ARCHITECTURE.md).
    """
    settings = get_settings()
    log_context = {"tenant_id": str(tenant_id)}

    try:
        question_vector = get_embeddings_client().embed_query(question)
        matches: list[tuple[str, float]] = query_chunk_vectors(
            namespace=tenant_schema_name, vector=question_vector, top_k=settings.chat_top_k
        )
    except ExternalServiceNotConfiguredError:
        raise
    except Exception as exc:
        logger.exception("chat retrieval failed", extra=log_context)
        raise ChatGenerationError(f"retrieval failed: {exc}") from exc

    relevant = [
        (vector_id, score) for vector_id, score in matches if score >= settings.chat_score_threshold
    ]
    if not relevant:
        logger.info("chat question had no relevant matches", extra=log_context)
        return _NO_MATCH_ANSWER, []

    vector_ids = [vector_id for vector_id, _ in relevant]
    rows = (
        tenant_db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(DocumentChunk.pinecone_vector_id.in_(vector_ids))
        .all()
    )
    by_vector_id = {chunk.pinecone_vector_id: (chunk, document) for chunk, document in rows}

    context_lines = []
    citations: list[Citation] = []
    seen_citations: set[tuple[str, int]] = set()
    source_number = 0
    for vector_id, _score in relevant:
        resolved = by_vector_id.get(vector_id)
        if resolved is None:
            # Vector exists in Pinecone but its Postgres row is gone (e.g. a
            # re-ingestion cleared and replaced it between the two calls).
            # Postgres is the source of truth for what's citable — skip it.
            continue
        chunk, document = resolved
        source_number += 1
        context_lines.append(
            f"[{source_number}] ({document.filename}, page {chunk.page_number}): {chunk.chunk_text}"
        )
        dedup_key = (str(document.id), chunk.page_number)
        if dedup_key not in seen_citations:
            seen_citations.add(dedup_key)
            citations.append(
                Citation(
                    document_id=document.id,
                    filename=document.filename,
                    page_number=chunk.page_number,
                )
            )

    if not context_lines:
        logger.info(
            "chat question's matches did not resolve to any citable chunk", extra=log_context
        )
        return _NO_MATCH_ANSWER, []

    human_prompt = f"Context sources:\n{chr(10).join(context_lines)}\n\nQuestion: {question}"

    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=_SYSTEM_PROMPT)
    ]
    for role, content in history or []:
        messages.append(
            HumanMessage(content=content) if role == "user" else AIMessage(content=content)
        )
    messages.append(HumanMessage(content=human_prompt))

    try:
        response = get_chat_client().invoke(messages)
    except ExternalServiceNotConfiguredError:
        raise
    except Exception as exc:
        logger.exception("chat generation failed", extra=log_context)
        raise ChatGenerationError(f"answer generation failed: {exc}") from exc

    logger.info("chat question answered", extra={**log_context, "citation_count": len(citations)})
    return response.content, citations
