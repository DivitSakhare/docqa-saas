import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.tenant_base import TENANT_SCHEMA_TOKEN, TenantBase


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Document(TenantBase):
    """One uploaded file, tracked from upload through ingestion.

    `uploaded_by_user_id` refers to `public.users.id`, but deliberately
    without a database-level foreign key: that table lives under a
    separate SQLAlchemy metadata (TenantBase vs. Base), and the only way to
    make a literal FK resolve across them is to merge the two metadata
    objects — which would also make Alembic's autogenerate try to manage
    these tenant-schema tables under the control-plane migration history.
    The value is only ever written from an authenticated request's own
    verified user id, so the invariant is already guaranteed one layer up.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status in ('pending', 'ready', 'failed')", name="ck_documents_status"),
        {"schema": TENANT_SCHEMA_TOKEN},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentStatus.PENDING.value
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
