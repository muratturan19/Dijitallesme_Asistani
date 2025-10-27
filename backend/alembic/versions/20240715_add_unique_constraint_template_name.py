"""
Add unique constraint to template name.

Revision ID: 32f8eac34adf
Revises: 79a5d0b2c745
Create Date: 2024-07-15 00:00:00.000000
"""

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "32f8eac34adf"
down_revision = "79a5d0b2c745"
branch_labels = None
depends_on = None


TABLE_NAME = "templates"
CONSTRAINT_NAME = "uq_templates_name"


def _normalize(value: str) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def upgrade() -> None:
    bind = op.get_bind()

    result = bind.execute(text(f"SELECT id, name FROM {TABLE_NAME}"))
    rows = result.fetchall()
    seen = {}

    for row in rows:
        mapping = row._mapping
        row_id = mapping["id"]
        row_name = mapping.get("name")

        normalized = _normalize(row_name)

        if not normalized:
            continue

        if normalized in seen:
            new_name = (
                f"{row_name}_{row_id}" if row_name else f"template_{row_id}"
            )
            bind.execute(
                text(
                    f"UPDATE {TABLE_NAME} SET name = :new_name WHERE id = :template_id"
                ),
                {"new_name": new_name, "template_id": row_id},
            )
        else:
            seen[normalized] = row_id

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT_NAME, ["name"])


def downgrade() -> None:
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
