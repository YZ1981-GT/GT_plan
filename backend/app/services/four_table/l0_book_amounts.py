"""L0-1 函证结果汇总表「一、函证情况」矩阵的账面金额取数（按品种）。

源模板 `函证结果汇总表L0-1` 的 `E30`/`F30`「本期（期末）账面金额」是**手填行**
（该行无公式，是矩阵 8 指标里唯一的录入位），本模块把它做成「自动取数 + 手工覆盖」。

L0 恰 **2 个品种**（源 `E29 长期应付款` / `F29 应付债券`），无 `……` 可扩位。

🔴 **复用 `l_cycle_specs.py`，不新写科目定位**

`L5_SPEC`（长期应付款 `BS-064` / 兜底 `2701`）与 `L4_SPEC`（应付债券 `BS-062` /
兜底 `2502`）已存在且经 `report_config` DB 对账，L0-1 的两个品种恰好一一对应。
新写一份等于制造双真源，且要重复踩「一码两义」「client chart 优先」那些坑。

🔴 **为什么不能照抄 F0 的口径**

F0 的 `F0_BOOK_AMOUNT_SOURCES` 从 F1/F3/F4 的 render-config
`project_context.tb_amount` 取账面额。但 L1~L8 的 render 并不统一下发该键
（同 H 循环的情形），照抄必得 ``undefined``（dead output）。故 L0 在后端自解。

🔴 **`2702 未确认融资费用` 不扣减**（2026-08-05 DB 实证）

- 它是**独立一级科目**，不是 `2701` 的子科目 —— `account_chart` 里 `2701` 的子科目
  只有 `.01 应付融资租赁款` / `.02 应付长期保证金` / `.03 应付长期借款` /
  `.99 一年内到期的长期应付款`；未确认融资费用挂在独立码 `2702`（其中 1 个项目
  client 侧名为「长期应付款未确认融资费用」但码仍是 2702）
  ⇒ `LIKE '2701%'` **扫不到它**，「父族聚合已净掉」的说法不成立。
- 且 `BS-064 = TB('2701','期末余额')` 本身**不减** 2702，与 H9 租赁负债
  `BS-063 = TB('2601')-TB('2602')` 的口径**不同** —— 属 `report_config` 既有口径
  差异，不在本 spec 半径。本模块按 `BS-064` 口径实现（`net_of_slots` 为空），
  并在溯源里如实标注。

**账面金额口径** = 该品种原值槽的叶子聚合（`absolute=True` 只作用于**聚合结果**）。
`resolve_leaf_totals` 两种符号约定都算、取与**父科目额**勾稽成立的那一种；
逐行 `abs()` 会破坏「叶子和 == 父额」勾稽（`2502.02 利息调整` 是借方性质，
逐行 abs 会把它加成正数）。

spec: .kiro/specs/l0-confirmation-source-alignment/
      Requirements 3.3 / 3.4 / 10.4 · Property 11 / 12
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from .l_cycle_specs import L4_SPEC, L5_SPEC
from .leaf_aggregation import resolve_leaf_totals, to_leaf_rows
from .semantic_account_resolver import (
    ResolverContext,
    SemanticAccountSpec,
    resolve_semantic_accounts,
)

logger = logging.getLogger(__name__)


# ─── 品种 → L 循环语义规格 ───────────────────────────────────────────────────


@dataclass(frozen=True)
class L0CategorySpec:
    """L0-1 矩阵一个品种 → L 循环语义规格的映射。"""

    #: 品种名 —— 🔴 必须与源模板 `E29`/`F29` 字面**逐字一致**（它同时是上区
    #: `E 账户/交易` 列 SUMIF 的 criteria，也是手工覆盖键的品种段）
    category: str
    #: 数据来源循环（仅供溯源展示，不参与查询）
    source_wp_code: str
    #: 复用该循环 `l_cycle_specs.py` 的语义规格
    spec: SemanticAccountSpec
    #: 原值槽键
    gross_slot: str = "gross"
    #: 需扣减的备抵槽键（L0 两品种均为空 —— 见模块 docstring 的 2702 说明）
    net_of_slots: tuple[str, ...] = ()
    #: 口径说明（溯源面板展示）
    formula_hint: str = ""
    #: 附加提示（溯源面板展示，如既有口径差异的如实标注）
    notes: tuple[str, ...] = ()


#: 🔴 品种名逐字取源模板 `函证结果汇总表L0-1!E29`/`F29`，**固定 2 个无可扩位**。
L0_MATRIX_CATEGORY_SPECS: tuple[L0CategorySpec, ...] = (
    L0CategorySpec(
        category="长期应付款",
        source_wp_code="L5",
        spec=L5_SPEC,
        formula_hint="长期应付款（BS-064 = TB('2701','期末余额')，叶子聚合口径）",
        notes=(
            "未确认融资费用（2702）是**独立一级科目**而非 2701 子科目，"
            "且报表行 BS-064 口径不扣减它 —— 与 H9 租赁负债 BS-063 减未确认融资费用的"
            "口径不同，属 report_config 既有口径差异，本底稿按 BS-064 取数。",
            "子科目「2701.99 一年内到期的长期应付款」会计上应重分类至 BS-052，"
            "但 BS-064 = TB('2701') 会将其计入 —— 属 report_config 既有重分类派生行议题，"
            "如需拆分请在审定表处理。",
        ),
    ),
    L0CategorySpec(
        category="应付债券",
        source_wp_code="L4",
        spec=L4_SPEC,
        formula_hint="应付债券（BS-062 = TB('2502','期末余额')，叶子聚合口径）",
        notes=(
            "客户常按「面值 / 利息调整 / 应计利息」设子科目，其中利息调整可能是借方性质；"
            "叶子聚合按 closing_direction 带符号求和（与父额勾稽自校验），"
            "不做逐行取绝对值。",
        ),
    ),
)

L0_CATEGORY_BY_NAME: dict[str, L0CategorySpec] = {
    c.category: c for c in L0_MATRIX_CATEGORY_SPECS
}


# ─── 返回结构 ────────────────────────────────────────────────────────────────


@dataclass
class L0BookAmountResult:
    """按品种的账面金额与溯源信息。

    Attributes:
        amounts: 品种 → 账面金额。``None`` = 本项目无此科目（**不是 0**）。
        source_codes: 品种 → 溯源 dict（报表行 / 解析出的码 / resolved_from / 口径）。
        conflicts: `report_config` 与项目科目表不一致的告警（跨品种汇总）。
    """

    amounts: dict[str, float | None] = field(default_factory=dict)
    source_codes: dict[str, dict] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "amounts": self.amounts,
            "source_codes": self.source_codes,
            "conflicts": self.conflicts,
        }


# ─── 主函数 ──────────────────────────────────────────────────────────────────


async def resolve_l0_book_amounts(
    ctx: ResolverContext,
    categories: Sequence[str] | None = None,
) -> L0BookAmountResult:
    """按品种解析 L0-1 矩阵的账面金额。

    Args:
        ctx: 只需 ``db`` / ``project_id`` / ``year``。
        categories: 限定品种（缺省 = 全部 2 个）。不在
            :data:`L0_MATRIX_CATEGORY_SPECS` 里的品种**不产出该键**，
            调用方据此渲染「-」（宁缺勿造）。

    Returns:
        :class:`L0BookAmountResult`

    失效处置（Requirement 3.4 / Error Handling）：
        - 槽 ``found=False``（本项目无此科目）→ ``amounts[品种] = None``
        - 单品种解析抛异常 → 该品种 ``None`` + warning，另一品种照常返回
        - ``tb_balance`` 整体查询失败 → 全部品种 ``None``（**不是 0**）
    """
    wanted = list(categories) if categories else [c.category for c in L0_MATRIX_CATEGORY_SPECS]
    specs = [L0_CATEGORY_BY_NAME[name] for name in wanted if name in L0_CATEGORY_BY_NAME]

    result = L0BookAmountResult()
    if not specs:
        return result

    # 一次查询服务两个品种（共用同一份 tb_balance 行集，**含父科目行**）
    all_rows = None
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        rows = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        # 🔴 `to_leaf_rows` / `resolve_leaf_totals` 都是**同步纯函数**，
        #    `await` 它们会抛 TypeError 并被 except 吞成 warning（G6 曾因此让
        #    审定表 TB seed 恒空）。改这里前先 `inspect.signature` 实证。
        #
        # 🔴🔴 这里**不能**先 `select_leaves()` —— `resolve_leaf_totals` 要拿
        #    **父科目行本身**当符号约定的判定依据（父行是参照物，预先剔除就退化成
        #    「原样求和」）。L0 的现实反例：`2502` 家族的 `.02 利息调整` 是借方性质，
        #    原样求和会把它加成正数而非抵减。
        all_rows = to_leaf_rows(list(rows.fetchall()))
    except Exception as e:  # noqa: BLE001
        logger.warning("L0 book amounts: tb_balance fetch failed: %s", e)

    for cat in specs:
        try:
            amount, source = await _resolve_one(ctx, cat, all_rows)
        except Exception as e:  # noqa: BLE001
            logger.warning("L0 book amounts: category %s failed: %s", cat.category, e)
            amount, source = None, _absent_source(cat, reason="解析失败")
        result.amounts[cat.category] = amount
        result.source_codes[cat.category] = source
        for c in source.get("conflicts") or []:
            if c not in result.conflicts:
                result.conflicts.append(c)

    return result


def _sum_family(all_rows, codes: Sequence[str]) -> tuple[float, dict[str, float]]:
    """按科目族逐个走 `resolve_leaf_totals`（符号约定自校验）求和。

    Returns:
        ``(期末合计, {原始码: 与父额的勾稽差额})``。差额供溯源面板渲染
        「叶子和 == 父额」证据（平台铁律：`parent_check` 是审计价值不是调试信息）。
    """
    total = 0.0
    diffs: dict[str, float] = {}
    for code in codes:
        totals = resolve_leaf_totals(all_rows, code, absolute=True)
        total += float(totals.closing or 0.0)
        diffs[str(code)] = round(float((totals.diff or {}).get("closing") or 0.0), 2)
    return total, diffs


async def _resolve_one(
    ctx: ResolverContext,
    cat: L0CategorySpec,
    all_rows,
) -> tuple[float | None, dict]:
    """解析单个品种。返回 ``(账面金额|None, 溯源 dict)``。"""
    accounts = await resolve_semantic_accounts(ctx, cat.spec)
    gross = accounts.slots.get(cat.gross_slot)

    source: dict = {
        "category": cat.category,
        "source_wp_code": cat.source_wp_code,
        "row_code": cat.spec.row_code,
        "formula_hint": cat.formula_hint,
        "notes": list(cat.notes),
        "gross": list(gross.codes) if gross else [],
        "gross_standard": list(gross.standard_codes) if gross else [],
        "resolved_from": gross.resolved_from if gross else "none",
        "found": bool(gross and gross.found),
        "net_of": [],
        "net_of_slots": list(cat.net_of_slots),
        "conflicts": list(accounts.conflicts or []),
        "chart_available": accounts.chart_available,
    }

    if gross is None or not gross.found:
        # 「本项目无此科目」—— 返 None 而不是 0（宁缺勿造，Requirement 3.4）
        source["absent_reason"] = "本项目科目表无该科目"
        return None, source

    if all_rows is None:
        source["absent_reason"] = "四表数据不可用"
        return None, source

    book, gross_diffs = _sum_family(all_rows, gross.codes)
    parent_check: dict[str, float] = dict(gross_diffs)

    # L0 两品种的 net_of_slots 均为空；保留该分支使结构与 H0 同构，
    # 将来若 report_config 口径改为扣减未确认融资费用，只需声明槽即可。
    for slot_key in cat.net_of_slots:
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        # 🔴 备抵科目若是原值科目族的**子科目**，父族聚合已按方向净掉 → 再减即双算。
        own = [
            c
            for c in slot.codes
            if not any(str(c) == g or str(c).startswith(str(g) + ".") for g in gross.codes)
        ]
        if not own:
            source.setdefault("net_of_skipped", []).extend(list(slot.codes))
            continue
        source["net_of"].extend(own)
        sub, sub_diffs = _sum_family(all_rows, own)
        parent_check.update(sub_diffs)
        book -= sub

    source["parent_check"] = parent_check
    return round(book, 2), source


def _absent_source(cat: L0CategorySpec, *, reason: str) -> dict:
    return {
        "category": cat.category,
        "source_wp_code": cat.source_wp_code,
        "row_code": cat.spec.row_code,
        "formula_hint": cat.formula_hint,
        "notes": list(cat.notes),
        "gross": [],
        "gross_standard": [],
        "resolved_from": "none",
        "found": False,
        "net_of": [],
        "net_of_slots": list(cat.net_of_slots),
        "conflicts": [],
        "chart_available": None,
        "absent_reason": reason,
        "parent_check": {},
    }


__all__ = [
    "L0CategorySpec",
    "L0BookAmountResult",
    "L0_MATRIX_CATEGORY_SPECS",
    "L0_CATEGORY_BY_NAME",
    "resolve_l0_book_amounts",
    # re-export：调用方（wp_render_config_helpers 的注入器）一次 import 即可拿到上下文类型
    "ResolverContext",
]
