import os
import tempfile
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://docqa:docqa@localhost:5432/docqa_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-do-not-use-in-production")
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="docqa_test_storage_"))
# `.delay()` runs the task synchronously in-process, with no real broker
# contact — see docqa/celery_app.py. Tests never need a running Redis.
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import docqa.models  # noqa: F401  (registers models on Base.metadata / TenantBase.metadata)
from docqa.config import get_settings
from docqa.db.base import Base
from docqa.db.session import engine, get_db
from docqa.main import app

_MAINTENANCE_DB_URL = "postgresql://docqa:docqa@localhost:5432/docqa"

_TestSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _ensure_test_database_exists(db_name: str) -> None:
    with psycopg.connect(_MAINTENANCE_DB_URL, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')


@pytest.fixture(scope="session", autouse=True)
def _control_plane_schema() -> Iterator[None]:
    """Ensures docqa_test exists and has the control-plane tables.

    Tenant schemas are created and torn down per-test (see db_session's
    teardown below) rather than here, since tenant provisioning genuinely
    commits real schemas/tables across more than one connection — there's
    no single outer transaction to roll them back with.
    """
    settings = get_settings()
    db_name = settings.database_url.rsplit("/", 1)[-1]
    _ensure_test_database_exists(db_name)

    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A real session against the test database — application code's own
    commits are real commits, matching production, since provisioning
    deliberately spans more than one connection (see
    tenant_provisioning.provision_tenant) and can't be wrapped in a single
    rollback-at-teardown transaction.

    Cleanup happens explicitly after each test instead: drop any
    `tenant_*` schemas a test created, and clear the control-plane tables.
    """
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as cleanup_connection:
            schema_names = (
                cleanup_connection.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name LIKE 'tenant\\_%' ESCAPE '\\'"
                    )
                )
                .scalars()
                .all()
            )
            for schema_name in schema_names:
                cleanup_connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
            cleanup_connection.execute(text("TRUNCATE TABLE public.users, public.tenants CASCADE"))
            cleanup_connection.commit()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
