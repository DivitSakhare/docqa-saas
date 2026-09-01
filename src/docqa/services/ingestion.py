import logging
import uuid

import pypdf
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from docqa.celery_app import celery_app
from docqa.config import get_settings
from docqa.core.embeddings import get_embeddings_client
from docqa.core.vector_store import upsert_chunk_vectors
from docqa.db.tenant_binding import tenant_session_scope
from docqa.models.document import Document, DocumentStatus
from docqa.models.document_chunk import DocumentChunk
from docqa.models.ingestion_job import IngestionJob, IngestionJobStatus
from docqa.models.tenant import Tenant, TenantStatus

logger = logging.getLogger(__name__)


def _extract_pdf_pages(storage_path: str) -> list[str]:
    reader = pypdf.PdfReader(storage_path)
    return [page.extract_text() or "" for page in reader.pages]


def _extract_docx_pages(storage_path: str) -> list[str]:
    """DOCX has no reliable page-boundary information in the saved file —
    pagination is a rendering-time concern, not something stored in the
    document's XML — so the whole document is treated as a single page.
    Citations on a DOCX document will always say "page 1"."""
    docx = DocxDocument(storage_path)
    full_text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    return [full_text]


def _sanitize_extracted_text(text: str) -> str:
    """Postgres text columns reject the NUL byte (0x00) outright, so it's
    stripped here, at the point extracted text first enters the system,
    rather than letting it reach Postgres and fail the whole ingestion job.
    Observed in practice from pypdf, which can emit a literal NUL for a
    glyph its font decoding can't resolve (e.g. subscript math notation like
    "wₙ") — the original character is unrecoverable either way, so dropping
    the NUL is the only real option."""
    return text.replace("\x00", "")


def _extract_pages(document: Document) -> list[str]:
    if document.doc_type == "docx":
        pages = _extract_docx_pages(document.storage_path)
    else:
        pages = _extract_pdf_pages(document.storage_path)
    return [_sanitize_extracted_text(page) for page in pages]


def _chunk_pages(pages: list[str]) -> list[dict]:
    """Returns [{"text": ..., "page_number": ...}, ...], preserving which
    page each chunk came from — page_number is 1-indexed to match how a
    human would cite it, not how pypdf indexes internally.
    """
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )

    chunks = []
    for page_index, page_text in enumerate(pages):
        for piece in splitter.split_text(page_text):
            chunks.append({"text": piece, "page_number": page_index + 1})
    return chunks


def _process_job(db: Session, *, tenant_schema_name: str, job: IngestionJob) -> None:
    document = db.get(Document, job.document_id)
    if document is None:
        raise RuntimeError(f"document {job.document_id} not found for job {job.id}")

    # Idempotent under retry: a previous attempt may have partially written
    # chunks before failing. Clear them rather than appending on top.
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

    pages = _extract_pages(document)
    chunks = _chunk_pages(pages)
    if not chunks:
        raise RuntimeError("no extractable text found in document")

    embeddings = get_embeddings_client().embed_documents([c["text"] for c in chunks])

    pinecone_vectors = []
    chunk_rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
        vector_id = f"{document.id}:{index}"
        pinecone_vectors.append(
            (vector_id, vector, {"document_id": str(document.id), "page": chunk["page_number"]})
        )
        chunk_rows.append(
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                page_number=chunk["page_number"],
                chunk_text=chunk["text"],
                pinecone_vector_id=vector_id,
            )
        )

    # Pinecone before Postgres: an orphaned vector on partial failure is
    # harmless, but a document_chunks row pointing at a vector that was
    # never written would be worse. Same ordering as documented for Chroma
    # originally — see docs/ARCHITECTURE.md, Reliability.
    upsert_chunk_vectors(namespace=tenant_schema_name, vectors=pinecone_vectors)

    for row in chunk_rows:
        db.add(row)
    document.status = DocumentStatus.READY.value
    document.page_count = len(pages)
    job.status = IngestionJobStatus.DONE.value
    db.commit()


def _handle_job_failure(db: Session, *, job_id: uuid.UUID, exc: Exception) -> None:
    db.rollback()
    job = db.get(IngestionJob, job_id)
    error_message = str(exc)[:2000]
    max_attempts = get_settings().ingestion_max_attempts

    if job.attempts >= max_attempts:
        job.status = IngestionJobStatus.FAILED.value
        document = db.get(Document, job.document_id)
        if document is not None:
            document.status = DocumentStatus.FAILED.value
    else:
        job.status = IngestionJobStatus.PENDING.value
    job.error_message = error_message
    db.commit()


