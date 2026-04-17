"""Phase 9 Task 1.1: staff_members + project_assignments + work_hours

Revision ID: 020
Revises: 019
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # staff_members
    op.create_table(
        "staff_members",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("employee_no", sa.String(50), unique=True, nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("title", sa.String(50), nullable=True),
        sa.Column("partner_name", sa.String(100), nullable=True),
        sa.Column("partner_id", sa.UUID(), sa.ForeignKey("staff_members.id"), nullable=True),
        sa.Column("specialty", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("resume_data", JSONB, nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_staff_department", "staff_members", ["department"],
                    postgresql_where=sa.text("is_deleted = false"))
    op.create_index("idx_staff_partner", "staff_members", ["partner_id"],
                    postgresql_where=sa.text("is_deleted = false"))

    # project_assignments
    op.create_table(
        "project_assignments",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("staff_id", sa.UUID(), sa.ForeignKey("staff_members.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("assigned_cycles", JSONB, nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_assignment_project_staff", "project_assignments",
                    ["project_id", "staff_id"], unique=True,
                    postgresql_where=sa.text("is_deleted = false"))
    op.create_index("idx_assignment_staff", "project_assignments", ["staff_id"],
                    postgresql_where=sa.text("is_deleted = false"))

    # work_hours
    op.create_table(
        "work_hours",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("staff_id", sa.UUID(), sa.ForeignKey("staff_members.id"), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(4, 1), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'draft'")),
        sa.Column("ai_suggested", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_workhour_staff_date", "work_hours", ["staff_id", "work_date"])
    op.create_index("idx_workhour_project", "work_hours", ["project_id"],
                    postgresql_where=sa.text("is_deleted = false"))


def downgrade() -> None:
    op.drop_table("work_hours")
    op.drop_table("project_assignments")
    op.drop_table("staff_members")
