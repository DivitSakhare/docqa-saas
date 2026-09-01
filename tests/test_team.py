from docqa.models.tenant import Tenant
from docqa.models.user import User


def _signup_payload(**overrides):
    payload = {
        "org_name": "Acme Corp",
        "admin_email": "admin@acme.example",
        "admin_password": "correct-horse-battery-staple",
    }
    payload.update(overrides)
    return payload


def _login(client, email, password):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _signup_and_login(client, **overrides):
    client.post("/api/v1/auth/signup", json=_signup_payload(**overrides))
    return _login(
        client,
        overrides.get("admin_email", "admin@acme.example"),
        overrides.get("admin_password", "correct-horse-battery-staple"),
    )


def test_admin_can_add_team_member(client, db_session):
    headers = _signup_and_login(client)
    response = client.post(
        "/api/v1/team/members",
        headers=headers,
        json={"email": "member@acme.example", "password": "another-strong-pass", "role": "member"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "member@acme.example"
    assert body["role"] == "member"

    tenant = db_session.query(Tenant).filter(Tenant.name == "Acme Corp").one()
    member = db_session.query(User).filter(User.email == "member@acme.example").one()
    assert member.tenant_id == tenant.id
    assert member.hashed_password != "another-strong-pass"


def test_added_member_can_log_in(client):
    headers = _signup_and_login(client)
    client.post(
        "/api/v1/team/members",
        headers=headers,
        json={"email": "member@acme.example", "password": "another-strong-pass", "role": "member"},
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "member@acme.example", "password": "another-strong-pass"},
    )
    assert response.status_code == 200


def test_member_cannot_add_team_member(client):
    admin_headers = _signup_and_login(client)
    client.post(
        "/api/v1/team/members",
        headers=admin_headers,
        json={"email": "member@acme.example", "password": "another-strong-pass", "role": "member"},
    )
    member_headers = _login(client, "member@acme.example", "another-strong-pass")

    response = client.post(
        "/api/v1/team/members",
        headers=member_headers,
        json={"email": "second@acme.example", "password": "yet-another-pass", "role": "member"},
    )
    assert response.status_code == 403


def test_add_team_member_rejects_duplicate_email(client):
    headers = _signup_and_login(client)
    response = client.post(
        "/api/v1/team/members",
        headers=headers,
        json={"email": "admin@acme.example", "password": "another-strong-pass", "role": "member"},
    )
    assert response.status_code == 409


def test_list_team_members_is_tenant_scoped(client):
    acme_headers = _signup_and_login(client)
    client.post(
        "/api/v1/team/members",
        headers=acme_headers,
        json={"email": "member@acme.example", "password": "another-strong-pass", "role": "member"},
    )
    other_headers = _signup_and_login(
        client, org_name="Other Org", admin_email="admin@other.example"
    )

    acme_emails = {
        m["email"] for m in client.get("/api/v1/team/members", headers=acme_headers).json()
    }
    other_emails = {
        m["email"] for m in client.get("/api/v1/team/members", headers=other_headers).json()
    }

    assert acme_emails == {"admin@acme.example", "member@acme.example"}
    assert other_emails == {"admin@other.example"}
