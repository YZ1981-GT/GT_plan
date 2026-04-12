"""017 - AI chat session tables

Revision ID: 017_ai_chat
Revises: 016
Create Date: 2024-12-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "017_ai_chat"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- session_type_enum ---
    session_type_enum = sa.Enum(
        "general", "contract", "workpaper", "confirmation",
        name="session_type_enum",
    )
    session_type_enum.create(op.get_bind(), checkfirst=True)

    # --- analysis_report_status_enum ---
    analysis_report_status_enum = sa.Enum(
        "pending", "analyzing", "completed", "failed",
        name="analysis_report_status_enum",
    )
    analysis_report_status_enum.create(op.get_bind(), checkfirst=True)

    # --- ai_chat_session ---
    op.create_table(
        "ai_chat_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id", UUID(as_uuid=True),
            sa.ForeignKey("projects.id"), nullable=False,
        ),
        sa.Column(
            "session_type", session_type_enum, nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column(
            "total_messages", sa.Integer,
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "total_tokens", sa.Integer,
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("context_summary", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_ai_chat_session_project", "ai_chat_session", ["project_id"])
    op.create_index("ix_ai_chat_session_user", "ai_chat_session", ["user_id"])

    # --- ai_chat_message ---
    op.create_table(
        "ai_chat_message",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_chat_session.id"), nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "system", name="chat_role_enum"),
            nullable=False,
        ),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("referenced_sources", JSONB, nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_ai_chat_message_session", "ai_chat_message", ["session_id"])

    # --- ai_knowledge_base ---
    op.create_table(
        "ai_knowledge_base",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id", UUID(as_uuid=True),
            sa.ForeignKey("projects.id"), nullable=False,
        ),
        sa.Column("doc_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "workpaper", "contract", "confirmation", "document", "report",
                name="source_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_ai_knowledge_base_project", "ai_knowledge_base", ["project_id"])
    op.create_index("ix_ai_knowledge_base_doc", "ai_knowledge_base", ["doc_uuid"])
    op.create_index("ix_ai_knowledge_base_hash", "ai_knowledge_base", ["content_hash"])

    # --- ai_analysis_report ---
    op.create_table(
        "ai_analysis_report",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id", UUID(as_uuid=True),
            sa.ForeignKey("projects.id"), nullable=False,
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("key_findings", JSONB, nullable=True),
        sa.Column("risk_indicators", JSONB, nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "status", analysis_report_status_enum, nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_ai_analysis_report_project", "ai_analysis_report", ["project_id"])
    op.create_index("ix_ai_analysis_report_status", "ai_analysis_report", ["status"])

    # --- ai_analysis_item ---
    op.create_table(
        "ai_analysis_item",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_analysis_report.id"), nullable=False,
        ),
        sa.Column(
            "clause_type",
            sa.Enum(
                "amount", "payment_terms", "delivery_terms", "penalty",
                "guarantee", "pledge", "related_party", "special_terms",
                "pricing", "duration",
                name="clause_type_enum",
            ),
            nullable=True,
        ),
        sa.Column("clause_text", sa.Text, nullable=False),
        sa.Column("extraction_result", JSONB, nullable=True),
        sa.Column(
            "risk_flag", sa.Boolean,
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column("risk_reason", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "human_confirmed", sa.Boolean,
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column("human_note", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_ai_analysis_item_report", "ai_analysis_item", ["report_id"])

    # --- ai_confirmation_audit ---
    op.create_table(
        "ai_confirmation_audit",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id", UUID(as_uuid=True),
            sa.ForeignKey("projects.id"), nullable=False,
        ),
        sa.Column("confirmation_type", sa.String(50), nullable=False),
        sa.Column("original_content", sa.Text, nullable=False),
        sa.Column("response_content", sa.Text, nullable=True),
        sa.Column("audit_period", sa.String(50), nullable=False),
        sa.Column("audit_result", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "processing", "completed", "failed",
                name="ai_confirmation_status_enum",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_ai_confirmation_audit_project",
        "ai_confirmation_audit", ["project_id"],
    )
    op.create_index(
        "ix_ai_confirmation_audit_status",
        "ai_confirmation_audit", ["status"],
    )


def downgrade() -> None:
    op.drop_table("ai_confirmation_audit")
    op.drop_table("ai_analysis_item")
    op.drop_table("ai_analysis_report")
    op.drop_table("ai_knowledge_base")
    op.drop_table("ai_chat_message")
    op.drop_table("ai_chat_session")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS session_type_enum")
    op.execute("DROP TYPE IF EXISTS analysis_report_status_enum")
