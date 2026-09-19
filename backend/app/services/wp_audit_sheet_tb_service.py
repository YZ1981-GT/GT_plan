"""审定表 TB 取数服务 — 从 router 下沉的纯 service 层

提供:
- ``decimal_to_float(value)``：Decimal/numeric → float 安全转换
- ``fetch_audit_sheet_tb_values(audit_rows, db, project_id)``：
  按 audit_rows 各行 account_code 批量查 trial_balance，返回 tb_values 字典

从 ``wp_render_config.py`` 迁入，消除策略文件对 router 的反向 import 依赖。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.project_audit_year import fetch_project_audit_year

logger = logging.getLogger(__name__)


def decimal_to_float(value: Any) -> float | None:
    """Decimal / numeric → float（None → None，转换失败 → None）。

    trial_balance 金额列是 ``Numeric(20, 2)`` → SQLAlchemy 返回 ``Decimal``。
    前端 JSON 消费 float，故统一转换；保留 None 语义（TB 列为空时前端显示「—」）。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def fetch_audit_sheet_tb_values(
    audit_rows: list[dict],
    *,
    db: AsyncSession | None,
    project_id: UUID | None,
) -> dict[str, dict]:
    """按 audit_rows 各行的 ``account_code`` 批量查 ``trial_balance`` 取数（Req 3.1~3.3）。

    返回 ``{ "row-{n}": { opening_unadjusted, current_unadjusted, sys_aje, sys_rje } }``
    （keyed by ``row["id"]``）：

    - ``opening_unadjusted`` ← ``trial_balance.opening_balance``（期初未审数）
    - ``current_unadjusted`` ← ``trial_balance.unadjusted_amount``（本期未审数）
    - ``sys_aje``            ← ``trial_balance.aje_adjustment``（系统汇总 AJE 参考值）
    - ``sys_rje``            ← ``trial_balance.rje_adjustment``（系统汇总 RJE 参考值）

    降级（graceful degradation，对齐 Req 3.3，绝不抛异常阻塞渲染）：
    - ``db`` / ``project_id`` 缺失、无 account_code、年度为空 → 返回 ``{}``；
    - 某行 account_code 无对应 TB 行 → 该行不进 tb_values（前端按缺失即 null/「—」处理）；
    - 任意 SQL / 数据异常 → 记 warning 并返回已构建部分（或 ``{}``）。

    年度来源：``project_audit_year`` 通用规则（audit_year > audit_period_end > audit_period_start）。
    """
    if db is None or project_id is None or not audit_rows:
        return {}

    # 收集去重后的非空 account_code（仅对这些行取数）
    account_codes = sorted(
        {
            str(r["account_code"]).strip()
            for r in audit_rows
            if r.get("account_code")
        }
    )
    if not account_codes:
        return {}

    try:
        year = await fetch_project_audit_year(db, project_id)
        if not year:
            return {}

        # ─── 批量查 trial_balance（参数化 IN，绝不字符串拼接）──────────────
        from app.models.audit_platform_models import TrialBalance

        tb_result = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.opening_balance,
                TrialBalance.unadjusted_amount,
                TrialBalance.aje_adjustment,
                TrialBalance.rje_adjustment,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_by_code = {row[0]: row for row in tb_result.all()}

        # ─── 按 row.id 组装 tb_values（无 TB 行的科目自动省略）────────────
        tb_values: dict[str, dict] = {}
        for r in audit_rows:
            code = r.get("account_code")
            if not code:
                continue
            tb_row = tb_by_code.get(str(code).strip())
            if tb_row is None:
                continue  # 该 account_code 无 TB 行 → 省略（前端按缺失处理）
            tb_values[r["id"]] = {
                "opening_unadjusted": decimal_to_float(tb_row[1]),
                "current_unadjusted": decimal_to_float(tb_row[2]),
                "sys_aje": decimal_to_float(tb_row[3]),
                "sys_rje": decimal_to_float(tb_row[4]),
            }
        return tb_values
    except Exception as e:  # noqa: BLE001 — TB 取数降级不阻塞渲染（Req 3.3）
        logger.warning("审定表 TB 取数失败 project_id=%s: %s", project_id, e)
        return {}


# ─── 兼容性别名（供旧 import 路径平滑迁移）─────────────────────────────────
_decimal_to_float = decimal_to_float
_fetch_audit_sheet_tb_values = fetch_audit_sheet_tb_values
