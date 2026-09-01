from sqlalchemy.orm import DeclarativeBase

# The schema name given to every table declared against this base is never
# a real Postgres schema — it's a placeholder rewritten per-request via
# SQLAlchemy's schema_translate_map (see tenant_binding.py). Because
# TenantBase is a distinct DeclarativeBase from the control-plane Base, its
# tables live in a separate MetaData and are invisible to Alembic's
# autogenerate against Base.metadata — tenant tables are never accidentally
# folded into the public-schema migration history.
TENANT_SCHEMA_TOKEN = "tenant"


class TenantBase(DeclarativeBase):
    """Declarative base for tables that live inside each tenant's own
    Postgres schema, rather than `public`. Not Alembic-managed: tables are
    created directly against a tenant's schema via
    `tenant_binding.create_tenant_tables`, using this base's metadata.
    """
