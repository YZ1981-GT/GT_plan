"""H0-1 函证结果汇总表「一、函证情况」矩阵的账面金额取数（按品种）。

源模板 `函证结果汇总表H0-1` R30「本期（期末）账面金额」是**手填行**，本模块把它
做成「自动取数 + 手工覆盖」。

🔴 **为什么不能照抄 F0 的口径**

F0 的 `F0_BOOK_AMOUNT_SOURCES` 从 F1/F3/F4 的 render-config
`project_context.tb_amount` 取账面额。但实测 H1~H10 **十个 render 策略里
`tb_amount` 零命中** —— H 循环下发的是 `html_data.tb_values`（按槽前缀键，如
`cost_unadjusted`/`rou_asset_audited`）+ `tb_source_codes`。照抄 F0 的读法
必得 ``undefined``（又一个 dead output）。故 H0 自己在后端按品种解析。

🔴 **为什么必须走语义定位而不是按标准科目码硬查**

H 循环实证（h-cycle-four-table-extraction-and-account-mapping）：
- H8 使用权资产：某客户实际用 ``1651/1652``（标准码 1641/1642）
- H9 租赁负债：某客户实际用 ``2651``（标准码 2601）
→ 按标准码硬查这两个品种在该项目会**取空**。本模块一律复用各循环已建的
``h{n}_account_scope.py`` 语义规格，标准码只作兜底且只写在 ``fallback`` 里。

**账面金额口径** = 该品种原值槽 − 各备抵槽（`absolute=True` 归一后相减）。
备抵在 ``tb_balance`` 里有两种符号约定（正/负并存），逐行 abs 会破坏
「叶子和 == 父额」勾稽，故 ``absolute=True`` 只作用于**聚合结果**。

spec: .kiro/specs/h0-confirmation-source-fidelity-and-linkage/
      Requirements 3.1~3.9 / Property 8 / Property 9
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from .h_cycle_specs import (
    H1_ACCOUNT_SPEC,
    H2_ACCOUNT_SPEC,
    H3_ACCOUNT_SPEC,
    H4_ACCOUNT_SPEC,
    H5_ACCOUNT_SPEC,
    H6_ACCOUNT_SPEC,
    H7_ACCOUNT_SPEC,
    H8_ACCOUNT_SPEC,
    H9_ACCOUNT_SPEC,
)
from .leaf_aggregation import resolve_leaf_totals, to_leaf_rows
from .semantic_account_resolver import (
    ResolverContext,
    SemanticAccountSpec,
    resolve_semantic_accounts,
)

logger = logging.getLogger(__name__)


# ─── 品种 → H 循环语义规格 ───────────────────────────────────────────────────


@dataclass(frozen=True)
class H0CategorySpec:
    """H0-1 矩阵一个品种 → H 循环语义规格的映射。"""

    #: 品种名（须与 `system_dicts.confirmation_account_type` 标签逐字一致）
    category: str
    #: 数据来源循环（仅供溯源展示，不参与查询）
    source_wp_code: str
    #: 复用该循环 `h{n}_account_scope.py` 的语义规格
    spec: SemanticAccountSpec
    #: 原值槽键
    gross_slot: str
    #: 需扣减的备抵槽键（空 tuple = 账面金额即原值）
    net_of_slots: tuple[str, ...] = ()
    #: 口径说明（溯源面板展示）
    formula_hint: str = ""


#: 🔴 品种名逐字取 `wp_system_map.json` 的「固定资产循环」accounts，
#: 「资产处置损益」(H10) 是损益类不函证故不在列。
H0_MATRIX_CATEGORY_SPECS: tuple[H0CategorySpec, ...] = (
    H0CategorySpec(
        category="固定资产",
        source_wp_code="H1",
        spec=H1_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("accum_dep", "impairment"),
        formula_hint="固定资产原值 − 累计折旧 − 减值准备",
    ),
    H0CategorySpec(
        category="在建工程",
        source_wp_code="H2",
        spec=H2_ACCOUNT_SPEC,
        gross_slot="gross",
        # 🔴 不含 H2 的 `eng_mat` 槽 —— 那是工程物资，自成一个品种（否则双算）
        net_of_slots=("impairment",),
        formula_hint="在建工程 − 在建工程减值准备",
    ),
    H0CategorySpec(
        category="投资性房地产",
        source_wp_code="H3",
        spec=H3_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("accum_dep", "accum_amort", "impairment"),
        formula_hint="投资性房地产原值 − 累计折旧 − 累计摊销 − 减值准备",
    ),
    H0CategorySpec(
        category="工程物资",
        source_wp_code="H4",
        spec=H4_ACCOUNT_SPEC,
        gross_slot="gross",
        # 🔴 不含 H4 的 `cip` 槽 —— 那是在建工程（核对用），自成一个品种
        net_of_slots=(),
        formula_hint="工程物资",
    ),
    H0CategorySpec(
        category="油气资产",
        source_wp_code="H5",
        spec=H5_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("accum_depletion", "impairment"),
        formula_hint="油气资产原值 − 累计折耗 − 减值准备",
    ),
    H0CategorySpec(
        category="固定资产清理",
        source_wp_code="H6",
        spec=H6_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=(),
        formula_hint="固定资产清理",
    ),
    H0CategorySpec(
        category="生产性生物资产",
        source_wp_code="H7",
        spec=H7_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("accum_dep", "impairment"),
        formula_hint="生产性生物资产原值 − 累计折旧 − 减值准备",
    ),
    H0CategorySpec(
        category="使用权资产",
        source_wp_code="H8",
        spec=H8_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("accum_dep", "impairment"),
        formula_hint="使用权资产原值 − 累计折旧 − 减值准备",
    ),
    H0CategorySpec(
        category="租赁负债",
        source_wp_code="H9",
        spec=H9_ACCOUNT_SPEC,
        gross_slot="gross",
        net_of_slots=("unearned_finance",),
        formula_hint="租赁负债 − 未确认融资费用",
    ),
)

H0_CATEGORY_BY_NAME: dict[str, H0CategorySpec] = {c.category: c for c in H0_MATRIX_CATEGORY_SPECS}


# ─── 返回结构 ────────────────────────────────────────────────────────────────


@dataclass
class H0BookAmountResult:
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


async def resolve_h0_book_amounts(
    ctx: ResolverContext,
    categories: Sequence[str] | None = None,
) -> H0BookAmountResult:
    """按品种解析 H0-1 矩阵的账面金额。

    Args:
        ctx: 只需 ``db`` / ``project_id`` / ``year``。
        categories: 限定品种（缺省 = 全部 9 个）。不在
            :data:`H0_MATRIX_CATEGORY_SPECS` 里的品种**不产出该键**，
            调用方据此渲染「-」（宁缺勿造）。

    Returns:
        :class:`H0BookAmountResult`

    失效处置（Requirement 3.8 / Error Handling）：
        - 槽 ``found=False``（本项目无此科目）→ ``amounts[品种] = None``
        - 单品种解析抛异常 → 该品种 ``None`` + warning，其余品种照常返回
        - ``tb_balance`` 整体查询失败 → 全部品种 ``None``（不是 0）
    """
    wanted = list(categories) if categories else [c.category for c in H0_MATRIX_CATEGORY_SPECS]
    specs = [H0_CATEGORY_BY_NAME[name] for name in wanted if name in H0_CATEGORY_BY_NAME]

    result = H0BookAmountResult()
    if not specs:
        return result

    # 一次查询服务全部品种（9 个循环共用同一份 tb_balance 行集，含父科目行）
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
        # 🔴 to_leaf_rows / resolve_leaf_totals 都是**同步纯函数**，
        #    `await` 它们会抛 TypeError 并被 except 吞成 warning（G6 曾因此让
        #    审定表 TB seed 恒空）。改这里前先 `inspect.signature` 实证。
        #
        # 🔴🔴 这里**不能**先 `select_leaves()` —— `resolve_leaf_totals` 要拿
        #    **父科目行本身**当符号约定的判定依据（父行是参照物，预先剔除就退化成
        #    「原样求和」）。2026-08-04 实测：`c8621493` 的 `2651 租赁负债` 家族
        #    叶子 `2651.01 租赁付款额 98,176.48(credit)` 与 `2651.02 未确认融资费用
        #    3,956.64(debit)` 方向相反，原样求和得 102,133.12，而父额是 94,219.84
        #    —— 前者把借方性质的未确认融资费用**加**了进去（应为减）。
        all_rows = to_leaf_rows(list(rows.fetchall()))
    except Exception as e:  # noqa: BLE001
        logger.warning("H0 book amounts: tb_balance fetch failed: %s", e)

    for cat in specs:
        try:
            amount, source = await _resolve_one(ctx, cat, all_rows)
        except Exception as e:  # noqa: BLE001
            logger.warning("H0 book amounts: category %s failed: %s", cat.category, e)
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
    cat: H0CategorySpec,
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
        # 「本项目无此科目」—— 返 None 而不是 0（宁缺勿造，Requirement 3.8）
        source["absent_reason"] = "本项目科目表无该科目"
        return None, source

    if all_rows is None:
        source["absent_reason"] = "四表数据不可用"
        return None, source

    # 🔴 `resolve_leaf_totals` 两种符号约定都算、取与**父科目额**勾稽成立的那一种；
    #    `absolute=True` 只作用于聚合结果（逐行 abs 会破坏「叶子和 == 父额」勾稽，
    #    且会把借方性质的 contra 子科目加成正数 —— `2651.02 未确认融资费用` 即如此）。
    book, gross_diffs = _sum_family(all_rows, gross.codes)
    parent_check: dict[str, float] = dict(gross_diffs)

    for slot_key in cat.net_of_slots:
        slot = accounts.slots.get(slot_key)
        if slot is None or not slot.found:
            continue
        # 🔴 备抵科目若是原值科目族的**子科目**（如 `2651.02` 在 `2651` 下），
        #    父族聚合已经把它按方向净掉了 → 再减一次就是双算。
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


def _absent_source(cat: H0CategorySpec, *, reason: str) -> dict:
    return {
        "category": cat.category,
        "source_wp_code": cat.source_wp_code,
        "row_code": cat.spec.row_code,
        "formula_hint": cat.formula_hint,
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
    "H0CategorySpec",
    "H0BookAmountResult",
    "H0_MATRIX_CATEGORY_SPECS",
    "H0_CATEGORY_BY_NAME",
    "resolve_h0_book_amounts",
    # re-export：调用方（wp_render_config_helpers 的注入器）一次 import 即可拿到上下文类型
    "ResolverContext",
]
