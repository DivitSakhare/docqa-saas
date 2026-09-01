import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from docqa.config import get_settings
from docqa.core.security import generate_refresh_token, hash_refresh_token
from docqa.exceptions import InvalidRefreshTokenError, TenantNotActiveError
from docqa.models.refresh_token import RefreshToken
from docqa.models.tenant import Tenant, TenantStatus
from docqa.models.user import User


def issue_refresh_token(db: Session, *, user_id: uuid.UUID) -> str:
    """Called once at login, alongside the access token. Returns the raw
    token — the only time it's ever available in plaintext; only its hash
    is persisted (see models/refresh_token.py)."""
    settings = get_settings()
    raw_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return raw_token


def _find_by_raw_token(db: Session, *, raw_token: str) -> RefreshToken | None:
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .first()
    )


def rotate_refresh_token(db: Session, *, raw_token: str) -> tuple[User, Tenant, str]:
    """Validates and single-use-consumes a refresh token: the presented
    token is revoked and a new one takes its place, chained via
    `replaced_by_id`. Returns (user, tenant, new_raw_token).

    Reuse detection: presenting a token that was already exchanged for a
    newer one (`replaced_by_id` is set) is refused *and* treated as a
    signal the original token leaked, so every other active token for
    that user is revoked too, forcing every session to log back in — a
    legitimate client never presents the same refresh token twice; only a
    thief replaying a stolen one, or a client racing itself, would.

    A token revoked by explicit logout instead (`replaced_by_id` is still
    None) is refused the same way but *without* the cascading revocation —
    trying to refresh a session the caller already logged out of is
    expected client behavior, not a theft signal, and shouldn't nuke a
    user's other, unrelated sessions.
    """
    record = _find_by_raw_token(db, raw_token=raw_token)
    if record is None:
        raise InvalidRefreshTokenError()

    now = datetime.now(UTC)
    if record.revoked_at is not None:
        if record.replaced_by_id is not None:
            revoke_all_refresh_tokens_for_user(db, user_id=record.user_id)
        raise InvalidRefreshTokenError()
    if record.expires_at < now:
        raise InvalidRefreshTokenError()

    user = db.get(User, record.user_id)
    tenant = db.get(Tenant, user.tenant_id) if user is not None else None
    if user is None or tenant is None:
        raise InvalidRefreshTokenError()
    if tenant.status != TenantStatus.ACTIVE.value:
        raise TenantNotActiveError()

    settings = get_settings()
    new_raw_token = generate_refresh_token()
    new_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw_token),
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_record)
    db.flush()

    record.revoked_at = now
    record.replaced_by_id = new_record.id
    db.commit()

    return user, tenant, new_raw_token


def revoke_refresh_token(db: Session, *, raw_token: str) -> None:
    """Logout: revoke exactly the presented token. Silently a no-op for an
    unknown/already-revoked token — a logout call should look the same to
    the caller whether or not the session was still alive."""
    record = _find_by_raw_token(db, raw_token=raw_token)
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        db.commit()


def revoke_all_refresh_tokens_for_user(db: Session, *, user_id: uuid.UUID) -> None:
    """Forced logout: revoke every currently active refresh token for this
    user, e.g. 'log out of all devices' or a suspected-compromise
    response. Access tokens already issued keep working until they expire
    on their own (see docs/ARCHITECTURE.md — session management doesn't
    include instant access-token invalidation, only refresh)."""
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(UTC)})
    db.commit()
