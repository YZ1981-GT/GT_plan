"""Refinement Round 2: budget fields + handover records + system_settings hourly_rates

Revision ID: round2_budget_handover_20260510
Revises: round1_long_term_compliance_20260508

本迁移落地 Round 2 Sprint 3（长期运营合规）的数据模型变更：

1. ``projects`` 表新增预算字段：
   - ``budget_hours`` INT NULL — 预算工时
   - ``contract_amount`` NUMERIC(20,2) NULL — 合同金额
   - ``budgeted_by`` UUID NULL FK(users.id) — 预算填写人
   - ``budgeted_at`` DATETIME NULL — 预算填写时间

2. 新建 ``handover_records`` 表 — 人员交接记录（需求 10）

3. 新建 ``system_settings`` 表（如不存在）— 键值对配置存储，
   并插入 ``hourly_rates`` 默认配置（需求 9 成本计算依赖）

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用
``IF [NOT] EXISTS`` + inspector 防重。
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round2_budget_handover_20260510"
down_revision = "round1_long_term_compliance_20260508"
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


# ---------------------------------------------------------------------------
# hourly_rates 默认配置
# ---------------------------------------------------------------------------

HOURLY_RATES_DEFAULT = {
    "partner": 3000,
    "manager": 1500,
    "senior": 900,
    "auditor": 500,
    "intern": 200,
}


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:  # noqa: C901
    # ============== 1. projects: budget fields =============================
    if _has_table("projects"):
        if not _has_column("projects", "budget_hours"):
            op.add_column(
                "projects",
                sa.Column("budget_hours", sa.Integer(), nullable=True),
            )
        if not _has_column("projects", "contract_amount"):
            op.add_column(
                "projects",
                sa.Column(
                    "contract_amount",
                    sa.Numeric(precision=20, scale=2),
                    nullable=True,
                ),
            )
        if not _has_column("projects", "budgeted_by"):
            op.add_column(
                "projects",
                sa.Column(
                    "budgeted_by",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            )
        if not _has_column("projects", "budgeted_at"):
            op.add_column(
                "projects",
                sa.Column("budgeted_at", sa.DateTime(), nullable=True),
            )

    # ============== 2. handover_records ====================================
    if not _has_table("handover_records"):
        op.create_table(
            "handover_records",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "from_staff_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "to_staff_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column("scope", sa.String(length=20), nullable=False),
            sa.Column(
                "project_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("reason_code", sa.String(length=30), nullable=False),
            sa.Column("reason_detail", sa.Text(), nullable=True),
            sa.Column("effective_date", sa.Date(), nullable=False),
            sa.Column(
                "workpapers_moved", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "issues_moved", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "assignments_moved", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "executed_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "executed_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
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

    # Indexes for handover_records
    if not _has_index("handover_records", "idx_handover_records_from_staff"):
        op.create_index(
            "idx_handover_records_from_staff",
            "handover_records",
            ["from_staff_id", sa.text("executed_at DESC")],
        )
    if not _has_index("handover_records", "idx_handover_records_to_staff"):
        op.create_index(
            "idx_handover_records_to_staff",
            "handover_records",
            ["to_staff_id"],
        )
    if not _has_index("handover_records", "idx_handover_records_effective_date"):
        op.create_index(
            "idx_handover_records_effective_date",
            "handover_records",
            ["effective_date"],
        )

    # ============== 3. system_settings table + hourly_rates ================
    if not _has_table("system_settings"):
        op.create_table(
            "system_settings",
            sa.Column(
                "key", sa.String(length=100), primary_key=True, nullable=False
            ),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("value_type", sa.String(length=20), server_default="text",
                      nullable=False, comment="值类型: text/json/int/bool"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column(
                "updated_by",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

    # 插入 hourly_rates 默认值（幂等：不存在才插入）
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT key FROM system_settings WHERE key = 'hourly_rates'")
    )
    if result.fetchone() is None:
        bind.execute(
            sa.text(
                "INSERT INTO system_settings (key, value, value_type, description) "
                "VALUES (:key, :value, :value_type, :description)"
            ),
            {
                "key": "hourly_rates",
                "value": json.dumps(HOURLY_RATES_DEFAULT),
                "value_type": "json",
                "description": "各职级小时费率（元/小时），用于项目成本计算",
            },
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # handover_records indexes
    if _has_index("handover_records", "idx_handover_records_effective_date"):
        op.drop_index(
            "idx_handover_records_effective_date",
            table_name="handover_records",
        )
    if _has_index("handover_records", "idx_handover_records_to_staff"):
        op.drop_index(
            "idx_handover_records_to_staff",
            table_name="handover_records",
        )
    if _has_index("handover_records", "idx_handover_records_from_staff"):
        op.drop_index(
            "idx_handover_records_from_staff",
            table_name="handover_records",
        )

    # handover_records table
    if _has_table("handover_records"):
        op.drop_table("handover_records")

    # system_settings: remove hourly_rates row (keep table for rotation_check_service)
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM system_settings WHERE key = 'hourly_rates'")
    )

    # projects: budget columns
    if _has_column("projects", "budgeted_at"):
        op.drop_column("projects", "budgeted_at")
    if _has_column("projects", "budgeted_by"):
        op.drop_column("projects", "budgeted_by")
    if _has_column("projects", "contract_amount"):
        op.drop_column("projects", "contract_amount")
    if _has_column("projects", "budget_hours"):
        op.drop_column("projects", "budget_hours")
