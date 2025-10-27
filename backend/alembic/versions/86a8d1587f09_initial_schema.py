"""Initial database schema generated from SQLAlchemy models."""

from alembic import op
import sqlalchemy as sa


revision = "86a8d1587f09"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column("target_fields", sa.JSON(), nullable=False),
        sa.Column("extraction_rules", sa.JSON(), nullable=True),
        sa.Column("sample_document_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_templates_name"),
    )
    op.create_index(op.f("ix_templates_id"), "templates", ["id"], unique=False)

    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=True),
        sa.Column("processed_files", sa.Integer(), nullable=True),
        sa.Column("failed_files", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_jobs_id"), "batch_jobs", ["id"], unique=False)

    op.create_table(
        "template_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=True),
        sa.Column("calculated", sa.Boolean(), nullable=True),
        sa.Column("calculation_rule", sa.String(length=500), nullable=True),
        sa.Column("regex_hint", sa.String(length=500), nullable=True),
        sa.Column("ocr_psm", sa.Integer(), nullable=True),
        sa.Column("ocr_roi", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("auto_learned_type", sa.String(length=50), nullable=True),
        sa.Column("learning_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_learned_at", sa.DateTime(), nullable=True),
        sa.Column(
            "processing_mode",
            sa.String(length=50),
            server_default=sa.text("'auto'"),
            nullable=False,
        ),
        sa.Column(
            "llm_tier",
            sa.String(length=50),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
        sa.Column("handwriting_threshold", sa.Float(), nullable=True),
        sa.Column(
            "auto_detected_handwriting",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_template_fields_id"), "template_fields", ["id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_job_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("upload_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["batch_job_id"], ["batch_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)

    op.create_table(
        "template_field_hints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_field_id", sa.Integer(), nullable=False),
        sa.Column("hint_type", sa.String(length=100), nullable=False),
        sa.Column("hint_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["template_field_id"], ["template_fields.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_field_id",
            "hint_type",
            name="uq_template_field_hints_field_type",
        ),
    )
    op.create_index(
        op.f("ix_template_field_hints_id"),
        "template_field_hints",
        ["id"],
        unique=False,
    )

    op.create_table(
        "correction_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("template_field_id", sa.Integer(), nullable=True),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=False),
        sa.Column("feedback_context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("applied_by", sa.Integer(), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_field_id"], ["template_fields.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "template_field_id",
            "corrected_value",
            name="uq_correction_feedback_document_field_value",
        ),
    )
    op.create_index(
        op.f("ix_correction_feedback_id"),
        "correction_feedback",
        ["id"],
        unique=False,
    )

    op.create_table(
        "extracted_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("field_values", sa.JSON(), nullable=False),
        sa.Column("confidence_scores", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=50), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_extracted_data_id"), "extracted_data", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_extracted_data_id"), table_name="extracted_data")
    op.drop_table("extracted_data")

    op.drop_index(op.f("ix_correction_feedback_id"), table_name="correction_feedback")
    op.drop_table("correction_feedback")

    op.drop_index(op.f("ix_template_field_hints_id"), table_name="template_field_hints")
    op.drop_table("template_field_hints")

    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_index(op.f("ix_template_fields_id"), table_name="template_fields")
    op.drop_table("template_fields")

    op.drop_index(op.f("ix_batch_jobs_id"), table_name="batch_jobs")
    op.drop_table("batch_jobs")

    op.drop_index(op.f("ix_templates_id"), table_name="templates")
    op.drop_table("templates")
