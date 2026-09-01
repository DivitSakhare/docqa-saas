import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.base import Base


class RefreshToken(Base):
    """Control-plane record backing session management: refresh-token
    rotation and forced logout. Lives in `public`, alongside `users` — a
    session concept, not tenant business data.

    The raw token is never stored — only `token_hash` (SHA-256 hex digest),
    so a database read can't be turned directly into a usable session the
    way a leaked password hash at least requires cracking first. SHA-256
    (not argon2, unlike passwords) is deliberate here: the token itself is
    already a high-entropy random secret rather than something guessable,
    so the property that matters is a fast, deterministic lookup by hash —
    argon2's per-hash random salt would make that lookup impossible without
    scanning every row.

    Rotation: each successful `/auth/refresh` call revokes the presented
    token and issues a new one, chaining `replaced_by_id` to it. Presenting
    an already-rotated token again is refused and, per standard
    refresh-token-reuse handling, revokes every other active token for
    that user too — a rotated token being reused is a signal the original
    token leaked, not that the client just made a duplicate call.

    A token revoked by explicit logout instead (`replaced_by_id` left
    None) is refused the same way but without that cascading revocation —
    see services/session.py.rotate_refresh_token for why the two cases
    are kept distinct despite both just setting `revoked_at`.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.refresh_tokens.id"), nullable=True
    )
