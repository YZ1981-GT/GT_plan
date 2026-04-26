"""Phase 10: review_conversations + review_messages + forum_posts + forum_comments

Revision ID: 023
Revises: 022
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- review_conversations ---
    op.create_table(
        "review_conversations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("initiator_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("related_object_type", sa.String(50), nullable=False),
        sa.Column("related_object_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("cell_ref", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_review_conv_project", "review_conversations",
                    ["project_id", "status"])

    # --- review_messages ---
    op.create_table(
        "review_messages",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("review_conversations.id"), nullable=False),
        sa.Column("sender_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(20),
                  server_default=sa.text("'text'")),
        sa.Column("attachment_path", sa.String(500), nullable=True),
        sa.Column("finding_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_review_msg_conv", "review_messages",
                    ["conversation_id", "created_at"])

    # --- forum_posts ---
    op.create_table(
        "forum_posts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("author_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("category", sa.String(20), server_default=sa.text("'share'")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # --- forum_comments ---
    op.create_table(
        "forum_comments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("post_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("forum_posts.id"), nullable=False),
        sa.Column("author_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_forum_comments_post", "forum_comments", ["post_id"])


def downgrade() -> None:
    op.drop_table("forum_comments")
    op.drop_table("forum_posts")
    op.drop_table("review_messages")
    op.drop_table("review_conversations")
