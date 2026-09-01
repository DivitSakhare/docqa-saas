import uuid
from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from docqa.core.security import decode_access_token
from docqa.db.session import get_db
from docqa.db.tenant_binding import tenant_session
from docqa.exceptions import AdminRequiredError, InvalidTokenError, TenantNotActiveError
from docqa.models.tenant import Tenant, TenantStatus
from docqa.models.user import User, UserRole

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from a bearer JWT.

    `tenant_id` in the token's claims is not used here — this dependency
    only proves *who* is calling. Binding a request to the caller's tenant
    schema is a separate mechanism introduced alongside the per-tenant
    resource tables it protects.
    """
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise InvalidTokenError("invalid or expired token") from None

    user = db.get(User, user_id)
    if user is None:
        raise InvalidTokenError("token no longer valid")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_tenant(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Tenant:
    """Resolve and validate the caller's tenant.

    Re-checks the tenant is active on every call instead of trusting the
    JWT's snapshot from login time, since a tenant could be deactivated in
    between. FastAPI caches this per request, so endpoints that need both
    `CurrentTenant` and `TenantDB` don't pay for this lookup twice.
    """
    tenant = db.get(Tenant, current_user.tenant_id)
    if tenant is None or tenant.status != TenantStatus.ACTIVE.value:
        raise TenantNotActiveError()
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


def require_admin(current_user: CurrentUser) -> User:
    """Gate for admin-only endpoints (e.g. adding a team member). Layers on
    top of CurrentUser rather than replacing it, so admin-only routes still
    get the same identity resolution as everywhere else.
    """
    if current_user.role != UserRole.ADMIN.value:
        raise AdminRequiredError()
    return current_user


RequireAdmin = Annotated[User, Depends(require_admin)]


def get_tenant_db(tenant: CurrentTenant) -> Iterator[Session]:
    """Session scoped to the caller's own tenant schema — the mechanism
    that makes isolation load-bearing at the query level rather than
    something application code has to remember to apply consistently.
    """
    yield from tenant_session(tenant.schema_name)


TenantDB = Annotated[Session, Depends(get_tenant_db)]
