from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from docqa.core.deps import CurrentUser, RequireAdmin
from docqa.db.session import get_db
from docqa.schemas.team import TeamMemberCreate, TeamMemberResponse
from docqa.services.team import create_team_member, list_team_members

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/members", response_model=list[TeamMemberResponse])
def list_members(
    current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[TeamMemberResponse]:
    """Lists every user in the caller's own tenant. Any authenticated
    member can view their teammates; only an admin can add one (see
    POST below)."""
    members = list_team_members(db, tenant_id=current_user.tenant_id)
    return [
        TeamMemberResponse(
            user_id=member.id,
            email=member.email,
            role=member.role,
            created_at=member.created_at,
        )
        for member in members
    ]


@router.post("/members", response_model=TeamMemberResponse, status_code=201)
def add_member(
    body: TeamMemberCreate,
    current_user: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> TeamMemberResponse:
    """Adds a new user to the caller's own tenant. Admin-only — there's no
    email-invite flow, so the admin sets the new member's email/password
    directly and shares it out of band."""
    member = create_team_member(
        db,
        tenant_id=current_user.tenant_id,
        email=body.email,
        password=body.password,
        role=body.role,
    )
    return TeamMemberResponse(
        user_id=member.id,
        email=member.email,
        role=member.role,
        created_at=member.created_at,
    )
