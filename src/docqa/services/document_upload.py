import logging
import uuid

from sqlalchemy.orm import Session

from docqa.config import get_settings
from docqa.core.storage import save_document_file, sniff_doc_type
from docqa.exceptions import FileTooLargeError, UnsupportedFileTypeError
from docqa.models.document import Document, DocumentStatus
from docqa.models.ingestion_job import IngestionJob, IngestionJobStatus
from docqa.services.ingestion import process_ingestion_job

logger = logging.getLogger(__name__)


def upload_document(
    tenant_db: Session,
    *,
    tenant_schema_name: str,
    uploaded_by_user_id: uuid.UUID,
    filename: str,
    file_bytes: bytes,
) -> tuple[Document, IngestionJob]:
    """Validates and stores an uploaded PDF or DOCX file, then queues it for ingestion.

    The file is written to disk before any database row is created — an
    orphaned file with no matching row is harmless, but a `documents` row
    pointing at a file that was never actually saved would be a worse
    failure to be in (same reasoning as the Pinecone-before-Postgres
    ordering documented for ingestion writes).

    Raises FileTooLargeError or UnsupportedFileTypeError; validation runs
    before anything is written anywhere.
    """
    max_size = get_settings().max_upload_size_bytes
    if len(file_bytes) > max_size:
        raise FileTooLargeError(f"file exceeds the {max_size}-byte limit")

    doc_type = sniff_doc_type(file_bytes)
    if doc_type is None:
        raise UnsupportedFileTypeError("only PDF and DOCX files are supported")

    # Generated explicitly rather than left to the column's ORM-side
    # default, since the id is needed for the storage path before this row
    # is ever flushed to the database.
    document_id = uuid.uuid4()
    storage_path = save_document_file(
        tenant_schema_name=tenant_schema_name,
        document_id=document_id,
        doc_type=doc_type,
        file_bytes=file_bytes,
    )

    document = Document(
        id=document_id,
        filename=filename,
        doc_type=doc_type,
        uploaded_by_user_id=uploaded_by_user_id,
        status=DocumentStatus.PENDING.value,
        storage_path=storage_path,
    )
    tenant_db.add(document)
    tenant_db.flush()

    ingestion_job = IngestionJob(document_id=document.id, status=IngestionJobStatus.PENDING.value)
    tenant_db.add(ingestion_job)
    tenant_db.commit()
    tenant_db.refresh(document)
    tenant_db.refresh(ingestion_job)

    logger.info(
        "document queued for ingestion",
        extra={"document_id": str(document.id), "job_id": str(ingestion_job.id)},
    )

    # Enqueued after the commit above, not before: the job row must already
    # be durably visible to any worker that might pick this task up —
    # enqueueing first could race a fast worker against our own commit.
    process_ingestion_job.delay(job_id=str(ingestion_job.id), tenant_schema_name=tenant_schema_name)

    return document, ingestion_job
