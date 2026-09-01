import io
import zipfile
from pathlib import Path

import pytest
from docx import Document as DocxDocument

from docqa.exceptions import FileTooLargeError, UnsupportedFileTypeError
from docqa.services import document_upload as document_upload_module
from docqa.services.document_upload import upload_document

FAKE_PDF_BYTES = b"%PDF-1.4\nfake pdf content for tests\n%%EOF"


def _make_docx_bytes(text_content: str) -> bytes:
    docx = DocxDocument()
    docx.add_paragraph(text_content)
    buffer = io.BytesIO()
    docx.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_op_ingestion_dispatch(monkeypatch):
    """These tests are about the upload flow itself (validation, storage,
    the returned/listed rows) — not ingestion outcomes, which is
    test_ingestion.py's job and uses genuinely valid PDFs. FAKE_PDF_BYTES
    above isn't real PDF content, so letting the real task run (Celery is
    in eager mode for tests — see conftest.py) would make every upload
    here actually attempt, fail, and retry ingestion for no reason this
    file cares about. No-op the dispatch instead, same as it was
    structurally impossible for these tests to trigger ingestion before
    dispatch became upload-triggered.
    """
    monkeypatch.setattr(
        document_upload_module.process_ingestion_job, "delay", lambda **kwargs: None
    )


def _signup_and_login(client, *, org_name: str, email: str) -> tuple[str, dict]:
    signup = client.post(
        "/api/v1/auth/signup",
        json={"org_name": org_name, "admin_email": email, "admin_password": "a-strong-password"},
    )
    assert signup.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "a-strong-password"},
    )
    assert login.status_code == 200
    return login.json()["access_token"], signup.json()


def test_upload_creates_document_and_ingestion_job(client):
    token, _ = _signup_and_login(client, org_name="Upload Co", email="admin@upload.example")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report.pdf", FAKE_PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["status"] == "pending"
    assert body["document_id"]
    assert body["job_id"]


def test_uploaded_file_is_actually_written_to_disk(client):
    token, _ = _signup_and_login(client, org_name="Disk Co", email="admin@disk.example")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report.pdf", FAKE_PDF_BYTES, "application/pdf")},
    )

    document_id = response.json()["document_id"]
    matches = list(
        Path(document_upload_module.get_settings().storage_root).rglob(f"{document_id}.pdf")
    )
    assert len(matches) == 1
    assert matches[0].read_bytes() == FAKE_PDF_BYTES


def test_upload_appears_in_list_documents(client):
    token, _ = _signup_and_login(client, org_name="List Co", email="admin@list.example")

    client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("report.pdf", FAKE_PDF_BYTES, "application/pdf")},
    )

    response = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["filename"] == "report.pdf"
    assert response.json()[0]["status"] == "pending"


def test_upload_accepts_a_real_docx_file(client):
    token, _ = _signup_and_login(client, org_name="Docx Co", email="admin@docx.example")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "report.docx",
                _make_docx_bytes("Hello docx world"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["filename"] == "report.docx"

    matches = list(
        Path(document_upload_module.get_settings().storage_root).rglob(
            f"{body['document_id']}.docx"
        )
    )
    assert len(matches) == 1


def test_upload_rejects_docx_disguised_by_extension_alone(client):
    """A .docx filename whose content isn't actually a Word document (e.g.
    missing word/document.xml) must still be rejected — same "disguised
    extension" rigor as the PDF case below. A plain zip has the OOXML
    magic bytes but not the actual Word document part."""
    token, _ = _signup_and_login(
        client, org_name="Docx Disguise Co", email="admin@docxdisguise.example"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("not_a_word_doc.txt", "just some zip content")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "fake.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 415


def test_upload_rejects_non_pdf_content(client):
    token, _ = _signup_and_login(client, org_name="Reject Co", email="admin@reject.example")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"just plain text, not a pdf", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_rejects_pdf_disguised_by_extension_alone(client):
    """A .pdf filename with non-PDF bytes must still be rejected — the
    check is on the actual file content, not the client-supplied name."""
    token, _ = _signup_and_login(client, org_name="Disguise Co", email="admin@disguise.example")

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
    )

    assert response.status_code == 415


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("report.pdf", FAKE_PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 401


def test_other_tenant_cannot_see_an_uploaded_document(client):
    token_a, _ = _signup_and_login(client, org_name="Isolation A", email="a@isolation.example")
    token_b, _ = _signup_and_login(client, org_name="Isolation B", email="b@isolation.example")

    client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret.pdf", FAKE_PDF_BYTES, "application/pdf")},
    )

    response_b = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert response_b.json() == []


def test_upload_document_rejects_file_over_the_configured_size_limit(db_session, monkeypatch):
    class _TinyLimitSettings:
        max_upload_size_bytes = 10

    monkeypatch.setattr(document_upload_module, "get_settings", lambda: _TinyLimitSettings())

    with pytest.raises(FileTooLargeError):
        upload_document(
            db_session,
            tenant_schema_name="tenant_does_not_matter",
            uploaded_by_user_id="00000000-0000-0000-0000-000000000000",
            filename="big.pdf",
            file_bytes=FAKE_PDF_BYTES,
        )


def test_upload_document_rejects_non_pdf_bytes_at_the_service_level():
    with pytest.raises(UnsupportedFileTypeError):
        upload_document(
            None,
            tenant_schema_name="tenant_does_not_matter",
            uploaded_by_user_id="00000000-0000-0000-0000-000000000000",
            filename="notes.txt",
            file_bytes=b"not a pdf",
        )
