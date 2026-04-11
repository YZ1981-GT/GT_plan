"""初始化5张核心业务表及枚举类型

Revision ID: 001
Revises: None
Create Date: 2025-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. 创建 PostgreSQL 枚举类型
    # ------------------------------------------------------------------
    user_role = postgresql.ENUM(
        "admin", "partner", "manager", "auditor", "qc", "readonly",
        name="user_role",
        create_type=True,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    project_type = postgresql.ENUM(
        "annual", "special", "ipo", "internal_control",
        name="project_type",
        create_type=True,
    )
    project_type.create(op.get_bind(), checkfirst=True)

    project_status = postgresql.ENUM(
        "created", "planning", "execution", "completion", "reporting", "archived",
        name="project_status",
        create_type=True,
    )
    project_status.create(op.get_bind(), checkfirst=True)

    project_user_role = postgresql.ENUM(
        "partner", "manager", "auditor", "qc", "readonly",
        name="project_user_role",
        create_type=True,
    )
    project_user_role.create(op.get_bind(), checkfirst=True)

    permission_level = postgresql.ENUM(
        "edit", "review", "readonly",
        name="permission_level",
        create_type=True,
    )
    permission_level.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. 创建 users 表
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(150), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("office_code", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        # SoftDeleteMixin
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        # TimestampMixin
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        # AuditMixin
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        # AuditMixin FK 约束（自引用，需延迟创建）
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_users_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_users_updated_by"),
    )

    # ------------------------------------------------------------------
    # 3. 创建 projects 表
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("audit_period_start", sa.Date(), nullable=True),
        sa.Column("audit_period_end", sa.Date(), nullable=True),
        sa.Column(
            "project_type",
            postgresql.ENUM(name="project_type", create_type=False),
            nullable=True,
        ),
        sa.Column("materiality_level", sa.Float(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="project_status", create_type=False),
            server_default=sa.text("'created'"),
            nullable=False,
        ),
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
        # SoftDeleteMixin
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        # TimestampMixin
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        # AuditMixin
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 4. 创建 project_users 表
    # ------------------------------------------------------------------
    op.create_table(
        "project_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM(name="project_user_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "permission_level",
            postgresql.ENUM(name="permission_level", create_type=False),
            server_default=sa.text("'readonly'"),
            nullable=False,
        ),
        sa.Column("scope_cycles", sa.Text(), nullable=True),
        sa.Column("scope_accounts", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        # SoftDeleteMixin
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        # TimestampMixin
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 5. 创建 logs 表
    # ------------------------------------------------------------------
    op.create_table(
        "logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 6. 创建 notifications 表
    # ------------------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("related_object_type", sa.String(100), nullable=True),
        sa.Column("related_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 7. 创建索引
    # ------------------------------------------------------------------

    # 复合索引：project_users(project_id, user_id) WHERE is_deleted=false（唯一）
    op.create_index(
        "idx_project_users_project_user",
        "project_users",
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # 复合索引：logs(object_type, object_id)
    op.create_index(
        "idx_logs_object",
        "logs",
        ["object_type", "object_id"],
    )

    # 复合索引：logs(user_id, created_at DESC)
    op.create_index(
        "idx_logs_user_time",
        "logs",
        ["user_id", sa.text("created_at DESC")],
    )

    # 复合索引：notifications(recipient_id, is_read)
    op.create_index(
        "idx_notifications_recipient_read",
        "notifications",
        ["recipient_id", "is_read"],
    )

    # 过滤索引：users(is_active) WHERE is_deleted=false
    op.create_index(
        "idx_users_active",
        "users",
        ["is_active"],
        postgresql_where=sa.text("is_deleted = false"),
    )

    # 过滤索引：projects(status) WHERE is_deleted=false
    op.create_index(
        "idx_projects_status",
        "projects",
        ["status"],
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 按创建的逆序删除索引
    # ------------------------------------------------------------------
    op.drop_index("idx_projects_status", table_name="projects")
    op.drop_index("idx_users_active", table_name="users")
    op.drop_index("idx_notifications_recipient_read", table_name="notifications")
    op.drop_index("idx_logs_user_time", table_name="logs")
    op.drop_index("idx_logs_object", table_name="logs")
    op.drop_index("idx_project_users_project_user", table_name="project_users")

    # ------------------------------------------------------------------
    # 按创建的逆序删除表
    # ------------------------------------------------------------------
    op.drop_table("notifications")
    op.drop_table("logs")
    op.drop_table("project_users")
    op.drop_table("projects")
    op.drop_table("users")

    # ------------------------------------------------------------------
    # 删除枚举类型（逆序）
    # ------------------------------------------------------------------
    postgresql.ENUM(name="permission_level").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_user_role").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
