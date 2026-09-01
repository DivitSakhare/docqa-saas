from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from docqa.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Request-scoped session for control-plane (`public` schema) data.

    Endpoints that need to operate inside a tenant's own schema get a
    separate, schema-bound dependency introduced alongside the per-tenant
    resource tables.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
