"""Add OCR configuration columns to template_fields"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "4b01f4a686aa"
down_revision = None
branch_labels = None
depends_on = None


TABLE_NAME = "template_fields"
PSM_COLUMN = "ocr_psm"
ROI_COLUMN = "ocr_roi"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}

    if PSM_COLUMN not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column(PSM_COLUMN, sa.Integer(), nullable=True))

    if ROI_COLUMN not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column(ROI_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}

    if ROI_COLUMN in existing_columns:
        op.drop_column(TABLE_NAME, ROI_COLUMN)

    if PSM_COLUMN in existing_columns:
        op.drop_column(TABLE_NAME, PSM_COLUMN)
