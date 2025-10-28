"""Create audit_logs table for security auditing."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "7c3e1d2a9f4b"
down_revision = "4f8f7b9b7a3d"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    tables = _existing_tables()

    if "audit_logs" in tables:
        return

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_table("audit_logs")

