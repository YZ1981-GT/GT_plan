"""Foundation Sprint 1 Task 1.3: cell_annotations 新增 annotation_type + sheet_name

支持复核标记（review_mark）与普通批注（comment）区分，
以及按 sheet 过滤批注。

Revision ID: workpaper_completion_cell_annotations_20260517
Revises: custom_query_templates_20260518
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "workpaper_completion_cell_annotations_20260517"
down_revision = "custom_query_templates_20260518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cell_annotations",
        sa.Column(
            "annotation_type",
            sa.String(30),
            nullable=False,
            server_default="comment",
        ),
    )
    op.add_column(
        "cell_annotations",
        sa.Column(
            "sheet_name",
            sa.String(100),
            nullable=True,
        ),
    )
    # Index for review-status aggregation queries
    op.create_index(
        "idx_cell_annotations_type_object",
        "cell_annotations",
        ["annotation_type", "object_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_cell_annotations_type_object", table_name="cell_annotations")
    op.drop_column("cell_annotations", "sheet_name")
    op.drop_column("cell_annotations", "annotation_type")
