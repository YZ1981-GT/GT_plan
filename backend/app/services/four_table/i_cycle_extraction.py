"""I 类循环四表取数编排（六个 render 策略的唯一入口）。

一次查询 `tb_balance` + 一次查询 `trial_balance`，再用纯函数
（:mod:`.i_cycle_prefill`）产出 render 需要的全部字段。

**为什么要有这一层**

改造前六个策略各写一份 `_fetch_tb_data`（前缀硬编码 + 父子双计 + 损益类
`debit - credit` 恒为 0），共 6 份方言。收敛到这里后：科目定位归
:mod:`.i_cycle_accounts`、聚合归 :mod:`.leaf_aggregation`、行集归
:mod:`.i_cycle_prefill`，本模块只做 IO 编排。

**`tb_values` 键名保持不变** —— 前端已在读的键（`useI4FormData` 的
``long_term_prepaid_1801_unadjusted``、`useI6FormData` 的 ``unadjusted_debit`` /
``unadjusted_credit``）逐字保留，避免前端连带改动。

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1 / 1.6 / 2.3 / 3.1 / 4.1，Property 1 / 4 / 11
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

from .i1_asset_categories import category_defs_payload, default_category_keys
from .i_cycle_accounts import (
    SEGMENT_AMORTIZATION,
    SEGMENT_COST,
    SEGMENT_EXPENSE,
    SEGMENT_IMPAIRMENT,
    ICycleAccounts,
    resolve_i_cycle_accounts,
)
from .i_cycle_prefill import (
    TOLERANCE,
    build_adjudication_prefill,
    build_parent_check,
    build_tb_values,
    segment_amounts,
)
from .leaf_aggregation import LeafRow, select_leaves, to_leaf_rows

logger = logging.getLogger(__name__)

#: 段键 → `tb_values` 键前缀。**逐字保留改造前的键名**（前端零改动）。
I_CYCLE_TB_KEY_MAP: dict[str, dict[str, str]] = {
    "I1": {
        SEGMENT_COST: "cost_unadjusted",
        SEGMENT_AMORTIZATION: "amort_unadjusted",
        SEGMENT_IMPAIRMENT: "impair_unadjusted",
    },
    "I2": {SEGMENT_COST: "dev_unadjusted"},
    "I3": {
        SEGMENT_COST: "goodwill_unadjusted",
        SEGMENT_IMPAIRMENT: "goodwill_impair_unadjusted",
    },
    "I4": {SEGMENT_COST: "long_term_prepaid_1801_unadjusted"},
    "I5": {SEGMENT_COST: "other_noncurrent_assets_unadjusted"},
    "I6": {SEGMENT_EXPENSE: "rd_expense_unadjusted"},
}

#: 段键 → `tb_values` 审定数键（`trial_balance.audited_amount` 口径）
I_CYCLE_AUDITED_KEY_MAP: dict[str, dict[str, str]] = {
    "I1": {
        SEGMENT_COST: "cost_audited",
        SEGMENT_AMORTIZATION: "amort_audited",
        SEGMENT_IMPAIRMENT: "impair_audited",
    },
    "I2": {SEGMENT_COST: "dev_audited"},
    "I3": {
        SEGMENT_COST: "goodwill_audited",
        SEGMENT_IMPAIRMENT: "goodwill_impair_audited",
    },
    "I4": {SEGMENT_COST: "long_term_prepaid_1801_audited"},
    "I5": {SEGMENT_COST: "other_noncurrent_assets_audited"},
    "I6": {SEGMENT_EXPENSE: "rd_expense_audited"},
}


@dataclass
class ICycleExtraction:
    """一次取数的全部产出。"""

    wp_code: str
    accounts: ICycleAccounts
    all_rows: list[LeafRow] = field(default_factory=list)
    leaves: list[LeafRow] = field(default_factory=list)
    tb_values: dict[str, float] = field(default_factory=dict)
    trial_balance: dict[str, float] = field(default_factory=dict)
    parent_check: dict[str, dict[str, float]] = field(default_factory=dict)
    adjudication_prefill: dict | None = None

    def source_codes_payload(self) -> dict:
        """render 的 `tb_source_codes`（含自检与诊断）。"""
        out = self.accounts.as_dict()
        out["parent_check"] = self.parent_check
        out["parent_check_ok"] = all(
            abs(v.get("diff", 0.0)) <= TOLERANCE for v in self.parent_check.values()
        )
        prefill = self.adjudication_prefill or {}
        out["unmapped"] = list(prefill.get("unmapped") or [])
        if self.wp_code == "I1":
            out["category_defs"] = category_defs_payload()
        return out


async def _fetch_tb_rows(ctx) -> list[LeafRow]:
    """取该项目 active 数据集的全部 `tb_balance` 行（一次查询）。失败返 ``[]``。

    🔴 取**全部行**而非按科目前缀过滤 —— `select_leaves` 要靠兄弟行判定叶子，
    先按前缀过滤会把「父科目的子科目」筛掉从而误判父科目为叶子（父子双计复发）。
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
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
        return to_leaf_rows([dict(r._mapping) for r in result.fetchall()])
    except Exception as e:  # noqa: BLE001 — 取数失败不阻断 render
        logger.warning("I 类取数: tb_balance 查询失败: %s", e)
        return []


