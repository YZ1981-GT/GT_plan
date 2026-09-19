"""D4 损益类发生额取数口径。

本模块只补共享件覆盖不到的两处，**范围刻意收窄**：

* ``tb_balance`` 侧的符号约定识别与父额勾稽 → 一律走
  :func:`app.services.four_table.resolve_leaf_totals`（该函数对发生额
  ``debit`` / ``credit`` 明确按「无方向语义 → 原样求和」处理，正是损益类所需）。
  **禁在本模块或 D4 其它位置再写一份方向判定。**
* 本模块负责：``tb_ledger`` 的单侧发生额表达式、``trial_balance`` 的符号归一。

spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1~1.6 / Property 3, 4, 6
"""

from __future__ import annotations

from typing import Literal

import sqlalchemy as sa

#: `tb_ledger` 可取的发生额方向
LedgerSide = Literal["credit", "debit"]

#: 损益类科目按性质取哪一侧发生额 —— 收入类取贷方、成本费用类取借方
REVENUE_SIDE: LedgerSide = "credit"
COST_SIDE: LedgerSide = "debit"


def ledger_occurrence_expr(side: LedgerSide, *, table=None):
    """`tb_ledger` **单侧**发生额 SQL 表达式（``COALESCE(col, 0)`` 求和前归一）。

    🔴 **禁用 ``credit_amount - debit_amount`` 净额口径**，两条独立原因各自足以让
    取数恒为 0（DB 只读实证，见 spec Notes）：

    1. **NULL 传播**：`tb_ledger` 只写发生的那一侧，对侧列存 ``NULL``；
       ``credit_amount - debit_amount`` 因此对**每一行**都是 ``NULL`` →
       ``SUM(...)`` 返回 ``NULL`` → 外层 ``COALESCE(..., 0)`` 把它变成 0。
       实测 10 个在册项目中 **8 个** 该表达式返回 ``NULL``。
    2. **年末结转损益**：全年账必有「结转本年利润」分录（借记 6001 冲平），
       故两侧合计恒等 → 即便补了 ``COALESCE``，净额仍结构性为 0。
       实测 **7/10** 项目 ``SUM(credit) == SUM(debit)`` 精确相等
       （如 ``a7fc75e5`` 两侧均为 6,798,732,711.94）。

    单侧口径为什么可用：结转分录只写在**对侧**（收入类结转记借方），
    故取贷方即业务确认额；成本类同理取借方。红字冲销以负数记在同侧，
    天然被正确抵减。

    Args:
        side: ``"credit"``（收入类）或 ``"debit"``（成本费用类）。
        table: SQLAlchemy 表/ORM 类；为 ``None`` 时用 `TbLedger` 模型。

    Returns:
        可直接放进 ``sa.func.sum(...)`` 的列表达式。

    Raises:
        ValueError: ``side`` 不是 ``credit`` / ``debit``。
    """
    if side not in ("credit", "debit"):
        raise ValueError(f"ledger_occurrence_expr: 非法 side={side!r}（只允许 credit/debit）")
    if table is None:
        from app.models.audit_platform_models import TbLedger

        table = TbLedger
    col = getattr(table, f"{side}_amount")
    return sa.func.coalesce(col, 0)


def ledger_occurrence_sql(side: LedgerSide) -> str:
    """同 :func:`ledger_occurrence_expr` 的裸 SQL 片段（供 ``sa.text()`` 场景）。"""
    if side not in ("credit", "debit"):
        raise ValueError(f"ledger_occurrence_sql: 非法 side={side!r}（只允许 credit/debit）")
    return f"COALESCE({side}_amount, 0)"


def normalize_trial_balance_pl(amount) -> float | None:
    """`trial_balance` 损益类金额归一为**正数**口径；``None`` 透传。

    为什么只对 `trial_balance` 做：它没有 ``closing_direction`` 列、行不是
    :class:`~app.services.four_table.LeafRow`，故共享件
    :func:`~app.services.four_table.resolve_leaf_totals` 的「两种约定 + 父额自校验」
    在这里无参照物可用。

    实证：项目 ``df5b8403`` 的 ``6001 主营业务收入`` = **-38,258,743.63**
    （贷方性质以负数存储），不归一会让披露表出现「负收入」。
    同一份数据在多数项目里是正数（如 ``0ec33ac9`` = 895,804,876.83）→
    **两种约定并存，取绝对值是唯一对两者都成立的口径**。

    ``None`` 必须透传（不塌成 0）—— 上期无数据与上期为 0 是两件事，
    前端要能区分并显示「上期无数据」。
    """
    if amount is None:
        return None
    try:
        return abs(float(amount))
    except (TypeError, ValueError):
        return None
