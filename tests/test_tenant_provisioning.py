import pytest
from sqlalchemy import text

from docqa.core.security import verify_password
from docqa.db.session import engine
from docqa.exceptions import EmailAlreadyRegisteredError
from docqa.models.tenant import Tenant, TenantStatus
from docqa.services.tenant_provisioning import provision_tenant


def test_provision_tenant_hashes_the_password(db_session):
    _, user = provision_tenant(
        db_session,
        org_name="Beta LLC",
        admin_email="owner@beta.example",
        admin_password="a-strong-password",
    )
    assert user.hashed_password != "a-strong-password"
    assert verify_password("a-strong-password", user.hashed_password)


def test_provision_tenant_generates_a_scoped_schema_name_and_activates(db_session):
    tenant, _ = provision_tenant(
        db_session,
        org_name="Gamma Inc.",
        admin_email="owner@gamma.example",
        admin_password="a-strong-password",
    )
    assert tenant.schema_name.startswith("tenant_gamma_inc")
    assert tenant.status == TenantStatus.ACTIVE.value


def test_provision_tenant_rejects_duplicate_email_without_leaving_a_dangling_tenant(db_session):
    provision_tenant(
        db_session,
        org_name="Delta Co",
        admin_email="dup@delta.example",
        admin_password="a-strong-password",
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        provision_tenant(
            db_session,
            org_name="Delta Co Two",
            admin_email="dup@delta.example",
            admin_password="another-strong-password",
        )

    assert db_session.query(Tenant).filter(Tenant.name == "Delta Co Two").first() is None


def test_provision_tenant_creates_the_resource_tables_in_the_new_schema(db_session):
    tenant, _ = provision_tenant(
        db_session,
        org_name="Epsilon Corp",
        admin_email="owner@epsilon.example",
        admin_password="a-strong-password",
    )

    with engine.connect() as connection:
        table_names = set(
            connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"
                ),
                {"schema": tenant.schema_name},
            )
            .scalars()
            .all()
        )

    assert table_names == {
        "documents",
        "ingestion_jobs",
        "document_chunks",
        "conversations",
        "messages",
    }
