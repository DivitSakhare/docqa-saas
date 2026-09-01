import io
import uuid
import zipfile
from pathlib import Path

from docqa.config import get_settings

PDF_MAGIC_BYTES = b"%PDF-"
DOCX_ZIP_MAGIC_BYTES = b"PK\x03\x04"


def sniff_doc_type(file_bytes: bytes) -> str | None:
    """Sniffs the actual file content rather than trusting the client's
    declared filename or Content-Type header, both of which are untrusted
    input the client fully controls.

    Returns "pdf", "docx", or None if the content doesn't match either.
    The DOCX check goes one level deeper than the generic ZIP signature
    (`PK\\x03\\x04` alone also matches `.xlsx`/`.pptx`/a plain `.zip` — all
    OOXML formats share it): it opens the file as a zip and confirms
    `word/document.xml` is actually present.
    """
    if file_bytes.startswith(PDF_MAGIC_BYTES):
        return "pdf"
    if file_bytes.startswith(DOCX_ZIP_MAGIC_BYTES):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    return None


def save_document_file(
    *, tenant_schema_name: str, document_id: uuid.UUID, doc_type: str, file_bytes: bytes
) -> str:
    """Writes an uploaded document to local disk and returns its storage path.

    The path is built entirely from server-generated values (schema name,
    document id, sniffed doc type) — never from the client-supplied
    filename — so there's no path-traversal surface here at all; the
    original filename is kept only as display metadata on the `documents`
    row.
    """
    tenant_dir = Path(get_settings().storage_root) / tenant_schema_name
    tenant_dir.mkdir(parents=True, exist_ok=True)

    file_path = tenant_dir / f"{document_id}.{doc_type}"
    file_path.write_bytes(file_bytes)
    return str(file_path)
