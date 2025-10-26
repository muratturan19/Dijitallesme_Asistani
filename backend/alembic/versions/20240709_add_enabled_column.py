"""Add enabled column to template_fields"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "79a5d0b2c745"
down_revision = "4b01f4a686aa"
branch_labels = None
depends_on = None


TABLE_NAME = "template_fields"
COLUMN_NAME = "enabled"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}

    if COLUMN_NAME not in existing_columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.Boolean(), nullable=True, server_default="1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}

    if COLUMN_NAME in existing_columns:
        op.drop_column(TABLE_NAME, COLUMN_NAME)
