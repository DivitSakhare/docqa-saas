"""Explicit cross-tenant isolation tests for the chat/RAG endpoint (phase 6).

Phase 5 added two new places a leak could happen that phase 6's
existing tenant-isolation tests (test_tenant_isolation.py) don't cover:

1. Retrieval — does the app ever query another tenant's Pinecone namespace?
2. Citation resolution — if a foreign vector id somehow came back from
   retrieval anyway, can it resolve to another tenant's document/page
   through the caller's own tenant-scoped Postgres session?

Both are tested against a namespace-partitioned fake vector store rather
than a mock that just returns whatever's configured — that way the app's
own namespace-routing code is what's actually being exercised, not a
mock's promise that it behaves the way real Pinecone namespaces would.
"""

import io

from reportlab.pdfgen import canvas

from docqa.models.document import Document
from docqa.models.document_chunk import DocumentChunk
from docqa.models.tenant import Tenant
from docqa.services import chat as chat_module
from docqa.services import ingestion as ingestion_module


def _make_pdf_bytes(text_content: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 700, text_content)
    pdf.save()
    return buffer.getvalue()


class _FakeEmbeddingsClient:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1024


class _FakeChatClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)

        class _Response:
            def __init__(self, content):
                self.content = content

        return _Response(self.response_text)


class _NamespacedFakeVectorStore:
    """Stands in for Pinecone but is a plain dict keyed by namespace — a
    query against namespace X can structurally never see what was upserted
    under namespace Y, which is exactly the property under test.
    """

    def __init__(self) -> None:
        self.by_namespace: dict[str, list[tuple[str, list[float], dict]]] = {}

    def upsert(self, *, namespace: str, vectors: list[tuple[str, list[float], dict]]) -> None:
        self.by_namespace.setdefault(namespace, []).extend(vectors)

    def query(self, *, namespace: str, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        entries = self.by_namespace.get(namespace, [])
        return [(vector_id, 1.0) for vector_id, _vec, _meta in entries[:top_k]]


def _install_fakes(
    monkeypatch, store: _NamespacedFakeVectorStore, chat_client: _FakeChatClient
) -> None:
    monkeypatch.setattr(ingestion_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        ingestion_module,
        "upsert_chunk_vectors",
        lambda *, namespace, vectors: store.upsert(namespace=namespace, vectors=vectors),
    )
    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: store.query(
            namespace=namespace, vector=vector, top_k=top_k
        ),
    )
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: chat_client)


def _signup_and_ingest(
    client, db_session, *, org_name: str, email: str, filename: str, pdf_text: str
):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"org_name": org_name, "admin_email": email, "admin_password": "a-strong-password"},
    )
    assert signup.status_code == 201
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()["access_token"]

    upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, _make_pdf_bytes(pdf_text), "application/pdf")},
    )
    assert upload.status_code == 202
    # Celery runs in eager mode for tests — the upload call above already
    # ran ingestion to completion synchronously (see conftest.py).

    tenant = db_session.query(Tenant).filter(Tenant.name == org_name).one()
    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        chunk = (
            tenant_db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).one()
        )

    return token, tenant, document, chunk


def test_chat_retrieval_never_queries_another_tenants_namespace(client, db_session, monkeypatch):
    store = _NamespacedFakeVectorStore()
    _install_fakes(monkeypatch, store, _FakeChatClient("stub answer [1]"))

    token_a, tenant_a, document_a, _chunk_a = _signup_and_ingest(
        client,
        db_session,
        org_name="Tenant A Chat",
        email="a@chatiso.example",
        filename="tenant-a-secret.pdf",
        pdf_text="Tenant A confidential content about widgets.",
    )
    token_b, tenant_b, document_b, _chunk_b = _signup_and_ingest(
        client,
        db_session,
        org_name="Tenant B Chat",
        email="b@chatiso.example",
        filename="tenant-b-secret.pdf",
        pdf_text="Tenant B confidential content about gadgets.",
    )

    # Sanity check on the test double itself: two genuinely separate
    # namespaces exist before either tenant asks a question.
    assert set(store.by_namespace.keys()) == {tenant_a.schema_name, tenant_b.schema_name}

    response_a = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"question": "Tell me about the confidential content."},
    )
    assert response_a.status_code == 200
    citations_a = response_a.json()["citations"]
    assert len(citations_a) == 1
    assert citations_a[0]["document_id"] == str(document_a.id)
    assert citations_a[0]["filename"] == "tenant-a-secret.pdf"

    response_b = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"question": "Tell me about the confidential content."},
    )
    assert response_b.status_code == 200
    citations_b = response_b.json()["citations"]
    assert len(citations_b) == 1
    assert citations_b[0]["document_id"] == str(document_b.id)
    assert citations_b[0]["filename"] == "tenant-b-secret.pdf"

    # Neither tenant's answer ever cites the other tenant's document.
    assert citations_a[0]["document_id"] != citations_b[0]["document_id"]


def test_chat_citation_resolution_ignores_a_leaked_foreign_vector_id(
    client, db_session, monkeypatch
):
    """Defense in depth: even if retrieval somehow handed back a vector id
    that belongs to a different tenant (a Pinecone bug, a forged id, a
    stale cache — the mechanism doesn't matter), citation resolution runs
    against the caller's own tenant-scoped Postgres session. That session
    was bound via schema_translate_map to the caller's schema only, so a
    foreign vector id simply doesn't resolve to anything — never to the
    other tenant's document.
    """
    store = _NamespacedFakeVectorStore()
    fake_chat = _FakeChatClient("should never be called")
    _install_fakes(monkeypatch, store, fake_chat)

    _token_a_unused, _tenant_a, _document_a, _chunk_a = _signup_and_ingest(
        client,
        db_session,
        org_name="Tenant A Leak Test",
        email="a@leaktest.example",
        filename="tenant-a-doc.pdf",
        pdf_text="Tenant A content.",
    )
    token_a = client.post(
        "/api/v1/auth/login", json={"email": "a@leaktest.example", "password": "a-strong-password"}
    ).json()["access_token"]

    token_b, tenant_b, document_b, chunk_b = _signup_and_ingest(
        client,
        db_session,
        org_name="Tenant B Leak Test",
        email="b@leaktest.example",
        filename="tenant-b-secret.pdf",
        pdf_text="Tenant B secret payroll figures.",
    )
    foreign_vector_id = chunk_b.pinecone_vector_id

    # Force retrieval to return tenant B's vector id no matter which
    # namespace was actually queried — simulating the leak directly,
    # since a real leak can't be reproduced through the honest fake store.
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(foreign_vector_id, 0.99)],
    )

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"question": "What are the payroll figures?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "tenant-b-secret.pdf" not in body["answer"]
    assert "payroll" not in body["answer"].lower()
    # The leaked id resolved to nothing in tenant A's schema, so there was
    # no context to ground an answer in — the chat model is never even
    # called, let alone given tenant B's content to work with.
    assert fake_chat.calls == []
