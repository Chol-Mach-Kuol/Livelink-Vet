"""v0.2: triage, offline sync, USSD channel, GPS, audit log and notification outbox.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("disease_reports") as batch:
        batch.add_column(sa.Column("client_ref", sa.String(64), nullable=True))
        batch.add_column(sa.Column("species", sa.String(30), nullable=True, server_default="cattle"))
        batch.add_column(sa.Column("signs", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
        batch.add_column(sa.Column("channel", sa.String(20), nullable=True, server_default="app"))
        batch.add_column(sa.Column("triage", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("suggested_priority", sa.String(20), nullable=True, server_default="normal"))
        batch.add_column(sa.Column("zoonotic_alert", sa.Boolean(), nullable=True, server_default=sa.false()))
    op.create_index("ix_disease_reports_client_ref", "disease_reports", ["client_ref"], unique=True)
    op.create_index("ix_disease_reports_created_at", "disease_reports", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_index("ix_audit_logs_created_at", "audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_disease_reports_created_at", "disease_reports")
    op.drop_index("ix_disease_reports_client_ref", "disease_reports")
    with op.batch_alter_table("disease_reports") as batch:
        for col in ("zoonotic_alert", "suggested_priority", "triage", "channel", "longitude",
                    "latitude", "signs", "species", "client_ref"):
            batch.drop_column(col)
