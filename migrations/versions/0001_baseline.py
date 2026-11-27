"""Baseline: the original v0.1 schema.

Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "locations", _id(),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("county", sa.String(100)),
        sa.Column("payam", sa.String(100)),
        sa.Column("boma", sa.String(100)),
        sa.Column("cattle_camp", sa.String(150)),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        _created(),
    )
    op.create_table(
        "organizations", _id(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("organization_type", sa.String(50)),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id")),
        sa.Column("contact_email", sa.String(150)),
        _created(),
    )
    op.create_table(
        "users", _id(),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(150), unique=True),
        sa.Column("password_hash", sa.String()),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("phone_verified", sa.Boolean()),
        _created(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "role_assignments", _id(),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id")),
        sa.Column("verified", sa.Boolean()),
        _created(),
    )
    op.create_table(
        "disease_reports", _id(),
        sa.Column("reporter_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("death_count", sa.Integer()),
        sa.Column("first_observed_at", sa.DateTime(timezone=True)),
        sa.Column("description", sa.Text()),
        sa.Column("report_status", sa.String(30)),
        _created(),
    )
    op.create_table(
        "cases", _id(),
        sa.Column("case_number", sa.String(40), nullable=False, unique=True),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("assigned_vet_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("case_status", sa.String(30)),
        sa.Column("priority", sa.String(20)),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "case_reports",
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id"), primary_key=True),
        sa.Column("report_id", UUID(as_uuid=True), sa.ForeignKey("disease_reports.id"), primary_key=True, unique=True),
    )
    op.create_table(
        "case_assignments", _id(),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignment_role", sa.String(30), nullable=False),
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "diagnoses", _id(),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("veterinarian_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("disease_name", sa.String(150)),
        sa.Column("diagnosis_status", sa.String(30), nullable=False),
        sa.Column("diagnostic_method", sa.String(50)),
        sa.Column("clinical_notes", sa.Text()),
        sa.Column("diagnosed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )
    op.create_table(
        "lab_results", _id(),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("laboratory_name", sa.String(150)),
        sa.Column("test_name", sa.String(150)),
        sa.Column("sample_type", sa.String(100)),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("result_date", sa.DateTime(timezone=True)),
        sa.Column("verified_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        _created(),
    )


def downgrade() -> None:
    for table in ("lab_results", "diagnoses", "case_assignments", "case_reports", "cases",
                  "disease_reports", "role_assignments", "users", "organizations", "locations"):
        op.drop_table(table)
