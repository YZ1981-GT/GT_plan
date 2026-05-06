"""Refinement Round 5: EQCR (Engagement Quality Control Review) tables

Revision ID: round5_eqcr_20260505
Revises: round1_review_closure_20260508

本迁移一次性落地 Round 5（独立复核）任务 1 的全部数据模型变更：

1. 新建 6 张表：
   - ``eqcr_opinions``               EQCR 判断类事项意见留痕
   - ``eqcr_review_notes``           EQCR 独立复核笔记（默认仅 EQCR 可见）
   - ``eqcr_shadow_computations``    EQCR 独立取数留痕（无软删除，永久保留）
   - ``eqcr_disagreement_resolutions`` EQCR 异议合议结论
   - ``related_party_registry``      关联方主数据（项目级最小建模）
   - ``related_party_transactions``  关联方交易明细
2. ``report_status`` PG enum 新增 ``eqcr_approved`` 值（位于 ``review`` 与
   ``final`` 之间；PG 不支持枚举中间插入，只能 ADD VALUE，逻辑顺序由代码维护）。
3. ``work_hours.purpose`` 新增 ``VARCHAR(20) NULL`` 列，允许值
   ``preparation|review|eqcr|training|admin``（字符串约定，不建 DB enum）。

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用 ``IF [NOT] EXISTS``
+ inspector 防重。PG ``ALTER TYPE ADD VALUE`` 不能在事务中执行，使用
``op.get_context().autocommit_block()``。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round5_eqcr_20260505"
down_revision = "round1_review_closure_20260508"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    cols = {c["name"] for c in _inspector().get_columns(table_name)}
    return column_name in cols


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    indexes = {ix["name"] for ix in _inspector().get_indexes(table_name)}
    return index_name in indexes


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enum_has_value(enum_name: str, value: str) -> bool:
    """检查 PG enum 是否已含某值（幂等保护）。SQLite 下直接返回 True 跳过。"""
    if not _is_postgres():
        return True
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_type t "
            "JOIN pg_enum e ON t.oid = e.enumtypid "
            "WHERE t.typname = :name AND e.enumlabel = :val"
        ),
        {"name": enum_name, "val": value},
    ).first()
    return result is not None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:  # noqa: C901 - 按章节顺序易读
    # ---------------- 1. eqcr_opinions ----------------------------------
    if not _has_table("eqcr_opinions"):
        op.create_table(
            "eqcr_opinions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("domain", sa.String(length=32), nullable=False),
            sa.Column("verdict", sa.String(length=32), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column(
                "extra_payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index("eqcr_opinions", "idx_eqcr_opinions_project_domain"):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_eqcr_opinions_project_domain "
                "ON eqcr_opinions (project_id, domain) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_eqcr_opinions_project_domain",
                "eqcr_opinions",
                ["project_id", "domain"],
            )

    # ---------------- 2. eqcr_review_notes ------------------------------
    if not _has_table("eqcr_review_notes"):
        op.create_table(
            "eqcr_review_notes",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column(
                "shared_to_team",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("shared_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index("eqcr_review_notes", "idx_eqcr_review_notes_project"):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_eqcr_review_notes_project "
                "ON eqcr_review_notes (project_id) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_eqcr_review_notes_project",
                "eqcr_review_notes",
                ["project_id"],
            )

    # ---------------- 3. eqcr_shadow_computations -----------------------
    if not _has_table("eqcr_shadow_computations"):
        op.create_table(
            "eqcr_shadow_computations",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("computation_type", sa.String(length=64), nullable=False),
            sa.Column(
                "params",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "result",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "team_result_snapshot",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "has_diff",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index(
        "eqcr_shadow_computations", "idx_eqcr_shadow_comp_project_type"
    ):
        op.create_index(
            "idx_eqcr_shadow_comp_project_type",
            "eqcr_shadow_computations",
            ["project_id", "computation_type"],
        )

    # ---------------- 4. eqcr_disagreement_resolutions ------------------
    if not _has_table("eqcr_disagreement_resolutions"):
        op.create_table(
            "eqcr_disagreement_resolutions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "eqcr_opinion_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("eqcr_opinions.id"),
                nullable=False,
            ),
            sa.Column(
                "participants",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("resolution_verdict", sa.String(length=32), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index(
        "eqcr_disagreement_resolutions", "idx_eqcr_disagreement_project"
    ):
        op.create_index(
            "idx_eqcr_disagreement_project",
            "eqcr_disagreement_resolutions",
            ["project_id"],
        )

    # ---------------- 5. related_party_registry -------------------------
    if not _has_table("related_party_registry"):
        op.create_table(
            "related_party_registry",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("relation_type", sa.String(length=64), nullable=False),
            sa.Column(
                "is_controlled_by_same_party",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index(
        "related_party_registry", "idx_related_party_registry_project"
    ):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_related_party_registry_project "
                "ON related_party_registry (project_id) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_related_party_registry_project",
                "related_party_registry",
                ["project_id"],
            )
    if not _has_index(
        "related_party_registry", "uq_related_party_registry_project_name"
    ):
        if _is_postgres():
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_related_party_registry_project_name "
                "ON related_party_registry (project_id, name) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "uq_related_party_registry_project_name",
                "related_party_registry",
                ["project_id", "name"],
                unique=True,
            )

    # ---------------- 6. related_party_transactions ---------------------
    if not _has_table("related_party_transactions"):
        op.create_table(
            "related_party_transactions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id"),
                nullable=False,
            ),
            sa.Column(
                "related_party_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("related_party_registry.id"),
                nullable=False,
            ),
            sa.Column("amount", sa.Numeric(20, 2), nullable=True),
            sa.Column("transaction_type", sa.String(length=64), nullable=False),
            sa.Column("is_arms_length", sa.Boolean(), nullable=True),
            sa.Column(
                "evidence_refs",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index("related_party_transactions", "idx_rp_transactions_project"):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_rp_transactions_project "
                "ON related_party_transactions (project_id) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_rp_transactions_project",
                "related_party_transactions",
                ["project_id"],
            )
    if not _has_index("related_party_transactions", "idx_rp_transactions_party"):
        if _is_postgres():
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_rp_transactions_party "
                "ON related_party_transactions (related_party_id) "
                "WHERE is_deleted = false"
            )
        else:
            op.create_index(
                "idx_rp_transactions_party",
                "related_party_transactions",
                ["related_party_id"],
            )

    # ---------------- 7. report_status enum: ADD VALUE 'eqcr_approved' --
    # PG enum 不支持中间插入，用 ADD VALUE；逻辑顺序由代码（ReportStatus）维护。
    if _is_postgres() and not _enum_has_value("report_status", "eqcr_approved"):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE report_status ADD VALUE IF NOT EXISTS 'eqcr_approved'"
            )

    # ---------------- 8. work_hours.purpose -----------------------------
    if _has_table("work_hours") and not _has_column("work_hours", "purpose"):
        op.add_column(
            "work_hours",
            sa.Column("purpose", sa.String(length=20), nullable=True),
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 8. work_hours.purpose
    if _has_column("work_hours", "purpose"):
        op.drop_column("work_hours", "purpose")

    # 7. report_status enum: PG 不支持 DROP VALUE，重建 enum 回退
    if _is_postgres() and _enum_has_value("report_status", "eqcr_approved"):
        # 先把任何处于 eqcr_approved 的行回退到 review（保守选择，上游代码会重算状态）
        op.execute(
            "UPDATE audit_report SET status = 'review' "
            "WHERE status = 'eqcr_approved'"
        )
        # 重建 enum：
        # 1) 重命名旧类型，
        # 2) 新建不含 eqcr_approved 的类型，
        # 3) 表列转成新类型，
        # 4) 丢弃旧类型。
        op.execute("ALTER TYPE report_status RENAME TO report_status_old")
        op.execute(
            "CREATE TYPE report_status AS ENUM ('draft', 'review', 'final')"
        )
        op.execute(
            "ALTER TABLE audit_report "
            "ALTER COLUMN status DROP DEFAULT, "
            "ALTER COLUMN status TYPE report_status "
            "USING status::text::report_status, "
            "ALTER COLUMN status SET DEFAULT 'draft'"
        )
        op.execute("DROP TYPE report_status_old")

    # 6. related_party_transactions
    if _has_index("related_party_transactions", "idx_rp_transactions_party"):
        op.drop_index(
            "idx_rp_transactions_party",
            table_name="related_party_transactions",
        )
    if _has_index("related_party_transactions", "idx_rp_transactions_project"):
        op.drop_index(
            "idx_rp_transactions_project",
            table_name="related_party_transactions",
        )
    if _has_table("related_party_transactions"):
        op.drop_table("related_party_transactions")

    # 5. related_party_registry
    if _has_index(
        "related_party_registry", "uq_related_party_registry_project_name"
    ):
        op.drop_index(
            "uq_related_party_registry_project_name",
            table_name="related_party_registry",
        )
    if _has_index(
        "related_party_registry", "idx_related_party_registry_project"
    ):
        op.drop_index(
            "idx_related_party_registry_project",
            table_name="related_party_registry",
        )
    if _has_table("related_party_registry"):
        op.drop_table("related_party_registry")

    # 4. eqcr_disagreement_resolutions
    if _has_index(
        "eqcr_disagreement_resolutions", "idx_eqcr_disagreement_project"
    ):
        op.drop_index(
            "idx_eqcr_disagreement_project",
            table_name="eqcr_disagreement_resolutions",
        )
    if _has_table("eqcr_disagreement_resolutions"):
        op.drop_table("eqcr_disagreement_resolutions")

    # 3. eqcr_shadow_computations
    if _has_index(
        "eqcr_shadow_computations", "idx_eqcr_shadow_comp_project_type"
    ):
        op.drop_index(
            "idx_eqcr_shadow_comp_project_type",
            table_name="eqcr_shadow_computations",
        )
    if _has_table("eqcr_shadow_computations"):
        op.drop_table("eqcr_shadow_computations")

    # 2. eqcr_review_notes
    if _has_index("eqcr_review_notes", "idx_eqcr_review_notes_project"):
        op.drop_index(
            "idx_eqcr_review_notes_project", table_name="eqcr_review_notes"
        )
    if _has_table("eqcr_review_notes"):
        op.drop_table("eqcr_review_notes")

    # 1. eqcr_opinions
    if _has_index("eqcr_opinions", "idx_eqcr_opinions_project_domain"):
        op.drop_index(
            "idx_eqcr_opinions_project_domain", table_name="eqcr_opinions"
        )
    if _has_table("eqcr_opinions"):
        op.drop_table("eqcr_opinions")
