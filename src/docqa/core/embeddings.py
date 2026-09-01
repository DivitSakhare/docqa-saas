from functools import lru_cache

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

from docqa.config import get_settings
from docqa.exceptions import ExternalServiceNotConfiguredError


@lru_cache
def get_embeddings_client() -> NVIDIAEmbeddings:
    """Shared by both the ingestion worker (batched embed_documents) and the
    chat endpoint (single embed_query per question) — no explicit timeout
    override here, so both keep the client library's own bounded default
    (60s) rather than the chat endpoint's shorter budget forcing large
    ingestion batches to time out.
    """
    settings = get_settings()
    if not settings.nvidia_api_key:
        raise ExternalServiceNotConfiguredError("NVIDIA_API_KEY is not configured")
    return NVIDIAEmbeddings(model=settings.embedding_model, api_key=settings.nvidia_api_key)
