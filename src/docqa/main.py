import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from docqa.api.v1.router import api_router
from docqa.exceptions import (
    AdminRequiredError,
    ChatGenerationError,
    ConversationNotFoundError,
    EmailAlreadyRegisteredError,
    ExternalServiceNotConfiguredError,
    FileTooLargeError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTokenError,
    TenantNotActiveError,
    TenantProvisioningError,
    UnsupportedFileTypeError,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DocQA SaaS")
app.include_router(api_router)


def _error(status_code: int, detail: str, *, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


@app.exception_handler(EmailAlreadyRegisteredError)
def _email_taken(request: Request, exc: EmailAlreadyRegisteredError) -> JSONResponse:
    return _error(409, "An account with this email already exists.")


@app.exception_handler(InvalidCredentialsError)
def _invalid_credentials(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    return _error(401, "Incorrect email or password.")


@app.exception_handler(TenantNotActiveError)
def _tenant_not_active(request: Request, exc: TenantNotActiveError) -> JSONResponse:
    return _error(403, "This account is not active.")


@app.exception_handler(InvalidTokenError)
def _invalid_token(request: Request, exc: InvalidTokenError) -> JSONResponse:
    return _error(401, "Could not validate credentials.", headers={"WWW-Authenticate": "Bearer"})


@app.exception_handler(TenantProvisioningError)
def _provisioning_failed(request: Request, exc: TenantProvisioningError) -> JSONResponse:
    logging.getLogger(__name__).error("tenant provisioning error: %s", exc)
    return _error(500, "Signup could not be completed. Please try again.")


@app.exception_handler(UnsupportedFileTypeError)
def _unsupported_file_type(request: Request, exc: UnsupportedFileTypeError) -> JSONResponse:
    return _error(415, "Only PDF and DOCX files are supported.")


@app.exception_handler(FileTooLargeError)
def _file_too_large(request: Request, exc: FileTooLargeError) -> JSONResponse:
    return _error(413, "File exceeds the maximum allowed upload size.")


@app.exception_handler(ChatGenerationError)
def _chat_generation_failed(request: Request, exc: ChatGenerationError) -> JSONResponse:
    logging.getLogger(__name__).error("chat generation error: %s", exc)
    return _error(503, "The chat service is temporarily unavailable. Please try again.")


@app.exception_handler(ExternalServiceNotConfiguredError)
def _external_service_not_configured(
    request: Request, exc: ExternalServiceNotConfiguredError
) -> JSONResponse:
    logging.getLogger(__name__).error("external service not configured: %s", exc)
    return _error(503, "The chat service is temporarily unavailable. Please try again.")


@app.exception_handler(ConversationNotFoundError)
def _conversation_not_found(request: Request, exc: ConversationNotFoundError) -> JSONResponse:
    return _error(404, "Conversation not found.")


@app.exception_handler(InvalidRefreshTokenError)
def _invalid_refresh_token(request: Request, exc: InvalidRefreshTokenError) -> JSONResponse:
    return _error(401, "Invalid or expired refresh token.", headers={"WWW-Authenticate": "Bearer"})


@app.exception_handler(AdminRequiredError)
def _admin_required(request: Request, exc: AdminRequiredError) -> JSONResponse:
    return _error(403, "This action requires an admin role.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
