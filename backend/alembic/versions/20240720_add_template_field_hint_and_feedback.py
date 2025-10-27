"""Add template field hint and correction feedback tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "4f8f7b9b7a3d"
down_revision = "32f8eac34adf"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    columns = _existing_columns("template_fields")

    if "auto_learned_type" not in columns:
        op.add_column(
            "template_fields",
            sa.Column("auto_learned_type", sa.String(length=50), nullable=True),
        )

    if "learning_enabled" not in columns:
        op.add_column(
            "template_fields",
            sa.Column(
                "learning_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )

    if "last_learned_at" not in columns:
        op.add_column(
            "template_fields",
            sa.Column("last_learned_at", sa.DateTime(), nullable=True),
        )

    tables = _existing_tables()

    if "template_field_hints" not in tables:
        op.create_table(
            "template_field_hints",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("template_field_id", sa.Integer(), nullable=False),
            sa.Column("hint_type", sa.String(length=100), nullable=False),
            sa.Column("hint_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(
                ["template_field_id"], ["template_fields.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "template_field_id",
                "hint_type",
                name="uq_template_field_hints_field_type",
            ),
        )
        op.create_index(
            "ix_template_field_hints_template_field_id",
            "template_field_hints",
            ["template_field_id"],
        )

    if "correction_feedback" not in tables:
        op.create_table(
            "correction_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("template_field_id", sa.Integer(), nullable=True),
            sa.Column("original_value", sa.Text(), nullable=True),
            sa.Column("corrected_value", sa.Text(), nullable=False),
            sa.Column("feedback_context", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("applied_by", sa.Integer(), nullable=True),
            sa.Column(
                "applied",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.ForeignKeyConstraint(
                ["document_id"], ["documents.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["template_field_id"], ["template_fields.id"], ondelete="SET NULL"
            ),
            sa.UniqueConstraint(
                "document_id",
                "template_field_id",
                "corrected_value",
                name="uq_correction_feedback_document_field_value",
            ),
        )
        op.create_index(
            "ix_correction_feedback_document_id",
            "correction_feedback",
            ["document_id"],
        )
        op.create_index(
            "ix_correction_feedback_template_field_id",
            "correction_feedback",
            ["template_field_id"],
        )
def downgrade() -> None:
    op.drop_index(
        "ix_correction_feedback_template_field_id",
        table_name="correction_feedback",
    )
    op.drop_index(
        "ix_correction_feedback_document_id",
        table_name="correction_feedback",
    )
    op.drop_table("correction_feedback")

    op.drop_index(
        "ix_template_field_hints_template_field_id",
        table_name="template_field_hints",
    )
    op.drop_table("template_field_hints")

    op.drop_column("template_fields", "last_learned_at")
    op.drop_column("template_fields", "learning_enabled")
    op.drop_column("template_fields", "auto_learned_type")
