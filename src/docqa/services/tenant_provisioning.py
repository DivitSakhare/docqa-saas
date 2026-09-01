import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from docqa.core.security import hash_password
from docqa.core.slug import schema_name_from_org_name
from docqa.db.tenant_binding import create_tenant_tables
from docqa.exceptions import EmailAlreadyRegisteredError, TenantProvisioningError
from docqa.models.tenant import Tenant, TenantStatus
from docqa.models.user import User, UserRole

logger = logging.getLogger(__name__)


def provision_tenant(
    db: Session, *, org_name: str, admin_email: str, admin_password: str
) -> tuple[Tenant, User]:
    """Create a tenant, its dedicated Postgres schema (with its resource
    tables), and its first admin user.

    Not one atomic transaction: schema/table creation runs over a separate
    connection from this session's transaction, so the process is modeled
    as an explicit, inspectable state machine instead — `tenants.status`
    goes provisioning -> active, or -> failed with the failure visible
    rather than silently rolled back. See docs/ARCHITECTURE.md,
    Reliability, concurrency & trust concerns.

    Raises EmailAlreadyRegisteredError if the email is already taken, or
    TenantProvisioningError if schema/table creation fails.
    """
    normalized_email = admin_email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).first() is not None:
        raise EmailAlreadyRegisteredError(normalized_email)

    schema_name = schema_name_from_org_name(org_name)
    tenant = Tenant(name=org_name, schema_name=schema_name, status=TenantStatus.PROVISIONING.value)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    logger.info("tenant provisioning started", extra={"tenant_id": str(tenant.id)})

    try:
        # schema_name is generated and validated by schema_name_from_org_name,
        # never taken from raw client input, so interpolating it here (the
        # only way to parameterize a DDL identifier) is safe.
        db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        db.commit()
        create_tenant_tables(schema_name)
    except Exception:
        db.rollback()
        tenant.status = TenantStatus.FAILED.value
        db.commit()
        logger.exception("tenant schema creation failed", extra={"tenant_id": str(tenant.id)})
        raise TenantProvisioningError(f"failed to create schema for tenant {tenant.id}") from None

    admin_user = User(
        tenant_id=tenant.id,
        email=normalized_email,
        hashed_password=hash_password(admin_password),
        role=UserRole.ADMIN.value,
    )
    db.add(admin_user)
    try:
        db.commit()
    except IntegrityError:
        # Only reachable via a race with a concurrent signup using the same
        # email, since the pre-check above already rejects the common case.
        # The tenant and its empty schema are left as a visible, harmless
        # `failed` row rather than force-rolled-back.
        db.rollback()
        tenant.status = TenantStatus.FAILED.value
        db.commit()
        raise EmailAlreadyRegisteredError(normalized_email) from None
    db.refresh(admin_user)

    tenant.status = TenantStatus.ACTIVE.value
    db.commit()
    db.refresh(tenant)
    logger.info("tenant provisioning completed", extra={"tenant_id": str(tenant.id)})

    return tenant, admin_user