def reclaim_stuck_jobs(db: Session) -> None:
    """Resets any job left at `processing` back to `pending`, and dispatches
    a fresh task for each one.

    Called once, when a Celery worker process finishes booting (see
    celery_app.py's `worker_ready` handler) — a defensive backstop
    alongside `task_acks_late`/`task_reject_on_worker_lost`
    (docqa.celery_app), which handle the common case of a crashed task
    getting redelivered automatically without any help from this function.
    This covers the rarer case where the broker itself lost track of a
    task rather than cleanly redelivering it.

    The re-dispatch matters, not just the status flip: dispatch is now
    purely event-driven (see services/document_upload.py) — there's no
    polling scan left that would ever notice a job sitting at `pending` on
    its own. Without explicitly enqueuing a fresh task here, resetting the
    status alone would just leave the job pending forever with nothing
    watching it.
    """
    tenants = db.query(Tenant).filter(Tenant.status == TenantStatus.ACTIVE.value).all()
    for tenant in tenants:
        try:
            with tenant_session_scope(tenant.schema_name) as tenant_db:
                stuck_job_ids = [
                    job_id
                    for (job_id,) in tenant_db.query(IngestionJob.id)
                    .filter(IngestionJob.status == IngestionJobStatus.PROCESSING.value)
                    .all()
                ]
                if not stuck_job_ids:
                    continue
                tenant_db.query(IngestionJob).filter(IngestionJob.id.in_(stuck_job_ids)).update(
                    {"status": IngestionJobStatus.PENDING.value}, synchronize_session=False
                )
                tenant_db.commit()
                logger.warning(
                    "reclaimed jobs stuck in processing from a previous run",
                    extra={"tenant_id": str(tenant.id), "count": len(stuck_job_ids)},
                )
            for job_id in stuck_job_ids:
                process_ingestion_job.delay(
                    job_id=str(job_id), tenant_schema_name=tenant.schema_name
                )
        except Exception:
            logger.exception(
                "failed to reclaim stuck jobs for tenant", extra={"tenant_id": str(tenant.id)}
            )


@celery_app.task(
    bind=True,
    max_retries=None,  # unbounded at the Celery level — see below for why
    rate_limit=get_settings().ingestion_rate_limit,
)
def process_ingestion_job(self, *, job_id: str, tenant_schema_name: str) -> None:
    """Celery task wrapping one ingestion attempt for one job. Dispatched
    once per job, right after upload (see services/document_upload.py) —
    not a table scan like the old polling cycle was.

    `max_retries=None` here is deliberate: Postgres (`ingestion_jobs.attempts`)
    stays the single source of truth for how many attempts a job has had,
    same as before this migration. Layering Celery's own separate retry
    counter on top would mean two numbers that could disagree; instead this
    task always defers to `job.attempts` vs `ingestion_max_attempts` to
    decide whether to call `self.retry()` at all.

    Idempotent under redelivery: `task_acks_late` + `task_reject_on_worker_lost`
    (see celery_app.py) mean a worker crashing mid-task gets this exact task
    redelivered to another worker. A job already `done`/`failed` when this
    runs is a no-op — the real outcome was already recorded, and this is
    just a spurious repeat delivery. A job still `pending` or `processing`
    (the latter meaning a previous attempt crashed before finishing) both
    proceed to `_process_job`, which is itself idempotent (clears partial
    chunks before reprocessing), so re-running it is always safe.
    """
    with tenant_session_scope(tenant_schema_name) as tenant_db:
        job = tenant_db.get(IngestionJob, uuid.UUID(job_id))
        if job is None or job.status in (
            IngestionJobStatus.DONE.value,
            IngestionJobStatus.FAILED.value,
        ):
            return

        if job.status == IngestionJobStatus.PENDING.value:
            job.status = IngestionJobStatus.PROCESSING.value
            job.attempts += 1
            tenant_db.commit()
            tenant_db.refresh(job)
        # else: already `processing` — a redelivery of a crashed attempt;
        # attempts was already incremented then, so just retry the work.

        try:
            _process_job(tenant_db, tenant_schema_name=tenant_schema_name, job=job)
            logger.info("ingestion job completed", extra={"job_id": job_id})
        except Exception as exc:
            # job_id (the string param), not job.id: if this except block was
            # reached because the session's own flush/commit failed (e.g. a
            # DB constraint violation), the session needs a rollback before
            # any of `job`'s attributes can be touched again — reading
            # job.id here would try to lazy-reload it on the still-broken
            # session and raise PendingRollbackError, which would replace
            # this exception and skip _handle_job_failure's rollback
            # entirely, leaving the job stuck at `processing` forever with
            # no error recorded and no retry ever scheduled.
            _handle_job_failure(tenant_db, job_id=uuid.UUID(job_id), exc=exc)
            logger.exception("ingestion job attempt failed", extra={"job_id": job_id})
            if job.attempts < get_settings().ingestion_max_attempts:
                self.retry(exc=exc, countdown=min(2**job.attempts, 60))
            # else: attempts exhausted — _handle_job_failure already marked
            # the job (and its document) FAILED; nothing more to do.
