"""adjustment_amount_source.py — 调整分录取数单一权威源.

spec: adj-formula-repair-and-approval-gate-wiring · 设计 §三 组件 1
与 formula_management/four_table_source.py 同构——后者是四表库取数的单一入口。

本模块提供：
- normalize_adj_type: 第二参归一（兼容 aje_net/AJE/审计调整 等全部既有写法）
- adj_net: 单点取数函数（三处调用点的唯一查询实现）

口径矩阵（三者不同是刻意的，见 ADR-ADJ-002/003）：
| 用途                          | review_status | origin        |
|-------------------------------|---------------|---------------|
| TB 调整列（参与审定数计算）    | 仅 approved   | 排除 workpaper |
| ADJ() 底稿呈现               | 仅 approved   | 不排除         |
| 交叉核对                      | 与 ADJ() 一致 | 不排除         |

差异通过 include_statuses / exclude_origins **显式参数**体现在调用点，
不再靠注释声称一致而实际不同。

ADR-ADJ-001: 科目列统一走 adjustment_entries.standard_account_code + JOIN adjustments
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 类型归一表（模块级常量）
# ---------------------------------------------------------------------------
# key = raw 字面量的 lower()，value = 归一后的标准值
_ADJ_TYPE_NORMALIZE: dict[str, str] = {
    # AJE 族
    "aje_net": "aje",
    "aje": "aje",
    "审计调整": "aje",
    # RJE 族
    "rje_net": "rje",
    "rje": "rje",
    "重分类": "rje",
}

# ADR-ADJ-003: 试算表调整列默认只纳入 approved
DEFAULT_INCLUDE_STATUSES: frozenset[str] = frozenset({"approved"})


def normalize_adj_type(raw: str) -> str:
    """将调整类型字面量归一到 ``"aje"`` 或 ``"rje"``。

    同时兼容既有写法：aje_net / AJE / 审计调整 / rje_net / RJE / 重分类。
    不可归一时 **raise ValueError**，禁止静默省略 adjustment_type 过滤。

    >>> normalize_adj_type("aje_net")
    'aje'
    >>> normalize_adj_type("RJE")
    'rje'
    >>> normalize_adj_type("审计调整")
    'aje'
    """
    if not raw or not raw.strip():
        raise ValueError(f"调整类型为空，无法归一: {raw!r}")
    key = raw.strip().lower()
    result = _ADJ_TYPE_NORMALIZE.get(key)
    if result is None:
        raise ValueError(
            f"无法将调整类型 {raw!r} 归一到 aje/rje。"
            f"合法值: {sorted(_ADJ_TYPE_NORMALIZE.keys())}"
        )
    return result


# ---------------------------------------------------------------------------
# 合法字面量白名单（供 CI 守卫使用）
# ---------------------------------------------------------------------------
VALID_ADJ_TYPE_LITERALS: frozenset[str] = frozenset(_ADJ_TYPE_NORMALIZE.keys())


async def adj_net(
    db: "AsyncSession",
    *,
    project_id: UUID,
    year: int,
    account_code: str,
    adj_type: str,
    include_statuses: frozenset[str] | None = None,
    exclude_origins: frozenset[str] = frozenset(),
) -> Decimal:
    """从调整分录表取指定科目的 AJE/RJE 净额（单点取数，三处调用点的唯一实现）。

    ADR-ADJ-001: 科目列走 adjustment_entries.standard_account_code + JOIN adjustments
    （origin / review_status 只在主表 adjustments）。

    符号归一：按 direction_resolver 将 SUM(debit-credit) 归一到科目自然方向
    （贷方类取反），与 trial_balance.aje_adjustment/rje_adjustment 口径一致。

    Args:
        db: 异步 DB session（只读，只 flush 不 commit）
        project_id: 项目 ID
        year: 会计年度
        account_code: 标准科目编码
        adj_type: 归一前的原始字面量（内部调 normalize_adj_type）
        include_statuses: 纳入的 review_status 集合。
            None = 使用 DEFAULT_INCLUDE_STATUSES（仅 approved，ADR-ADJ-003）。
            传空 frozenset() = 不过滤（纳入所有状态）。
        exclude_origins: 排除的 origin 集合。
            如 frozenset({"workpaper"})（TB 列传此值防 V124 双计）。
            空集 = 不排除（公式取数口径，ADR-ADJ-002）。

    Returns:
        按科目自然方向归一后的净额 Decimal（无数据返回 Decimal("0")）。
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    from app.services.ledger_import.direction_resolver import resolve_account_direction

    normalized_type = normalize_adj_type(adj_type)

    # 有效的 statuses 集合（None → 默认口径）
    statuses = include_statuses if include_statuses is not None else DEFAULT_INCLUDE_STATUSES

    # 构建查询：ADR-ADJ-001 统一走 entry 表 + JOIN 主表
    q = sa.select(
        sa.func.coalesce(
            sa.func.sum(AdjustmentEntry.debit_amount - AdjustmentEntry.credit_amount), 0
        ).label("net"),
        sa.func.max(AdjustmentEntry.account_name).label("account_name"),
    ).join(
        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.is_deleted == sa.false(),
        AdjustmentEntry.standard_account_code == account_code,
        Adjustment.adjustment_type == normalized_type,
    )

    # review_status 过滤（非空集才加条件）
    if statuses:
        q = q.where(Adjustment.review_status.in_(list(statuses)))

    # origin 排除（非空集才加条件）
    if exclude_origins:
        for origin in exclude_origins:
            q = q.where(
                sa.or_(Adjustment.origin.is_(None), Adjustment.origin != origin)
            )

    result = await db.execute(q)
    row = result.first()

    if row is None or row[0] is None:
        return Decimal("0")

    raw_net = Decimal(str(row[0]))
    account_name = (row[1] if len(row) > 1 else None) or ""

    # 符号归一：贷方类取反
    direction, _src = resolve_account_direction(account_code, account_name)
    sign = Decimal("-1") if direction == "credit" else Decimal("1")
    result = sign * raw_net

    # C1 实测修正：贷方类无数据时 `-1 * Decimal("0")` 得 **Decimal("-0")**。
    # 虽然 `-0 == 0` 为 True，但它会以 "-0" 形态流向前端展示 / Excel 写格 /
    # 字符串比较，属可见的脏值。归零为规范的 Decimal("0")。
    if result.is_zero():
        return Decimal("0")
    return result
