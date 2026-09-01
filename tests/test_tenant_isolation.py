import uuid

from docqa.db.tenant_binding import tenant_session_scope
from docqa.models.document import Document
from docqa.models.tenant import Tenant


def _signup_and_login(client, *, org_name: str, email: str) -> tuple[str, dict]:
    signup = client.post(
        "/api/v1/auth/signup",
        json={"org_name": org_name, "admin_email": email, "admin_password": "a-strong-password"},
    )
    assert signup.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "a-strong-password"},
    )
    assert login.status_code == 200
    return login.json()["access_token"], signup.json()


def test_tenant_cannot_see_another_tenants_documents(client, db_session):
    token_a, _ = _signup_and_login(client, org_name="Acme A", email="a@acme.example")
    token_b, tenant_b = _signup_and_login(client, org_name="Acme B", email="b@acme.example")

    schema_b = db_session.get(Tenant, tenant_b["tenant_id"]).schema_name

    # Seed a document directly into tenant B's schema — no upload endpoint
    # exists yet (phase 3), so this stands in for "B has real data".
    with tenant_session_scope(schema_b) as tenant_b_db:
        tenant_b_db.add(
            Document(
                filename="secret.pdf",
                doc_type="pdf",
                uploaded_by_user_id=uuid.UUID(tenant_b["user_id"]),
            )
        )
        tenant_b_db.commit()

    response_a = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_a}"})
    assert response_a.status_code == 200
    assert response_a.json() == []

    response_b = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert response_b.status_code == 200
    assert len(response_b.json()) == 1
    assert response_b.json()[0]["filename"] == "secret.pdf"
