"""F41 / Sprint 7.5: pre-allocate tenant_id column on ledger tables.

背景（requirements F41 / design D11.2）：
- 为未来真正的多租户能力预留数据列，**本迁移不启用多租户逻辑**。
- 四张 Tb* 业务表 + `ledger_datasets` metadata 表统一加 `tenant_id VARCHAR(64)
  NOT NULL DEFAULT 'default'`。
- 每张表再加一条复合索引 `(tenant_id, project_id, year)`，使未来多租户查询（最常用
  的 tenant 级 scoping + 项目年度过滤）能够直接命中索引。

**范围边界**：
- 本 Sprint 只做"加列 + 加索引"；
- `get_active_filter(db, table, project_id, year)` 签名 **保持不变**；
- 40+ 处调用点补 `current_user` 参数是 Sprint 7.6/7.7 单独任务，本迁移不触碰服务/路由代码。

**回滚策略**：downgrade 先 drop index，再 drop column；default 值由 server_default 落在
PG 元数据上，老行被自动填 'default'，无需数据迁移步骤。

Revision ID: view_refactor_tenant_id_20260518
Revises: view_refactor_activation_record_20260523
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "view_refactor_tenant_id_20260518"
down_revision = "view_refactor_activation_record_20260523"
branch_labels = None
depends_on = None


# 五张需要 tenant 维度的表（4 张业务表 + 数据集 metadata 表）
_TARGET_TABLES: tuple[str, ...] = (
    "tb_balance",
    "tb_ledger",
    "tb_aux_balance",
    "tb_aux_ledger",
    "ledger_datasets",
)


def _index_name(table: str) -> str:
    return f"idx_{table}_tenant_project_year"


def upgrade() -> None:
    for table in _TARGET_TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                sa.String(length=64),
                nullable=False,
                server_default="default",
            ),
        )
        op.create_index(
            _index_name(table),
            table,
            ["tenant_id", "project_id", "year"],
        )


def downgrade() -> None:
    # 先 drop index 再 drop column：PG 禁止删除被索引引用的列
    for table in _TARGET_TABLES:
        op.drop_index(_index_name(table), table_name=table)
        op.drop_column(table, "tenant_id")
