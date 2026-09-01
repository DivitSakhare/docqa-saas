from functools import lru_cache

from langchain_nvidia_ai_endpoints import ChatNVIDIA

from docqa.config import get_settings
from docqa.exceptions import ExternalServiceNotConfiguredError


@lru_cache
def get_chat_client() -> ChatNVIDIA:
    settings = get_settings()
    if not settings.nvidia_api_key:
        raise ExternalServiceNotConfiguredError("NVIDIA_API_KEY is not configured")
    return ChatNVIDIA(
        model=settings.chat_model,
        api_key=settings.nvidia_api_key,
        timeout=settings.chat_timeout_seconds,
        temperature=0.0,
        max_completion_tokens=settings.chat_max_tokens,
        # chat_model is a reasoning-capable model (confirmed live 2026-09-01
        # — see docs/ARCHITECTURE.md) that otherwise spends most of
        # chat_max_tokens on an internal chain-of-thought trace before ever
        # emitting the actual answer, routinely exhausting the budget before
        # a real response is produced. This disables that trace, matching
        # the vLLM/NIM convention other reasoning-toggle models also use —
        # confirmed via a real call to produce a complete, correctly cited
        # answer using zero reasoning tokens instead of a truncated one.
        chat_template_kwargs={"thinking": False},
    )
