from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    storage_root: str = "./storage"
    max_upload_size_bytes: int = 25 * 1024 * 1024

    # Celery's broker. No result backend is configured — Postgres
    # (ingestion_jobs.status) is the single source of truth for job state;
    # Celery never needs to hand a return value back to anyone.
    redis_url: str = "redis://localhost:6379/0"

    # Optional (not required) so the API and its tests run fine without ever
    # touching NVIDIA/Pinecone — only the ingestion worker actually needs
    # these, and it fails one job at a time with a clear error rather than
    # refusing to start the whole app.
    nvidia_api_key: str | None = None
    pinecone_api_key: str | None = None

    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2"
    embedding_dimension: int = 2048
    pinecone_index_name: str = "docqa-saas"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    chunk_size: int = 1000
    chunk_overlap: int = 200
    ingestion_max_attempts: int = 3
    # Celery's per-task throughput cap ("N/m" = N per minute), enforced
    # declaratively instead of being an implicit side-effect of having only
    # one sequential worker — see docs/ARCHITECTURE.md, Reliability, on
    # NVIDIA NIM's free-tier rate limit.
    ingestion_rate_limit: str = "40/m"

    # NVIDIA NIM's free-tier chat model catalog churns fast and without much
    # notice — nvidia/llama-3.1-8b-instruct and most of the other obvious
    # defaults reached end-of-life on 2026-08-26 (410 Gone); the previous
    # default here, nvidia/nemotron-3-nano-30b-a3b (confirmed live on
    # 2026-08-29), had itself stopped resolving for this account by
    # 2026-09-01 (404 "Function not found for account" — a live model can
    # apparently be pulled from an account's Free Endpoint allowlist with no
    # deprecation warning, unlike the dated 410 Gone case). Of ~15 candidates
    # real-invoked against this account on 2026-09-01, only this one
    # actually returned a response. Re-verify with a real call before
    # switching, the same way the embedding model default was verified —
    # don't trust `available_models`/the catalog listing, it does not
    # reflect this account's actual entitlements.
    chat_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    chat_timeout_seconds: float = 30.0
    chat_max_tokens: int = 1024
    chat_top_k: int = 5
    # Pinecone cosine similarity below this is treated as "not relevant" and
    # excluded from both the grounding context and the returned citations —
    # this is what keeps an unrelated question from fabricating a citation
    # to a document that wasn't actually a good match.
    #
    # Was 0.3; lowered after a real E2E run (embedding model
    # nvidia/llama-nemotron-embed-vl-1b-v2) showed a genuinely-answerable
    # follow-up question ("And when do I need a receipt?") scoring 0.197
    # against the one chunk that actually answered it, while a direct
    # phrasing of the same underlying question scored 0.465 against that
    # same chunk — short, pronoun/paraphrase-heavy follow-ups score much
    # lower than keyword-overlapping questions even when fully answerable.
    # A follow-up experiment (33 real embedding calls, three classes of
    # question against three synthetic policy chunks) found: obviously-
    # unrelated questions ("capital of France") score roughly [-0.04, 0.04];
    # genuinely-relevant paraphrases/follow-ups score >=0.257; and
    # same-domain-but-genuinely-unanswerable questions ("what's the dress
    # code" against a chunk that only covers expenses) fall in between,
    # ~0.10-0.22. 0.2 keeps a large margin below every relevant score
    # observed and stays far clear of the obviously-unrelated band, at the
    # cost of occasionally letting a same-domain-adjacent question's chunk
    # through as a citation (the LLM's own "answer using ONLY these
    # sources" instruction is the backstop against actually fabricating an
    # answer from it). No absolute cutoff fully separates "relevant
    # paraphrase" from "adjacent but unanswerable" for this model on short
    # queries — see docs/ARCHITECTURE.md, Reliability section, for the
    # full writeup, including why a relative/best-match threshold and a
    # higher chat_top_k were investigated and rejected as fixes for this
    # specific failure mode.
    chat_score_threshold: float = 0.2
    # How many prior turns (question+answer pairs) of a conversation get
    # replayed to the model as context for a follow-up question. Retrieval
    # itself still embeds only the latest question — no query rewriting —
    # so this only helps the model's own phrasing/coreference, not recall.
    chat_history_turns: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
