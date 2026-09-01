from sqlalchemy import text

from docqa.models.tenant import Tenant, TenantStatus
from docqa.models.user import User


def _signup_payload(**overrides):
    payload = {
        "org_name": "Acme Corp",
        "admin_email": "admin@acme.example",
        "admin_password": "correct-horse-battery-staple",
    }
    payload.update(overrides)
    return payload


def test_signup_creates_active_tenant_and_admin_user(client, db_session):
    response = client.post("/api/v1/auth/signup", json=_signup_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "admin"
    assert body["email"] == "admin@acme.example"

    tenant = db_session.get(Tenant, body["tenant_id"])
    assert tenant.status == TenantStatus.ACTIVE.value

    user = db_session.get(User, body["user_id"])
    assert user.hashed_password != "correct-horse-battery-staple"


def test_signup_provisions_a_real_postgres_schema(client, db_session):
    response = client.post("/api/v1/auth/signup", json=_signup_payload())
    tenant = db_session.get(Tenant, response.json()["tenant_id"])

    schema_exists = db_session.execute(
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
        {"name": tenant.schema_name},
    ).first()
    assert schema_exists is not None


def test_signup_rejects_duplicate_email(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    response = client.post("/api/v1/auth/signup", json=_signup_payload(org_name="Other Org"))
    assert response.status_code == 409


def test_signup_rejects_short_password(client):
    response = client.post("/api/v1/auth/signup", json=_signup_payload(admin_password="short"))
    assert response.status_code == 422


def test_login_returns_valid_token(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.example", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.example", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.example", "password": "whatever12345"},
    )
    assert response.status_code == 401


def test_login_error_does_not_distinguish_unknown_email_from_wrong_password(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.example", "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.example", "password": "whatever12345"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_rejects_inactive_tenant(client, db_session):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    db_session.query(Tenant).update({"status": TenantStatus.FAILED.value})
    db_session.flush()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.example", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 403


def test_me_returns_current_user_for_valid_token(client):
    client.post("/api/v1/auth/signup", json=_signup_payload())
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.example", "password": "correct-horse-battery-staple"},
    ).json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@acme.example"
    assert body["role"] == "admin"


def test_me_rejects_missing_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
