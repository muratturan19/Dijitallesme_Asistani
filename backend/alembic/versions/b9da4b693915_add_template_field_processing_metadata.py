"""add template field processing metadata"""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "b9da4b693915"
down_revision = "4f8f7b9b7a3d"
branch_labels = None
depends_on = None

TABLE_NAME = "template_fields"


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    columns = _existing_columns()

    if "processing_mode" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "processing_mode",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'auto'"),
            ),
        )

    if "llm_tier" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "llm_tier",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'standard'"),
            ),
        )

    if "handwriting_threshold" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("handwriting_threshold", sa.Float(), nullable=True),
        )

    if "auto_detected_handwriting" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "auto_detected_handwriting",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    bind = op.get_bind()
    templates = bind.execute(sa.text("SELECT id, target_fields FROM templates"))

    for row in templates:
        mapping = row._mapping
        template_id = mapping["id"]
        raw_fields = mapping.get("target_fields")

        try:
            fields = json.loads(raw_fields) if raw_fields else []
        except (TypeError, ValueError):
            fields = []

        if not isinstance(fields, list):
            continue

        updated = False

        for field in fields:
            if not isinstance(field, dict):
                continue

            if not field.get("processing_mode"):
                field["processing_mode"] = "auto"
                updated = True

            if not field.get("llm_tier"):
                field["llm_tier"] = "standard"
                updated = True

            if "handwriting_threshold" not in field:
                field["handwriting_threshold"] = None
                updated = True

            if "auto_detected_handwriting" not in field:
                field["auto_detected_handwriting"] = False
                updated = True

        if updated:
            bind.execute(
                sa.text("UPDATE templates SET target_fields = :payload WHERE id = :template_id"),
                {"payload": json.dumps(fields, ensure_ascii=False), "template_id": template_id},
            )


def downgrade() -> None:
    columns = _existing_columns()

    if "auto_detected_handwriting" in columns:
        op.drop_column(TABLE_NAME, "auto_detected_handwriting")

    if "handwriting_threshold" in columns:
        op.drop_column(TABLE_NAME, "handwriting_threshold")

    if "llm_tier" in columns:
        op.drop_column(TABLE_NAME, "llm_tier")

    if "processing_mode" in columns:
        op.drop_column(TABLE_NAME, "processing_mode")

    bind = op.get_bind()
    templates = bind.execute(sa.text("SELECT id, target_fields FROM templates"))

    for row in templates:
        mapping = row._mapping
        template_id = mapping["id"]
        raw_fields = mapping.get("target_fields")

        try:
            fields = json.loads(raw_fields) if raw_fields else []
        except (TypeError, ValueError):
            fields = []

        if not isinstance(fields, list):
            continue

        updated = False

        for field in fields:
            if not isinstance(field, dict):
                continue

            if field.pop("processing_mode", None) is not None:
                updated = True
            if field.pop("llm_tier", None) is not None:
                updated = True
            if field.pop("handwriting_threshold", None) is not None:
                updated = True
            if field.pop("auto_detected_handwriting", None) is not None:
                updated = True

        if updated:
            bind.execute(
                sa.text("UPDATE templates SET target_fields = :payload WHERE id = :template_id"),
                {"payload": json.dumps(fields, ensure_ascii=False), "template_id": template_id},
            )
