import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.base import Base


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class User(Base):
    """Control-plane identity record.

    Lives in `public`, not the tenant's own schema: login only has an email
    address to start from, so tenant context can't be resolved until after
    this table is queried. See docs/ARCHITECTURE.md, Key Decisions.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('admin', 'member')", name="ck_users_role"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.tenants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.MEMBER.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
