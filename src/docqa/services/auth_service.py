from sqlalchemy.orm import Session

from docqa.core.security import hash_password, verify_password
from docqa.exceptions import InvalidCredentialsError, TenantNotActiveError
from docqa.models.tenant import Tenant, TenantStatus
from docqa.models.user import User

# Hashed once at import time and compared against on every "user not found"
# path, so a login attempt for a nonexistent email takes roughly as long as
# one for a real email with a wrong password — otherwise response timing
# would let an attacker enumerate registered addresses.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-for-timing-only")


def authenticate_user(db: Session, *, email: str, password: str) -> tuple[User, Tenant]:
    """Resolve a user by email, verify their password, and confirm their
    tenant is active. Raises InvalidCredentialsError or TenantNotActiveError.

    InvalidCredentialsError is raised identically for "no such email" and
    "wrong password" — the caller must not distinguish them in the response.
    """
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    hashed_password = user.hashed_password if user else _DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, hashed_password)

    if user is None or not password_matches:
        raise InvalidCredentialsError()

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None or tenant.status != TenantStatus.ACTIVE.value:
        raise TenantNotActiveError()

    return user, tenant
