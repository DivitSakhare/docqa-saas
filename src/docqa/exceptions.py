class DocQAError(Exception):
    """Base class for application errors that map to a specific HTTP response."""


class EmailAlreadyRegisteredError(DocQAError):
    pass


class InvalidCredentialsError(DocQAError):
    """Covers both unknown email and wrong password — never distinguish the two
    in a response, to avoid leaking which accounts exist."""


class TenantNotActiveError(DocQAError):
    pass


class TenantProvisioningError(DocQAError):
    pass


class InvalidTokenError(DocQAError):
    pass


class UnsupportedFileTypeError(DocQAError):
    pass


class FileTooLargeError(DocQAError):
    pass


class ExternalServiceNotConfiguredError(DocQAError):
    """Raised when the ingestion worker needs NVIDIA NIM or Pinecone but no
    API key is configured. Never reaches an HTTP response — it's caught by
    the ingestion loop and recorded as a job's error_message instead."""


class ChatGenerationError(DocQAError):
    """Raised when the chat endpoint's call to NVIDIA NIM (embedding the
    question, querying Pinecone, or generating the answer) fails or times
    out. Maps to a clean, bounded HTTP error — never a hang, never a raw
    stack trace (see docs/ARCHITECTURE.md, Reliability)."""


class ConversationNotFoundError(DocQAError):
    """Raised for a conversation_id that doesn't exist, or that exists but
    belongs to a different user — the two cases are deliberately
    indistinguishable in the response, same reasoning as
    InvalidCredentialsError not distinguishing unknown-email from
    wrong-password."""


class InvalidRefreshTokenError(DocQAError):
    """Raised for a refresh token that's unknown, expired, or already
    revoked (whether by rotation or logout)."""


class AdminRequiredError(DocQAError):
    """Raised when a non-admin user calls an admin-only endpoint (e.g.
    adding a team member)."""
