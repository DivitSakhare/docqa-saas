import io

from docx import Document as DocxDocument
from reportlab.pdfgen import canvas
from sqlalchemy import text

from docqa.models.document import Document, DocumentStatus
from docqa.models.document_chunk import DocumentChunk
from docqa.models.ingestion_job import IngestionJob, IngestionJobStatus
from docqa.models.tenant import Tenant
from docqa.services import ingestion as ingestion_module
from docqa.services.ingestion import process_ingestion_job, reclaim_stuck_jobs

# Celery runs in eager mode for tests (task_always_eager, propagates=False —
# see conftest.py and celery_app.py): calling .delay() runs the task
# synchronously in-process, including looping through every retry attempt
# immediately, with no real broker involved. So uploading a document here
# also fully ingests it (or exhausts its retries) by the time the upload
# call returns — there's no separate "run a cycle" step to invoke anymore.


def _make_pdf_bytes(text_content: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 700, text_content)
    pdf.save()
    return buffer.getvalue()


def _make_docx_bytes(text_content: str) -> bytes:
    buffer = io.BytesIO()
    docx = DocxDocument()
    docx.add_paragraph(text_content)
    docx.save(buffer)
    return buffer.getvalue()


class _FakeEmbeddingsClient:
    """Returns a fixed-length fake vector per input text, so tests never
    touch the real NVIDIA API."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


def _install_fakes(monkeypatch, *, upserted: list) -> None:
    monkeypatch.setattr(ingestion_module, "get_embeddings_client", lambda: _FakeEmbeddingsClient())
    monkeypatch.setattr(
        ingestion_module,
        "upsert_chunk_vectors",
        lambda *, namespace, vectors: upserted.append((namespace, vectors)),
    )


def _signup_and_upload(client, db_session, *, org_name: str, email: str, pdf_bytes: bytes):
    """Fakes must already be installed before calling this — the upload
    call itself triggers ingestion synchronously under eager mode."""
    signup = client.post(
        "/api/v1/auth/signup",
        json={"org_name": org_name, "admin_email": email, "admin_password": "a-strong-password"},
    )
    assert signup.status_code == 201
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a-strong-password"}
    ).json()["access_token"]

    upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 202

    tenant = db_session.query(Tenant).filter(Tenant.name == org_name).one()
    return token, upload.json(), tenant


def test_uploading_a_document_ingests_it(client, db_session, monkeypatch):
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    token, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Ingestion Co",
        email="admin@ingestion.example",
        pdf_bytes=_make_pdf_bytes("Hello ingestion world"),
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        chunks = (
            tenant_db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
        )

        assert document.status == DocumentStatus.READY.value
        assert document.page_count == 1
        assert job.status == IngestionJobStatus.DONE.value
        assert len(chunks) == 1
        assert chunks[0].page_number == 1
        assert "Hello ingestion world" in chunks[0].chunk_text
        assert chunks[0].pinecone_vector_id == f"{document.id}:0"

    assert len(upserted) == 1
    namespace, vectors = upserted[0]
    assert namespace == tenant.schema_name
    assert len(vectors) == 1

    response = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.json()[0]["status"] == "ready"
    assert response.json()[0]["page_count"] == 1


def test_uploading_a_docx_document_ingests_it(client, db_session, monkeypatch):
    """DOCX has no page-boundary information in the saved file, so the
    whole document is treated as a single page — see
    services/ingestion.py::_extract_docx_pages."""
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "org_name": "Docx Ingestion Co",
            "admin_email": "admin@docxingestion.example",
            "admin_password": "a-strong-password",
        },
    )
    assert signup.status_code == 201
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@docxingestion.example", "password": "a-strong-password"},
    ).json()["access_token"]

    upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "report.docx",
                _make_docx_bytes("Hello docx ingestion world"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload.status_code == 202
    upload_body = upload.json()

    tenant = db_session.query(Tenant).filter(Tenant.name == "Docx Ingestion Co").one()
    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        chunks = (
            tenant_db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
        )

        assert document.status == DocumentStatus.READY.value
        assert document.doc_type == "docx"
        assert document.page_count == 1
        assert job.status == IngestionJobStatus.DONE.value
        assert len(chunks) == 1
        assert chunks[0].page_number == 1
        assert "Hello docx ingestion world" in chunks[0].chunk_text


def test_extracted_text_containing_a_nul_byte_does_not_break_ingestion(
    client, db_session, monkeypatch
):
    """Regression test: pypdf can emit a literal NUL (0x00) byte for a
    glyph its font decoding can't resolve (observed on a real PDF using
    subscript math notation, e.g. "wₙ") — Postgres text columns reject NUL
    bytes outright, which used to fail the final commit in _process_job.
    The NUL is now stripped at extraction time (_sanitize_extracted_text),
    so ingestion succeeds instead of failing on a byte no one asked to
    store."""
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)
    monkeypatch.setattr(
        ingestion_module, "_extract_pdf_pages", lambda storage_path: ["Hello \x00 nul world"]
    )

    token, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Nul Byte Co",
        email="admin@nulbyte.example",
        pdf_bytes=_make_pdf_bytes("irrelevant, extraction is mocked"),
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        chunks = (
            tenant_db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
        )

        assert document.status == DocumentStatus.READY.value
        assert job.status == IngestionJobStatus.DONE.value
        assert len(chunks) == 1
        assert "\x00" not in chunks[0].chunk_text
        assert "Hello" in chunks[0].chunk_text
        assert "nul world" in chunks[0].chunk_text


def test_a_flush_failure_during_ingestion_still_marks_the_job_failed_cleanly(
    client, db_session, monkeypatch
):
    """Regression test: if _process_job's own final commit fails for any
    reason (a real case: the NUL-byte PDF above, before it was fixed), the
    job must still land in `failed` (after retries) with a real
    error_message — not get stuck at `processing` forever with nothing
    watching it. That's what used to happen: building
    _handle_job_failure's arguments read job.id, which tried to lazy-reload
    the now-expired attribute on the session that had just failed to
    flush — raising PendingRollbackError instead of ever reaching
    _handle_job_failure's own rollback, so the job/document were never
    marked failed and no retry was ever scheduled."""
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    def _process_job_that_fails_its_own_commit(db, *, tenant_schema_name, job):
        document = db.get(Document, job.document_id)
        document.status = "not-a-real-status"  # violates ck_documents_status
        db.commit()

    monkeypatch.setattr(ingestion_module, "_process_job", _process_job_that_fails_its_own_commit)

    token, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Flush Fail Co",
        email="admin@flushfail.example",
        pdf_bytes=_make_pdf_bytes("irrelevant, _process_job is replaced"),
    )

    settings = ingestion_module.get_settings()
    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])

        assert job.status == IngestionJobStatus.FAILED.value
        assert job.attempts == settings.ingestion_max_attempts
        assert job.error_message is not None
        assert document.status == DocumentStatus.FAILED.value


def test_ingestion_only_touches_the_uploading_tenants_own_namespace(
    client, db_session, monkeypatch
):
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    _signup_and_upload(
        client,
        db_session,
        org_name="Tenant A Ingest",
        email="a@tenantingest.example",
        pdf_bytes=_make_pdf_bytes("Tenant A content"),
    )
    _signup_and_upload(
        client,
        db_session,
        org_name="Tenant B Ingest",
        email="b@tenantingest.example",
        pdf_bytes=_make_pdf_bytes("Tenant B content"),
    )

    namespaces = {namespace for namespace, _ in upserted}
    assert len(namespaces) == 2


def test_ingestion_retries_then_fails_after_max_attempts(client, db_session, monkeypatch):
    def _broken_embeddings_client():
        raise RuntimeError("simulated NVIDIA NIM outage")

    monkeypatch.setattr(ingestion_module, "get_embeddings_client", _broken_embeddings_client)

    token, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Flaky Co",
        email="admin@flaky.example",
        pdf_bytes=_make_pdf_bytes("Some content"),
    )

    settings = ingestion_module.get_settings()
    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        assert job.status == IngestionJobStatus.FAILED.value
        assert job.attempts == settings.ingestion_max_attempts
        assert "simulated NVIDIA NIM outage" in job.error_message
        assert document.status == DocumentStatus.FAILED.value


def test_ingestion_is_idempotent_when_a_crashed_jobs_task_is_redelivered(
    client, db_session, monkeypatch
):
    """Simulates the real crash-recovery path: a worker dies after chunks
    were partially written but before the job was marked done, and its task
    gets redelivered (what task_acks_late/task_reject_on_worker_lost
    produce for real — see celery_app.py). Must not duplicate chunks."""
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    token, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Crash Co",
        email="admin@crash.example",
        pdf_bytes=_make_pdf_bytes("Content that gets chunked"),
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        tenant_db.add(
            DocumentChunk(
                document_id=upload_body["document_id"],
                chunk_index=0,
                page_number=1,
                chunk_text="a leftover chunk from a crashed attempt",
                pinecone_vector_id="stale-vector-id",
            )
        )
        # Left at `processing`, not reset to `pending` — this is what a
        # redelivery (rather than a fresh dispatch) actually looks like.
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        job.status = IngestionJobStatus.PROCESSING.value
        tenant_db.commit()

    process_ingestion_job.delay(job_id=upload_body["job_id"], tenant_schema_name=tenant.schema_name)

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        chunks = (
            tenant_db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == upload_body["document_id"])
            .all()
        )
        assert len(chunks) == 1
        assert chunks[0].pinecone_vector_id != "stale-vector-id"


def test_redelivering_an_already_completed_jobs_task_is_a_safe_noop(
    client, db_session, monkeypatch
):
    """A task can be redelivered after it already succeeded (e.g. an ack
    lost in transit even though the DB commit went through) — this must
    not reprocess or duplicate anything, and must not touch Pinecone again.
    """
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    _, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Redelivery Co",
        email="admin@redelivery.example",
        pdf_bytes=_make_pdf_bytes("Some content"),
    )
    assert len(upserted) == 1  # the real upload already ingested it once

    process_ingestion_job.delay(job_id=upload_body["job_id"], tenant_schema_name=tenant.schema_name)

    assert len(upserted) == 1  # no second Pinecone write happened
    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        chunks = (
            tenant_db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == upload_body["document_id"])
            .all()
        )
        assert len(chunks) == 1


def test_reclaim_stuck_jobs_recovers_and_reprocesses_a_job_left_processing_after_a_crash(
    client, db_session, monkeypatch
):
    """Regression test: if a worker dies mid-job and its task is never
    redelivered to anyone (the rarer case reclaim_stuck_jobs exists for —
    see its docstring), that job is left at `processing` with nothing
    watching it, since dispatch is purely event-driven now. reclaim_stuck_jobs
    (run once at Celery worker startup) is what recovers *and re-dispatches*
    it — a status flip alone wouldn't be enough."""
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    _, upload_body, tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Crashed Worker Co",
        email="admin@crashedworker.example",
        pdf_bytes=_make_pdf_bytes("Content from before the crash"),
    )

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        job.status = IngestionJobStatus.PROCESSING.value
        tenant_db.commit()

    reclaim_stuck_jobs(db_session)

    with ingestion_module.tenant_session_scope(tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, upload_body["document_id"])
        job = tenant_db.get(IngestionJob, upload_body["job_id"])
        assert job.status == IngestionJobStatus.DONE.value
        assert document.status == DocumentStatus.READY.value


