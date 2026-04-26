"""Phase 10: cell_annotations + consol_snapshots + check_ins

Revision ID: 024
Revises: 023
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- cell_annotations ---
    op.create_table(
        "cell_annotations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("cell_ref", sa.String(100), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("author_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mentioned_user_ids", JSONB, nullable=True),
        sa.Column("linked_annotation_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_cell_ann_project_obj", "cell_annotations",
                    ["project_id", "object_type", "object_id"])
    op.create_index("idx_cell_ann_status", "cell_annotations",
                    ["project_id", "status"],
                    postgresql_where=sa.text("is_deleted = false"))

    # --- consol_snapshots ---
    op.create_table(
        "consol_snapshots",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("snapshot_data", JSONB, nullable=False),
        sa.Column("trigger_reason", sa.String(30), nullable=False),
        sa.Column("diff_summary", JSONB, nullable=True),
        sa.Column("created_by", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_consol_snap_project", "consol_snapshots",
                    ["project_id", "year", "created_at"])

    # --- check_ins ---
    op.create_table(
        "check_ins",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("staff_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("staff_members.id"), nullable=False),
        sa.Column("check_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("location_name", sa.String(200), nullable=True),
        sa.Column("check_type", sa.String(20), server_default=sa.text("'morning'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_check_ins_staff", "check_ins",
                    ["staff_id", "check_time"])


def downgrade() -> None:
    op.drop_table("check_ins")
    op.drop_table("consol_snapshots")
    op.drop_table("cell_annotations")
