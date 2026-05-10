"""F42 / Sprint 7.10: import_jobs.force_submit 门控字段。

背景（requirements F42 / design D30 / tasks 7.9-7.11 + 10.42-10.44）：
- detect 阶段新增规则 ``EMPTY_LEDGER_WARNING``（total_rows < 10）和
  ``SUSPICIOUS_DATASET_SIZE``（相对同 project 历史均值比 < 0.1 或 > 10）。
- /submit 端点在识别出这两类警告且调用方未显式 ``force_submit=True`` 时
  返回 400 + ``SCALE_WARNING_BLOCKED``，要求用户在前端点"强制继续"后重发。
- ``force_submit`` 持久化到 ``ImportJob``，保留"用户明确覆盖了规模警告"
  的审计轨迹（审计/回溯时可区分正常作业与强制作业）。

**范围边界**：
- 本迁移只做加列（``BOOLEAN NOT NULL DEFAULT false``），默认所有历史 job
  视为 ``force_submit=false``（即它们没经过规模门控，历史兼容）。
- server_default='false' 保证新旧环境所有已有行自动填 false，无需数据迁移。
- 不加索引（查询场景几乎不按 force_submit 过滤，仅审计穿透时偶查）。

**回滚策略**：downgrade 直接 drop_column。由于字段无索引、无 FK、无依赖视图，
删除安全且瞬时完成；若 Sprint 7 之后有依赖 ``force_submit`` 的代码路径上线，
回退前需配套注释处代码或 feature flag 关闭。

Revision ID: view_refactor_force_submit_20260524
Revises: view_refactor_tenant_id_20260518
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "view_refactor_force_submit_20260524"
down_revision = "view_refactor_tenant_id_20260518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column(
            "force_submit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "force_submit")
