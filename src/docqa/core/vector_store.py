from functools import lru_cache

from pinecone import Index, Pinecone, ServerlessSpec

from docqa.config import get_settings
from docqa.exceptions import ExternalServiceNotConfiguredError


@lru_cache
def _get_pinecone_client() -> Pinecone:
    settings = get_settings()
    if not settings.pinecone_api_key:
        raise ExternalServiceNotConfiguredError("PINECONE_API_KEY is not configured")
    return Pinecone(api_key=settings.pinecone_api_key)


@lru_cache
def get_pinecone_index() -> Index:
    """Returns the single shared index, creating it if this is the first
    call. All tenant isolation happens one level down, via namespaces
    within this index — not via separate indexes per tenant.
    """
    settings = get_settings()
    client = _get_pinecone_client()

    if settings.pinecone_index_name not in client.list_indexes().names():
        client.create_index(
            name=settings.pinecone_index_name,
            dimension=settings.embedding_dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
        )

    return client.Index(settings.pinecone_index_name)


def upsert_chunk_vectors(*, namespace: str, vectors: list[tuple[str, list[float], dict]]) -> None:
    """`vectors` is a list of (vector_id, embedding, metadata) tuples, all
    written into `namespace` — the tenant's own slice of the shared index,
    per Pinecone's documented multi-tenancy pattern.
    """
    get_pinecone_index().upsert(vectors=vectors, namespace=namespace)


def query_chunk_vectors(
    *, namespace: str, vector: list[float], top_k: int
) -> list[tuple[str, float]]:
    """Returns up to `top_k` (vector_id, cosine_score) pairs from `namespace`
    only — the tenant's own slice of the shared index — ordered by
    similarity. Metadata isn't requested here: the vector id is enough to
    resolve the chunk (and its citation) from Postgres, which is the
    source of truth for that data (see docs/ARCHITECTURE.md, State
    ownership).
    """
    response = get_pinecone_index().query(
        vector=vector, top_k=top_k, namespace=namespace, include_metadata=False
    )
    return [(match["id"], match["score"]) for match in response["matches"]]