async def _fetch_trial_balance(
    ctx, accounts: ICycleAccounts
) -> dict[str, dict[str, float]]:
    """按段取 `trial_balance` 的未审数 / 审定数（标准码口径）。

    🔴 只取**最长前缀命中**的行：`trial_balance` 里父码与细分子码可能并存
    （实证 `1231` 与 `1231-01..05`），`LIKE '1701%'` 全加会父子双计。

    Returns:
        ``{段键: {"unadjusted","audited"}}``；段无科目或查询失败则该段缺席。
    """
    out: dict[str, dict[str, float]] = {}
    wanted: list[str] = []
    for seg in accounts.segments:
        wanted.extend(c for c in seg.standard if c and "~" not in c)
    if not wanted:
        return out
    try:
        tb_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                tb_filter,
                sa.or_(*[TrialBalance.standard_account_code.like(f"{c}%") for c in wanted]),
            )
        )
        rows = [
            (
                str(r.standard_account_code or "").strip(),
                float(r.unadjusted_amount or 0),
                float(r.audited_amount or 0),
            )
            for r in result.fetchall()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("I 类取数: trial_balance 查询失败: %s", e)
        return out

    # 声明码 → 段键（同一码只可能属一个段，`claim_segments` 保证互斥）
    owner: dict[str, str] = {}
    for seg in accounts.segments:
        for c in seg.standard:
            if c and "~" not in c:
                owner.setdefault(c, seg.segment)

    totals: dict[str, list[float]] = {seg.segment: [0.0, 0.0] for seg in accounts.segments}
    for code, u, a in rows:
        # 最长前缀归属：该行只计入命中它的**最长**声明码（防父子双计）
        hits = [c for c in owner if code == c or code.startswith(c)]
        if not hits:
            continue
        seg_key = owner[max(hits, key=len)]
        totals[seg_key][0] += u
        totals[seg_key][1] += a

    for seg in accounts.segments:
        if seg.segment not in totals:
            continue
        unadj, audited = totals[seg.segment]
        if seg.absolute:
            unadj, audited = abs(unadj), abs(audited)
        out[seg.segment] = {"unadjusted": round(unadj, 2), "audited": round(audited, 2)}
    return out


async def load_i_cycle_extraction(ctx, wp_code: str) -> ICycleExtraction:
    """I 类某循环的完整取数（全程 fail-open，异常也返回可用结果）。

    Args:
        ctx: `RenderContext`。
        wp_code: ``'I1'`` ~ ``'I6'``。
    """
    accounts = await resolve_i_cycle_accounts(ctx, wp_code)
    all_rows = await _fetch_tb_rows(ctx)
    leaves = select_leaves(all_rows)

    key_map = I_CYCLE_TB_KEY_MAP.get(accounts.wp_code, {})
    tb_values = build_tb_values(leaves, accounts, key_map)

    tb_rows = await _fetch_trial_balance(ctx, accounts)
    audited_map = I_CYCLE_AUDITED_KEY_MAP.get(accounts.wp_code, {})
    for seg_key, amounts in tb_rows.items():
        prefix = key_map.get(seg_key)
        if prefix:
            tb_values[prefix] = amounts["unadjusted"]
        audited_key = audited_map.get(seg_key)
        if audited_key:
            tb_values[audited_key] = amounts["audited"]

    # 损益段（I6）：本期发生额口径 —— 取 `trial_balance`，回退 `tb_balance` **借方**。
    # 🔴 禁用 `debit - credit`：含年末结转损益分录时两侧恒相等 → 恒为 0。
    for seg in accounts.segments:
        if not seg.occurrence:
            continue
        amt = segment_amounts(leaves, seg)
        tb_values["unadjusted_debit"] = amt["debit"]
        tb_values["unadjusted_credit"] = amt["credit"]
        occurrence = tb_rows.get(seg.segment, {}).get("unadjusted") or amt["debit"]
        tb_values["occurrence_amount"] = round(occurrence, 2)
        tb_values["audited_amount"] = round(
            tb_rows.get(seg.segment, {}).get("audited") or occurrence, 2
        )

    parent_check = build_parent_check(all_rows, leaves, accounts)
    prefill = build_adjudication_prefill(
        leaves, accounts, default_category_keys=default_category_keys()
    )

    return ICycleExtraction(
        wp_code=accounts.wp_code,
        accounts=accounts,
        all_rows=all_rows,
        leaves=leaves,
        tb_values=tb_values,
        trial_balance={
            f"{k}_{f}": v[f] for k, v in tb_rows.items() for f in ("unadjusted", "audited")
        },
        parent_check=parent_check,
        adjudication_prefill=prefill,
    )


__all__ = [
    "ICycleExtraction",
    "I_CYCLE_AUDITED_KEY_MAP",
    "I_CYCLE_TB_KEY_MAP",
    "load_i_cycle_extraction",
]
