from datetime import UTC, datetime, timedelta

from docqa.core.security import hash_refresh_token
from docqa.models.refresh_token import RefreshToken


def _signup_and_login(client, *, email: str = "admin@sessionco.example"):
    client.post(
        "/api/v1/auth/signup",
        json={
            "org_name": "Session Co",
            "admin_email": email,
            "admin_password": "a-strong-password",
        },
    )
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()


def test_login_returns_an_access_token_and_a_refresh_token(client):
    body = _signup_and_login(client)
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_refresh_issues_a_new_access_token_and_rotates_the_refresh_token(client):
    tokens = _signup_and_login(client)

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The new access token actually works.
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert me.status_code == 200


def test_a_rotated_away_refresh_token_cannot_be_reused(client):
    tokens = _signup_and_login(client)
    client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401


def test_reusing_a_rotated_away_token_revokes_every_other_active_session(client):
    """Reuse of an already-rotated refresh token is treated as a signal the
    original token leaked: it forces every session for that user to log
    back in, not just the reused one — see services/session.py."""
    tokens = _signup_and_login(client)
    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()

    # Replaying the original (now-revoked) token triggers reuse detection.
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401

    # The legitimately-rotated token, issued just before the reuse attempt,
    # is now revoked too — not just the one that was replayed.
    now_also_dead = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert now_also_dead.status_code == 401


def test_an_unknown_refresh_token_is_rejected(client):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


def test_an_expired_refresh_token_is_rejected(client, db_session):
    tokens = _signup_and_login(client)
    db_session.query(RefreshToken).filter(
        RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"])
    ).update({"expires_at": datetime.now(UTC) - timedelta(days=1)})
    db_session.commit()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_logout_revokes_only_the_presented_session(client):
    """Two independent logins ('two devices'): logging out one must not
    affect the other."""
    tokens_device_a = _signup_and_login(client)
    tokens_device_b = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sessionco.example", "password": "a-strong-password"},
    ).json()

    logout = client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens_device_a["refresh_token"]}
    )
    assert logout.status_code == 204

    refresh_a = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens_device_a["refresh_token"]}
    )
    assert refresh_a.status_code == 401

    refresh_b = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens_device_b["refresh_token"]}
    )
    assert refresh_b.status_code == 200


def test_logout_is_idempotent_for_an_already_invalid_token(client):
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "garbage-token"})
    assert response.status_code == 204


def test_logout_all_revokes_every_session_for_the_user(client):
    tokens_device_a = _signup_and_login(client)
    tokens_device_b = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sessionco.example", "password": "a-strong-password"},
    ).json()

    response = client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {tokens_device_a['access_token']}"},
    )
    assert response.status_code == 204

    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens_device_a["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens_device_b["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_all_requires_authentication(client):
    response = client.post("/api/v1/auth/logout-all")
    assert response.status_code == 401
