"""符号约定过渡期检测 — 消费前守卫。

Task 7.1 / 需求 10：下游消费路径（trial_balance / data_quality）调用本模块，
在取数前检测该 project+year 是否存在旧约定（v1/NULL）残留数据集。

检测到 v1 残留 → 返回结构化 warning（不阻断取数，仅提示"需先运行符号迁移"）。
检测粒度：dataset 级（读四表 sign_convention_version，SELECT EXISTS LIMIT 1 级别轻量）。

设计选择（design 推荐）：消费前要求迁移——检测到 v1 则提示，不阻断但返回 warning。
下游读取行为不变（仍按 audited_amount 取数），warning 仅提示用户数据可能不准确。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_import.sign_convention_types import (
    CURRENT_SIGN_CONVENTION,
)


@dataclass
class SignConventionReadinessResult:
    """检测结果。

    Attributes:
        ready: True 表示全部为 v2（无 v1 残留），可放心消费。
        has_legacy: True 表示存在 v1/NULL 残留。
        warning: 结构化提示消息（has_legacy=True 时非空），可被前端消费为 banner/弹窗。
    """

    ready: bool
    has_legacy: bool
    warning: str | None = None


async def check_sign_convention_readiness(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> SignConventionReadinessResult:
    """检测指定 project+year 是否存在 v1 残留（sign_convention_version != v2 含 NULL/v1）。

    检测逻辑：
    - 对 tb_balance 表做 SELECT EXISTS(...LIMIT 1)，查是否有
      sign_convention_version IS NULL 或 sign_convention_version != CURRENT（v2）的记录。
    - 仅查 is_deleted=false 的活跃行。
    - 若表不存在（to_regclass 探测）则视为无残留（无数据=ready）。

    返回 SignConventionReadinessResult，has_legacy=True 时附带 warning 消息。
    """
    # PG 运维铁律：先探测表是否存在
    table_check = await db.execute(
        sa.text("SELECT to_regclass('public.tb_balance')")
    )
    if table_check.scalar() is None:
        return SignConventionReadinessResult(ready=True, has_legacy=False)

    # 轻量 SELECT EXISTS：只看是否存在至少一条非 v2 记录
    legacy_exists_sql = sa.text("""
        SELECT EXISTS(
            SELECT 1 FROM tb_balance
            WHERE project_id = :pid
              AND year = :yr
              AND is_deleted = false
              AND (sign_convention_version IS NULL
                   OR sign_convention_version != :current_version)
            LIMIT 1
        )
    """)
    result = await db.execute(
        legacy_exists_sql,
        {"pid": str(project_id), "yr": year, "current_version": CURRENT_SIGN_CONVENTION},
    )
    has_legacy = result.scalar() or False

    if has_legacy:
        return SignConventionReadinessResult(
            ready=False,
            has_legacy=True,
            warning=(
                "当前项目年度存在旧符号约定（v1）数据，金额符号可能不准确。"
                "建议先运行符号迁移脚本（migrate_sign_convention_v2.py）将数据统一为新约定后再使用。"
            ),
        )

    return SignConventionReadinessResult(ready=True, has_legacy=False)
