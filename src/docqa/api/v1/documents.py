from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from docqa.core.deps import CurrentTenant, CurrentUser, TenantDB
from docqa.models.document import Document
from docqa.schemas.document import DocumentResponse, DocumentUploadResponse
from docqa.services.document_upload import upload_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentResponse])
def list_documents(tenant_db: TenantDB) -> list[Document]:
    """List documents in the caller's own tenant schema."""
    return tenant_db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.post("", response_model=DocumentUploadResponse, status_code=202)
async def upload(
    tenant_db: TenantDB,
    current_user: CurrentUser,
    tenant: CurrentTenant,
    file: Annotated[UploadFile, File()],
) -> DocumentUploadResponse:
    """Upload a PDF. Returns immediately with a document/job id — actually
    parsing, chunking, and embedding the file happens later, in the
    ingestion worker (not built yet).
    """
    file_bytes = await file.read()

    document, ingestion_job = upload_document(
        tenant_db,
        tenant_schema_name=tenant.schema_name,
        uploaded_by_user_id=current_user.id,
        filename=file.filename or "document.pdf",
        file_bytes=file_bytes,
    )

    return DocumentUploadResponse(
        document_id=document.id,
        job_id=ingestion_job.id,
        filename=document.filename,
        status=document.status,
    )