def test_a_broken_tenant_schema_does_not_block_the_upload_response_or_other_tenants(
    client, db_session, monkeypatch
):
    """Regression test: if a tenant's schema is broken in a way that makes
    ingestion itself fail (e.g. missing tables from before they existed),
    that failure must be contained to that tenant's own job. It must not
    crash the upload request itself — task_eager_propagates=False (see
    celery_app.py) mirrors real .delay() fire-and-forget semantics even in
    eager mode — and must not affect any other, independent tenant.
    """
    upserted: list = []
    _install_fakes(monkeypatch, upserted=upserted)

    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "org_name": "Broken Schema Co",
            "admin_email": "admin@broken.example",
            "admin_password": "a-strong-password",
        },
    )
    assert signup.status_code == 201
    broken_tenant = db_session.query(Tenant).filter(Tenant.name == "Broken Schema Co").one()
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@broken.example", "password": "a-strong-password"},
    ).json()["access_token"]

    with ingestion_module.tenant_session_scope(broken_tenant.schema_name) as tenant_db:
        tenant_db.execute(text(f'DROP TABLE "{broken_tenant.schema_name}".document_chunks CASCADE'))
        tenant_db.commit()

    upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "report.pdf",
                _make_pdf_bytes("Doesn't matter, the chunks table is gone"),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 202  # the upload response itself is unaffected

    with ingestion_module.tenant_session_scope(broken_tenant.schema_name) as tenant_db:
        job = tenant_db.get(IngestionJob, upload.json()["job_id"])
        assert job.status == IngestionJobStatus.FAILED.value

    _, healthy_upload_body, healthy_tenant = _signup_and_upload(
        client,
        db_session,
        org_name="Healthy Schema Co",
        email="admin@healthy.example",
        pdf_bytes=_make_pdf_bytes("This one should still get processed"),
    )

    with ingestion_module.tenant_session_scope(healthy_tenant.schema_name) as tenant_db:
        document = tenant_db.get(Document, healthy_upload_body["document_id"])
        assert document.status == DocumentStatus.READY.value
