from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from docqa.core.deps import CurrentUser
from docqa.core.security import create_access_token
from docqa.db.session import get_db
from docqa.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from docqa.services.auth_service import authenticate_user
from docqa.services.session import (
    issue_refresh_token,
    revoke_all_refresh_tokens_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from docqa.services.tenant_provisioning import provision_tenant

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(body: SignupRequest, db: Annotated[Session, Depends(get_db)]) -> SignupResponse:
    tenant, admin_user = provision_tenant(
        db,
        org_name=body.org_name,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
    )
    return SignupResponse(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user, tenant = authenticate_user(db, email=body.email, password=body.password)
    access_token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    refresh_token = issue_refresh_token(db, user_id=user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    """Exchanges a refresh token for a new access token. The refresh token
    itself is single-use: this call also rotates it, so the body's
    `refresh_token` must be swapped in on the client for the next refresh
    (see services/session.rotate_refresh_token for why reusing an old one
    is treated as a security event, not a harmless retry)."""
    user, tenant, new_refresh_token = rotate_refresh_token(db, raw_token=body.refresh_token)
    access_token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=204)
def logout(body: LogoutRequest, db: Annotated[Session, Depends(get_db)]) -> None:
    """Ends one session by revoking its refresh token. Doesn't require a
    still-valid access token — the access token this session was using may
    already be expired, which is exactly when a client is likeliest to
    want to log out rather than refresh."""
    revoke_refresh_token(db, raw_token=body.refresh_token)


@router.post("/logout-all", status_code=204)
def logout_all(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> None:
    """Forced logout: revokes every refresh token belonging to the caller,
    ending every other session's ability to get a new access token. Any
    access token already issued elsewhere keeps working until it expires
    on its own — see docs/ARCHITECTURE.md, Not Now."""
    revoke_all_refresh_tokens_for_user(db, user_id=current_user.id)


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        role=current_user.role,
    )
