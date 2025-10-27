"""Add template field hint and correction feedback tables."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f8f7b9b7a3d"
down_revision = "32f8eac34adf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "template_fields",
        sa.Column("auto_learned_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "template_fields",
        sa.Column(
            "learning_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "template_fields",
        sa.Column("last_learned_at", sa.DateTime(), nullable=True),
    )

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
    )
    op.create_index(
        "ix_template_field_hints_template_field_id",
        "template_field_hints",
        ["template_field_id"],
    )
    op.create_unique_constraint(
        "uq_template_field_hints_field_type",
        "template_field_hints",
        ["template_field_id", "hint_type"],
    )

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
    op.create_unique_constraint(
        "uq_correction_feedback_document_field_value",
        "correction_feedback",
        ["document_id", "template_field_id", "corrected_value"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_correction_feedback_document_field_value",
        "correction_feedback",
        type_="unique",
    )
    op.drop_index(
        "ix_correction_feedback_template_field_id",
        table_name="correction_feedback",
    )
    op.drop_index(
        "ix_correction_feedback_document_id",
        table_name="correction_feedback",
    )
    op.drop_table("correction_feedback")

    op.drop_constraint(
        "uq_template_field_hints_field_type",
        "template_field_hints",
        type_="unique",
    )
    op.drop_index(
        "ix_template_field_hints_template_field_id",
        table_name="template_field_hints",
    )
    op.drop_table("template_field_hints")

    op.drop_column("template_fields", "last_learned_at")
    op.drop_column("template_fields", "learning_enabled")
    op.drop_column("template_fields", "auto_learned_type")
