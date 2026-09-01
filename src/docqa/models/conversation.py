import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.tenant_base import TENANT_SCHEMA_TOKEN, TenantBase


class Conversation(TenantBase):
    """One chat thread. `user_id` refers to `public.users.id`, deliberately
    without a database-level foreign key — same reasoning as
    `Document.uploaded_by_user_id`: it's a separate SQLAlchemy metadata, and
    the value is only ever written from an authenticated request's own
    verified user id.

    Conversations are private to the user who started them, not shared
    tenant-wide like documents — see services/conversation.py, which is
    where that ownership check actually lives.
    """

    __tablename__ = "conversations"
    __table_args__ = ({"schema": TENANT_SCHEMA_TOKEN},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
