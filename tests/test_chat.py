import io

from reportlab.pdfgen import canvas

from docqa.models.document import Document
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
    """Same fixed-length fake vector for every input, for both document
    chunks (embed_documents) and questions (embed_query) — cosine similarity
    between any two of these is always 1.0, so tests control relevance via
    the fake Pinecone matches below instead of real vector math."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1024


class _FakeChatClient:
    def __init__(self, response_text: str = "The vacation policy allows 15 days [1]."):
        self.response_text = response_text
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages

        class _Response:
            def __init__(self, content):
                self.content = content

        return _Response(self.response_text)


def _install_ingestion_fakes(monkeypatch, *, upserted: list) -> None:
    monkeypatch.setattr(ingestion_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        ingestion_module,
        "upsert_chunk_vectors",
        lambda *, namespace, vectors: upserted.append((namespace, vectors)),
    )


def _signup_and_ingest_document(
    client, db_session, monkeypatch, *, org_name: str, email: str, pdf_text: str
):
    upserted: list = []
    _install_ingestion_fakes(monkeypatch, upserted=upserted)

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
        files={"file": ("policy.pdf", _make_pdf_bytes(pdf_text), "application/pdf")},
    )
    assert upload.status_code == 202
    # Celery runs in eager mode for tests — the upload call above already
    # ran ingestion to completion synchronously (see conftest.py).

    tenant = db_session.query(Tenant).filter(Tenant.name == org_name).one()
    return token, tenant


def test_chat_answers_a_grounded_question_with_citations(client, db_session, monkeypatch):
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Vacation Co",
        email="admin@vacationco.example",
        pdf_text="Employees get 15 days of paid vacation per year.",
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        vector_id = f"{document.id}:0"

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.95)],
    )
    fake_chat = _FakeChatClient("Employees get 15 days of paid vacation per year [1].")
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days do employees get?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "15 days" in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["filename"] == "policy.pdf"
    assert body["citations"][0]["page_number"] == 1
    assert body["citations"][0]["document_id"] == str(document.id)


def test_chat_system_prompt_instructs_partial_grounding_for_compound_questions(
    client, db_session, monkeypatch
):
    """Regression test for a real hallucination: a compound question
    ("who wrote this document, and give me code for a linked list") was
    answered in full, including runnable linked-list code fabricated from
    the model's own general knowledge — none of the retrieved chunks
    mentioned linked lists at all. The system prompt now explicitly
    instructs the model to evaluate each part of a multi-part question
    independently and refuse the parts the sources don't cover, rather than
    filling gaps from outside knowledge because part of the question was
    genuinely answerable. This can't verify the live model's actual
    compliance (the chat client is mocked, same as every other test here),
    but it does verify the instruction is actually wired into what gets
    sent to the model rather than silently lost."""
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Compound Co",
        email="admin@compoundco.example",
        pdf_text="Employees get 15 days of paid vacation per year.",
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        vector_id = f"{document.id}:0"

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.95)],
    )
    fake_chat = _FakeChatClient("Employees get 15 days of paid vacation per year [1].")
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": (
                "How many vacation days do employees get, and give me the code for a linked list?"
            )
        },
    )

    assert response.status_code == 200
    assert fake_chat.last_messages is not None
    system_prompt = fake_chat.last_messages[0].content
    assert "never use outside knowledge" in system_prompt
    assert "multiple parts" in system_prompt
    assert "do not fill that gap from your own knowledge" in system_prompt


def test_chat_answers_a_low_scoring_but_genuinely_relevant_follow_up(
    client, db_session, monkeypatch
):
    """Regression test for a real false negative: a genuinely-answerable
    follow-up question can score well below a keyword-overlapping direct
    question against the same chunk (0.197 vs 0.465 observed live for a
    "when do I need a receipt?" follow-up — see docs/ARCHITECTURE.md,
    Reliability section). This score sits between the old threshold (0.3,
    too strict) and the current one (0.2) — it must be treated as
    relevant, not dropped.
    """
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Expense Co",
        email="admin@expenseco.example",
        pdf_text=(
            "Employees may expense up to $75 per day for meals. Receipts "
            "are required for any expense over $25."
        ),
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        vector_id = f"{document.id}:0"

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.25)],
    )
    fake_chat = _FakeChatClient("Receipts are required for expenses over $25 [1].")
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "And when do I need a receipt?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "$25" in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["document_id"] == str(document.id)
    assert fake_chat.last_messages is not None


def test_chat_does_not_fabricate_citations_for_an_unrelated_question(
    client, db_session, monkeypatch
):
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Unrelated Co",
        email="admin@unrelatedco.example",
        pdf_text="Employees get 15 days of paid vacation per year.",
    )

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    # Below the relevance threshold: simulates Pinecone finding nothing
    # genuinely relevant to an off-topic question.
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [("some-vector-id", 0.05)],
    )
    fake_chat = _FakeChatClient()
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the capital of France?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "don't have enough information" in body["answer"]
    # The LLM is never called once retrieval finds nothing relevant enough.
    assert fake_chat.last_messages is None


def test_chat_only_retrieves_from_the_caller_tenants_own_namespace(client, db_session, monkeypatch):
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Namespace Co",
        email="admin@namespaceco.example",
        pdf_text="Employees get 15 days of paid vacation per year.",
    )

    seen_namespaces: list[str] = []

    def _fake_query(*, namespace, vector, top_k):
        seen_namespaces.append(namespace)
        return []

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(chat_module, "query_chunk_vectors", _fake_query)

    client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days?"},
    )

    assert seen_namespaces == [tenant.schema_name]


def test_chat_returns_a_clean_error_when_the_chat_model_call_fails(client, db_session, monkeypatch):
    token, tenant = _signup_and_ingest_document(
        client,
        db_session,
        monkeypatch,
        org_name="Flaky Chat Co",
        email="admin@flakychatco.example",
        pdf_text="Employees get 15 days of paid vacation per year.",
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        vector_id = f"{document.id}:0"

    def _broken_chat_client():
        raise TimeoutError("simulated NVIDIA NIM timeout")

    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.95)],
    )
    monkeypatch.setattr(chat_module, "get_chat_client", _broken_chat_client)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days do employees get?"},
    )

    assert response.status_code == 503
    assert "detail" in response.json()


def test_chat_requires_authentication(client):
    response = client.post("/api/v1/chat", json={"question": "anything"})
    assert response.status_code == 401
