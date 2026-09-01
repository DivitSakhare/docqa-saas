from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection
from sqlalchemy.orm import Session

from docqa.db.session import engine
from docqa.db.tenant_base import TENANT_SCHEMA_TOKEN, TenantBase


def _tenant_connection(schema_name: str) -> Connection:
    """A connection whose queries against TENANT_SCHEMA_TOKEN-declared
    tables are transparently rewritten to run against `schema_name`.

    This is the single mechanism behind tenant isolation at the query
    level: nothing about which schema gets used is decided by application
    code branching on a tenant id — it's baked into how SQL gets compiled
    for this specific connection.
    """
    return engine.connect().execution_options(
        schema_translate_map={TENANT_SCHEMA_TOKEN: schema_name}
    )


def create_tenant_tables(schema_name: str) -> None:
    """Create documents/ingestion_jobs/document_chunks inside schema_name.

    Not Alembic-managed. If a tenant table's shape needs to change later,
    that requires a small migration script looping over existing tenant
    schemas — there's no per-tenant migration history yet, only "create
    what TenantBase.metadata currently declares" at provisioning time.
    """
    connection = _tenant_connection(schema_name)
    try:
        TenantBase.metadata.create_all(bind=connection)
        connection.commit()
    finally:
        connection.close()


def tenant_session(schema_name: str) -> Iterator[Session]:
    """Generator-style session scoped to one tenant's schema, for use as a
    FastAPI dependency (see core.deps.get_tenant_db).
    """
    connection = _tenant_connection(schema_name)
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        connection.close()


@contextmanager
def tenant_session_scope(schema_name: str) -> Iterator[Session]:
    """Context-manager form of tenant_session, for callers outside a
    FastAPI request — tests, scripts, and (later) the ingestion worker.
    """
    yield from tenant_session(schema_name)
