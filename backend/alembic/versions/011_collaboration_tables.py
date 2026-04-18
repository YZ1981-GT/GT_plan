"""010 collaboration_tables 协作与质控相关表

Revision ID: 010
Revises: 009
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========== 0. Enum Types ==========

    # user_role: admin/partner/manager/auditor/qc_reviewer/readonly
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'partner', 'manager', 'auditor', 'qc_reviewer', 'readonly')")

    # project_role: partner/manager/auditor/qc_reviewer/readonly
    op.execute("CREATE TYPE project_role AS ENUM ('partner', 'manager', 'auditor', 'qc_reviewer', 'readonly')")

    # review_status: pending/in_progress/approved/rejected
    op.execute("CREATE TYPE review_status AS ENUM ('pending', 'in_progress', 'approved', 'rejected')")

    # subsequent_event_type: adjusting/non_adjusting
    op.execute("CREATE TYPE subsequent_event_type AS ENUM ('adjusting', 'non_adjusting')")

    # sync_status: synced/pending/conflict
    op.execute("CREATE TYPE sync_status AS ENUM ('synced', 'pending', 'conflict')")

    # sync_type: upload/download/conflict_resolution
    op.execute("CREATE TYPE sync_type AS ENUM ('upload', 'download', 'conflict_resolution')")

    # milestone_type: planning/fieldwork/review/report/delivery/archive
    op.execute("CREATE TYPE milestone_type AS ENUM ('planning', 'fieldwork', 'review', 'report', 'delivery', 'archive')")

    # pbc_status: pending/in_progress/received/partially_received/not_received
    op.execute("CREATE TYPE pbc_status AS ENUM ('pending', 'in_progress', 'received', 'partially_received', 'not_received')")

    # confirmation_type: bank/account_receivable/other
    op.execute("CREATE TYPE confirmation_type AS ENUM ('bank', 'account_receivable', 'other')")

    # letter_format: standard/custom/bank_standard
    op.execute("CREATE TYPE letter_format AS ENUM ('standard', 'custom', 'bank_standard')")

    # reply_status: confirmed_match/confirmed_mismatch/no_reply/returned
    op.execute("CREATE TYPE reply_status AS ENUM ('confirmed_match', 'confirmed_mismatch', 'no_reply', 'returned')")

    # gc_risk_level: high/medium/low
    op.execute("CREATE TYPE gc_risk_level AS ENUM ('high', 'medium', 'low')")

    # indicator_severity: high/medium/low
    op.execute("CREATE TYPE indicator_severity AS ENUM ('high', 'medium', 'low')")

    # approval_status: pending/approved/rejected
    op.execute("CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected')")

    # ========== 1. users 表 ==========
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String, nullable=False),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("display_name", sa.String, nullable=True),
        sa.Column("role", sa.Enum("admin", "partner", "manager", "auditor", "qc_reviewer", "readonly", name="user_role", create_type=False), nullable=True),
        sa.Column("office_code", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_users_username", "users", ["username"], unique=True)
    op.create_index("idx_users_role_active", "users", ["role", "is_active"])

    # ========== 2. project_users 表 ==========
    op.create_table(
        "project_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_role", sa.Enum("partner", "manager", "auditor", "qc_reviewer", "readonly", name="project_role", create_type=False), nullable=True),
        sa.Column("assigned_cycles", JSONB, nullable=True),
        sa.Column("assigned_account_ranges", JSONB, nullable=True),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_project_users_project_user", "project_users", ["project_id", "user_id"], unique=True)
    op.create_index("idx_project_users_user", "project_users", ["user_id"])

    # ========== 3. review_records 表 ==========
    op.create_table(
        "review_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workpaper_id", UUID(as_uuid=True), sa.ForeignKey("workpapers.id"), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("reviewer_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("review_level", sa.Integer, nullable=True),
        sa.Column("review_status", sa.Enum("pending", "in_progress", "approved", "rejected", name="review_status", create_type=False), server_default="'pending'", nullable=False),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("reply_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_review_records_project", "review_records", ["project_id"])
    op.create_index("idx_review_records_reviewer", "review_records", ["reviewer_id"])

    # ========== 4. subsequent_events 表 ==========
    op.create_table(
        "subsequent_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("event_type", sa.Enum("adjusting", "non_adjusting", name="subsequent_event_type", create_type=False), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("financial_impact", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("is_disclosed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("adjustment_id", UUID(as_uuid=True), sa.ForeignKey("adjustment_entries.id"), nullable=True),
        sa.Column("disclosed_in_note_id", UUID(as_uuid=True), sa.ForeignKey("report_notes.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_subsequent_events_project_date", "subsequent_events", ["project_id", "event_date"])

    # ========== 5. se_checklist 表 ==========
    op.create_table(
        "se_checklist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("item_code", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_completed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("completed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_se_checklist_project", "se_checklist", ["project_id"])

    # ========== 6. project_sync 表 ==========
    op.create_table(
        "project_sync",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("global_version", sa.Integer, server_default="1", nullable=False),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("sync_status", sa.Enum("synced", "pending", "conflict", name="sync_status", create_type=False), server_default="'synced'", nullable=False),
        sa.Column("is_locked", sa.Boolean, server_default="false", nullable=False),
        sa.Column("locked_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("locked_at", sa.DateTime, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_project_sync_project", "project_sync", ["project_id"], unique=True)

    # ========== 7. sync_log 表 ==========
    op.create_table(
        "sync_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sync_type", sa.Enum("upload", "download", "conflict_resolution", name="sync_type", create_type=False), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_sync_log_project", "sync_log", ["project_id"])

    # ========== 8. project_timeline 表 ==========
    op.create_table(
        "project_timeline",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("milestone_type", sa.Enum("planning", "fieldwork", "review", "report", "delivery", "archive", name="milestone_type", create_type=False), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("completed_date", sa.Date, nullable=True),
        sa.Column("is_completed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_project_timeline_project_due", "project_timeline", ["project_id", "due_date"])

    # ========== 9. workhours 表 ==========
    op.create_table(
        "workhours",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("work_description", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_workhours_project_user", "workhours", ["project_id", "user_id"])
    op.create_index("idx_workhours_user_date", "workhours", ["user_id", "work_date"])

    # ========== 10. budget_hours 表 ==========
    op.create_table(
        "budget_hours",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("phase", sa.String, nullable=False),
        sa.Column("budget_hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("actual_hours", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_budget_hours_project", "budget_hours", ["project_id"])

    # ========== 11. pbc_checklist 表 ==========
    op.create_table(
        "pbc_checklist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("item_name", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("requested_date", sa.Date, nullable=True),
        sa.Column("received_date", sa.Date, nullable=True),
        sa.Column("status", sa.Enum("pending", "in_progress", "received", "partially_received", "not_received", name="pbc_status", create_type=False), server_default="'pending'", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_pbc_checklist_project", "pbc_checklist", ["project_id"])

    # ========== 12. notifications 表 ==========
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notification_type", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("related_object_type", sa.String, nullable=True),
        sa.Column("related_object_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean, server_default="false", nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_notifications_recipient_read", "notifications", ["recipient_id", "is_read", "created_at"])

    # ========== 13. confirmation_list 表 ==========
    op.create_table(
        "confirmation_list",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("confirmation_type", sa.Enum("bank", "account_receivable", "other", name="confirmation_type", create_type=False), nullable=True),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("counterparty_name", sa.String, nullable=False),
        sa.Column("account_info", sa.Text, nullable=True),
        sa.Column("balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("balance_date", sa.Date, nullable=True),
        sa.Column("status", sa.String, server_default="'pending'", nullable=False),
        sa.Column("sent_date", sa.Date, nullable=True),
        sa.Column("reply_deadline", sa.Date, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_confirmation_list_project", "confirmation_list", ["project_id"])

    # ========== 14. confirmation_letter 表 ==========
    op.create_table(
        "confirmation_letter",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("confirmation_list_id", UUID(as_uuid=True), sa.ForeignKey("confirmation_list.id"), nullable=False),
        sa.Column("letter_content", sa.Text, nullable=True),
        sa.Column("letter_format", sa.Enum("standard", "custom", "bank_standard", name="letter_format", create_type=False), nullable=True),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=True),
        sa.Column("is_sent", sa.Boolean, server_default="false", nullable=False),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("tracking_number", sa.String, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_confirmation_letter_list", "confirmation_letter", ["confirmation_list_id"])

    # ========== 15. confirmation_result 表 ==========
    op.create_table(
        "confirmation_result",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("confirmation_list_id", UUID(as_uuid=True), sa.ForeignKey("confirmation_list.id"), nullable=False),
        sa.Column("reply_date", sa.Date, nullable=True),
        sa.Column("reply_status", sa.Enum("confirmed_match", "confirmed_mismatch", "no_reply", "returned", name="reply_status", create_type=False), nullable=True),
        sa.Column("confirmed_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference_reason", sa.Text, nullable=True),
        sa.Column("needs_adjustment", sa.Boolean, server_default="false", nullable=False),
        sa.Column("alternative_procedure", sa.Text, nullable=True),
        sa.Column("alternative_conclusion", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_confirmation_result_list", "confirmation_result", ["confirmation_list_id"])

    # ========== 16. confirmation_summary 表 ==========
    op.create_table(
        "confirmation_summary",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("summary_date", sa.Date, nullable=False),
        sa.Column("total_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("sent_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("replied_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("matched_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("mismatched_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("not_replied_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("returned_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_confirmation_summary_project", "confirmation_summary", ["project_id"])

    # ========== 17. confirmation_attachment 表 ==========
    op.create_table(
        "confirmation_attachment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("confirmation_list_id", UUID(as_uuid=True), sa.ForeignKey("confirmation_list.id"), nullable=False),
        sa.Column("file_name", sa.String, nullable=False),
        sa.Column("file_path", sa.String, nullable=False),
        sa.Column("file_type", sa.String, nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_confirmation_attachment_list", "confirmation_attachment", ["confirmation_list_id"])

    # ========== 18. going_concern 表 ==========
    op.create_table(
        "going_concern",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("assessment_date", sa.Date, nullable=False),
        sa.Column("has_gc_indicator", sa.Boolean, server_default="false", nullable=False),
        sa.Column("risk_level", sa.Enum("high", "medium", "low", name="gc_risk_level", create_type=False), nullable=True),
        sa.Column("assessment_basis", sa.Text, nullable=True),
        sa.Column("management_plans", sa.Text, nullable=True),
        sa.Column("auditor_conclusion", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("idx_going_concern_project", "going_concern", ["project_id"])

    # ========== 19. going_concern_indicator 表 ==========
    op.create_table(
        "going_concern_indicator",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("going_concern_id", UUID(as_uuid=True), sa.ForeignKey("going_concern.id"), nullable=False),
        sa.Column("indicator_type", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("severity", sa.Enum("high", "medium", "low", name="indicator_severity", create_type=False), nullable=True),
        sa.Column("is_identified", sa.Boolean, server_default="false", nullable=False),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_going_concern_indicator_gc", "going_concern_indicator", ["going_concern_id"])

    # ========== 20. archive_checklist 表 ==========
    op.create_table(
        "archive_checklist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("item_code", sa.String, nullable=True),
        sa.Column("item_name", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("is_completed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("completed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_archive_checklist_project", "archive_checklist", ["project_id"])

    # ========== 21. archive_modifications 表 ==========
    op.create_table(
        "archive_modifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("requested_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime, nullable=False),
        sa.Column("modification_type", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("approval_status", sa.Enum("pending", "approved", "rejected", name="approval_status", create_type=False), server_default="'pending'", nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("approval_comments", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_archive_modifications_project_status", "archive_modifications", ["project_id", "approval_status"])


def downgrade() -> None:
    # 删除 tables（反向顺序）
    op.drop_table("archive_modifications")
    op.drop_table("archive_checklist")
    op.drop_table("going_concern_indicator")
    op.drop_table("going_concern")
    op.drop_table("confirmation_attachment")
    op.drop_table("confirmation_summary")
    op.drop_table("confirmation_result")
    op.drop_table("confirmation_letter")
    op.drop_table("confirmation_list")
    op.drop_table("notifications")
    op.drop_table("pbc_checklist")
    op.drop_table("budget_hours")
    op.drop_table("workhours")
    op.drop_table("project_timeline")
    op.drop_table("sync_log")
    op.drop_table("project_sync")
    op.drop_table("se_checklist")
    op.drop_table("subsequent_events")
    op.drop_table("review_records")
    op.drop_table("project_users")
    op.drop_table("users")

    # 删除枚举类型
    sa.Enum(name="approval_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="indicator_severity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="gc_risk_level").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reply_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="letter_format").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="confirmation_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="pbc_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="milestone_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sync_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sync_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="subsequent_event_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="review_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="project_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
