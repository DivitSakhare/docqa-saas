import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docqa.core.security import hash_password
from docqa.exceptions import EmailAlreadyRegisteredError
from docqa.models.user import User, UserRole


def create_team_member(
    db: Session, *, tenant_id: uuid.UUID, email: str, password: str, role: UserRole
) -> User:
    """Adds a second (or later) user to an already-provisioned tenant.

    Mirrors the user-creation half of tenant_provisioning.provision_tenant,
    minus the tenant/schema setup — that already happened at signup. Raises
    EmailAlreadyRegisteredError on the same global-unique-email constraint
    signup itself relies on (checked up front, and again on commit to catch
    a concurrent signup/add-member race using the same email).
    """
    normalized_email = email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).first() is not None:
        raise EmailAlreadyRegisteredError(normalized_email)

    member = User(
        tenant_id=tenant_id,
        email=normalized_email,
        hashed_password=hash_password(password),
        role=role.value,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegisteredError(normalized_email) from None
    db.refresh(member)
    return member


def list_team_members(db: Session, *, tenant_id: uuid.UUID) -> list[User]:
    return db.query(User).filter(User.tenant_id == tenant_id).order_by(User.created_at.asc()).all()
