import io

from reportlab.pdfgen import canvas

from docqa.models.document import Document
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
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)

        class _Response:
            def __init__(self, content):
                self.content = content

        return _Response(self._responses.pop(0) if self._responses else "stub answer")


def _install_fakes(monkeypatch, *, vector_id: str, chat_client: _FakeChatClient) -> None:
    monkeypatch.setattr(ingestion_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        ingestion_module, "upsert_chunk_vectors", lambda *, namespace, vectors: None
    )
    monkeypatch.setattr(chat_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.95)],
    )
    monkeypatch.setattr(chat_module, "get_chat_client", lambda: chat_client)


def _tenant_schema(db_session, tenant_id: str) -> str:
    from docqa.models.tenant import Tenant

    return db_session.get(Tenant, tenant_id).schema_name


def _setup_conversation_fixture(client, db_session, monkeypatch, *, chat_client: _FakeChatClient):
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "org_name": "Conversation Co",
            "admin_email": "admin@conversation.example",
            "admin_password": "a-strong-password",
        },
    )
    assert signup.status_code == 201
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@conversation.example", "password": "a-strong-password"},
    ).json()["access_token"]

    schema_name = _tenant_schema(db_session, signup.json()["tenant_id"])
    _install_fakes(monkeypatch, vector_id="placeholder", chat_client=chat_client)

    upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "policy.pdf",
                _make_pdf_bytes("Employees get 15 days of paid vacation per year."),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 202
    # Celery runs in eager mode for tests — the upload call above already
    # ran ingestion to completion synchronously (see conftest.py).

    with ingestion_module.tenant_session_scope(schema_name) as tenant_db:
        document = tenant_db.query(Document).one()
        vector_id = f"{document.id}:0"

    monkeypatch.setattr(
        chat_module,
        "query_chunk_vectors",
        lambda *, namespace, vector, top_k: [(vector_id, 0.95)],
    )

    return token, str(document.id), signup.json()["tenant_id"]


def test_chat_without_conversation_id_starts_a_new_conversation(client, db_session, monkeypatch):
    chat_client = _FakeChatClient(["You get 15 days of vacation [1]."])
    token, _document_id, _tenant_id = _setup_conversation_fixture(
        client, db_session, monkeypatch, chat_client=chat_client
    )

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days do I get?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]

    listing = client.get("/api/v1/conversations", headers={"Authorization": f"Bearer {token}"})
    assert listing.status_code == 200
    conversations = listing.json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == body["conversation_id"]
    assert conversations[0]["message_count"] == 2  # one user turn + one assistant turn


def test_follow_up_question_continues_the_same_conversation_and_sees_history(
    client, db_session, monkeypatch
):
    chat_client = _FakeChatClient(
        ["You get 15 days of vacation [1].", "Unused days roll over, up to 5 [1]."]
    )
    token, _document_id, _tenant_id = _setup_conversation_fixture(
        client, db_session, monkeypatch, chat_client=chat_client
    )

    first = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "How many vacation days do I get?"},
    )
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Do unused ones roll over?", "conversation_id": conversation_id},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    # The second call's prompt to the model included the first turn's
    # question and answer as history — this is what "conversation history"
    # actually means, not just that it got persisted afterward.
    second_call_messages = chat_client.calls[1]
    joined = " ".join(getattr(m, "content", "") for m in second_call_messages)
    assert "How many vacation days do I get?" in joined
    assert "You get 15 days of vacation" in joined

    detail = client.get(
        f"/api/v1/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "How many vacation days do I get?"
    assert messages[3]["content"] == "Unused days roll over, up to 5 [1]."
    assert messages[1]["citations"][0]["filename"] == "policy.pdf"


def test_unknown_conversation_id_returns_404(client, db_session, monkeypatch):
    chat_client = _FakeChatClient(["stub"])
    token, _document_id, _tenant_id = _setup_conversation_fixture(
        client, db_session, monkeypatch, chat_client=chat_client
    )

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "anything", "conversation_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_a_user_cannot_read_another_users_conversation_in_the_same_tenant(
    client, db_session, monkeypatch
):
    from docqa.core.security import hash_password
    from docqa.models.user import User, UserRole

    chat_client = _FakeChatClient(["stub answer"])
    token_admin, _document_id, tenant_id = _setup_conversation_fixture(
        client, db_session, monkeypatch, chat_client=chat_client
    )

    started = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"question": "How many vacation days?"},
    )
    conversation_id = started.json()["conversation_id"]

    # A second user in the SAME tenant (same schema) — not a second tenant.
    # /auth/signup always provisions a brand-new tenant, so the second user
    # is added directly, the way an invite flow would (not built yet).
    db_session.add(
        User(
            tenant_id=tenant_id,
            email="member@conversation.example",
            hashed_password=hash_password("a-strong-password"),
            role=UserRole.MEMBER.value,
        )
    )
    db_session.commit()
    token_member = client.post(
        "/api/v1/auth/login",
        json={"email": "member@conversation.example", "password": "a-strong-password"},
    ).json()["access_token"]

    response = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert response.status_code == 404

    listing = client.get(
        "/api/v1/conversations", headers={"Authorization": f"Bearer {token_member}"}
    )
    assert listing.json() == []
