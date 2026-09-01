import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.base import Base


class TenantStatus(enum.StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"


class Tenant(Base):
    """Control-plane record for an organization.

    `schema_name` is the Postgres schema that holds this tenant's business
    data (documents, ingestion_jobs, document_chunks) once provisioned.
    `status` tracks the multi-step provisioning process so a failed or
    in-progress tenant is visible rather than silently half-created.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status in ('provisioning', 'active', 'failed')", name="ck_tenants_status"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TenantStatus.PROVISIONING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
