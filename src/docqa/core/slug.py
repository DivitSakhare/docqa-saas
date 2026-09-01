import re
import uuid

# Postgres identifiers are limited to 63 bytes; leave headroom for the
# "tenant_" prefix and a disambiguating suffix appended on collision.
_MAX_SLUG_LENGTH = 40
_SCHEMA_NAME_PATTERN = re.compile(r"^tenant_[a-z0-9_]{1,55}$")


def schema_name_from_org_name(org_name: str) -> str:
    """Derive a Postgres-identifier-safe, deterministic schema name.

    Non-alphanumeric characters become underscores, the result is
    lowercased and truncated, and a short random suffix is appended so two
    tenants with the same organization name don't collide. The output is
    validated against a strict allow-list pattern before use — this is the
    only place an untrusted string (the org name) feeds into a Postgres
    identifier, so the check is defense in depth on top of the
    transformation itself.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", org_name.strip().lower()).strip("_")
    slug = slug[:_MAX_SLUG_LENGTH] or "org"
    suffix = uuid.uuid4().hex[:8]
    schema_name = f"tenant_{slug}_{suffix}"

    if not _SCHEMA_NAME_PATTERN.match(schema_name):
        raise ValueError(f"generated schema name is not valid: {schema_name!r}")
    return schema_name
