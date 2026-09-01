import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from docqa.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        # A random jti, not just iat/exp, is what actually guarantees two
        # tokens issued for the same user in the same second (e.g. login
        # immediately followed by a refresh) come out distinct — iat has
        # only whole-second resolution, so without this, identical claims
        # would otherwise produce a byte-identical JWT.
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError (or a subclass) on an invalid/expired token."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_refresh_token() -> str:
    """A high-entropy opaque token — not a JWT. Unlike the access token, it
    carries no claims of its own; it's just a lookup key into
    `refresh_tokens`, which is what makes it revocable (see
    models/refresh_token.py for why that's the point)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256, not argon2 — see models/refresh_token.py for why a
    deterministic hash is required here rather than a salted one."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
