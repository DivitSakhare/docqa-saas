import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from docqa.db.tenant_base import TENANT_SCHEMA_TOKEN, TenantBase


class DocumentChunk(TenantBase):
    """The citation bridge table: lets a chat answer point back to a real
    document + page without round-tripping to Pinecone. See
    docs/ARCHITECTURE.md, Data model.
    """

    __tablename__ = "document_chunks"
    __table_args__ = ({"schema": TENANT_SCHEMA_TOKEN},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{TENANT_SCHEMA_TOKEN}.documents.id"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    pinecone_vector_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
