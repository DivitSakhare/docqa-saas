from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import docqa.models  # noqa: F401  (registers models on Base.metadata)
from docqa.config import get_settings
from docqa.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    """Restricts autogenerate's schema comparison to `public`.

    Tenant schemas (`tenant_<slug>`) are created dynamically at runtime and
    managed by `create_tenant_tables` against `TenantBase.metadata`, a
    completely separate metadata object from this file's `target_metadata`
    (see db/tenant_base.py). Without this filter, `include_schemas=True`
    makes Alembic reflect every schema in the database, including tenant
    ones — and since none of their tables exist in `Base.metadata`, it
    would propose dropping every tenant's tables on every autogenerate run.
    """
    if type_ == "schema":
        return name in (None, "public")
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="public",
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
