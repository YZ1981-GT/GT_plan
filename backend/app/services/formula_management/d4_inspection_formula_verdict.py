# -*- coding: utf-8 -*-
"""D4-13/14/15/16 检查表公式裁决适配器 — 后端权威执行、前端同定义预览。

Task 2 / Spec: d4-inspection-writeback-formula-io
Requirements: 2.1, 2.2, 2.3, 2.4, 5.2

═══ 目的 ═══

D4-14/15/16 三表的派生列（合计行 SUM、检查比例、一致性判定、差异重算）
在前端由 `useD4FormulaEngine`/`useD4CompletenessCheck`/`D4TabExport.onCellChange`
内联计算。本模块提供 **后端同定义** 的纯函数执行器，通过 `effective_formula` 的
preset 定义保证 expression/refs/params 唯一真源，再经 `FormulaCellVerdict` 裁决
（失败不写值、不转零）。

═══ 设计要点（Req 2.1—2.4）═══

1. 每个公式的 expression/refs 与 `formula_presets_seed.json` 中 `d4_inspection_formula`
   source 的声明完全一致 → Req 2.1「effective definition 统一包含 expression/refs/params
   及 wp/sheet/row/field 稳定 scope」。
2. 后端执行器通过 `resolve_effective_formula` → `verdict_from_evaluation` 裁决 →
   前端预览用同一 preset 定义 → Req 2.2「后端权威 + 前端同定义预览」。
3. 解析/求值失败 → `verdict.outcome='failed'`，`value=None`，**保留原值** →
   Req 2.3「解析失败保留原值」。
4. 双模式 gate：D4-14/15/16 与所有 D4 sheet 共用 `d4:save-items` →
   `ContentMutationService` → `useWorkpaperSyncBridge` 保存链。当该链尚未完全接通时
   （当前 D4 36 sheet 走 last-write-wins `d4:save-items`），本模块只标记
   `dual_mode_status='blocking'`，不宣称已接通（Req 2.3「单模式只能标记阻塞态」）。

═══ 公式同定义映射表 ═══

    Preset target_cell             | 后端纯函数                     | 前端同定义
    ─────────────────────────────────────────────────────────────────────────────
    D4-14-凭证金额合计             | sum_amounts(items, 'voucher')  | calcSubtotal
    D4-14-出库金额合计             | sum_amounts(items, 'delivery') | calcSubtotal
    D4-14-发票金额合计             | sum_amounts(items, 'invoice')  | calcSubtotal
    D4-14-检查比例                 | coverage_rate(...)             | calcCoverageRate
    D4-14-发生一致性判定           | occurrence_diff(...)           | G-X diff
    D4-15-isConsistent             | completeness_diff(...)         | checkConsistency
    D4-15-发货单/发票/凭证金额合计 | sum_completeness(...)          | calcSubtotal
    D4-16-portsDiff                | ports_diff(book, ports)        | onCellChange
    D4-16-taxDiff                  | tax_diff(book, tax)            | onCellChange
    D4-16-*-total                  | sum_diffs(rows, field)         | totalPortsDiff/totalTaxDiff
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.formula_management.d4_formula_cell_verdict import (
    FormulaCellVerdict,
    build_source_tooltip,
    verdict_from_evaluation,
)
from app.services.formula_management.effective_formula import (
    EffectiveFormula,
    FormulaKey,
    make_formula_key,
    resolve_effective_formula,
)

__all__ = [
    "InspectionFormulaResult",
    "DualModeGateStatus",
    "d4_14_sum_amounts",
    "d4_14_coverage_rate",
    "d4_14_occurrence_diff",
    "d4_15_completeness_diff",
    "d4_15_sum_completeness",
    "d4_16_ports_diff",
    "d4_16_tax_diff",
    "d4_16_sum_diffs",
    "resolve_and_execute",
    "check_dual_mode_gate",
    "DUAL_MODE_STATUS",
]

# ── 双模式 gate 状态 ──────────────────────────────────────────────────────────

DualModeGateStatus = str  # 'connected' | 'blocking' | 'unknown'

# 当前 D4 36 sheet 共用 `d4:save-items` last-write-wins 保存链，尚未完全接通
# ContentMutationService → useWorkpaperSyncBridge → 三方合并 → durable ack。
# 按 Req 2.3 要求，单模式只标记阻塞态。
DUAL_MODE_STATUS: DualModeGateStatus = "blocking"


def check_dual_mode_gate() -> dict[str, Any]:
    """返回双模式 gate 状态。

    当 `d4:save-items` 保存链未接通 ContentMutationService 三方合并时，
    status='blocking'、reason 说明原因。接通后改为 'connected'。
    """
    return {
        "status": DUAL_MODE_STATUS,
        "save_chain": "d4:save-items → useD4FormData.saveBatch → PUT /checklist-responses",
        "mutation_service": "ContentMutationService 尚未接入（D4 36 sheet 共用 last-write-wins）",
        "sync_bridge": "useWorkpaperSyncBridge 尚未为 D4-14/15/16 独立接入",
        "three_way_merge": "版本三方合并待统一双向路径完成后接入",
        "durable_ack": "durable ack 待 sync bridge 接入后可用",
        "reason": (
            "D4 四表（D4-14/15/16）与其余 D4 sheet 共用 d4:save-items 保存链，"
            "该链走 PUT /checklist-responses last-write-wins，未经 ContentMutationService "
            "三方合并与 durable ack。按 Req 2.3，单模式只能标记阻塞态、不能宣称完成。"
            "接通需与 d4-9 统一双向路径合并推进。"
        ),
    }


# ── 纯函数执行器（与前端同定义）──────────────────────────────────────────────

def _safe_decimal(val: Any) -> Decimal:
    """安全转 Decimal（与前端 parseNum 同语义：无效→0）。"""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


# ── D4-14 发生检查 ────────────────────────────────────────────────────────────

def d4_14_sum_amounts(items: list[dict], dimension: str) -> Decimal:
    """D4-14 合计行 SUM：凭证金额/出库金额/发票金额。

    与前端 `calcSubtotal(values.map(i => i[dim].amount))` 同定义。
    """
    total = Decimal("0")
    for item in items:
        dim_data = item.get(dimension, {})
        total += _safe_decimal(dim_data.get("amount", 0))
    return total


def d4_14_coverage_rate(
    voucher_sum: Decimal, revenue_audited: Decimal
) -> Decimal:
    """D4-14 检查比例 = 凭证金额合计 / D4-1 营业收入合计审定数。

    与前端 `calcCoverageRate(checkedAmount, revenueTotal)` 同定义。
    除零返回 0。
    """
    if revenue_audited == 0:
        return Decimal("0")
    return voucher_sum / revenue_audited


def d4_14_occurrence_diff(
    voucher_sum: Decimal, delivery_sum: Decimal
) -> Decimal:
    """D4-14 发生一致性判定 = 凭证金额合计 − 出库金额合计（应为 0）。

    与前端 SUM(凭证金额) - SUM(出库金额) 同定义。
    """
    return voucher_sum - delivery_sum


# ── D4-15 完整性检查 ──────────────────────────────────────────────────────────

def d4_15_completeness_diff(
    delivery_amount: Decimal, invoice_amount: Decimal
) -> Decimal:
    """D4-15 一致性：发货单金额 − 发票金额（0 为一致）。

    与前端 `checkConsistency` 中 amounts 比对同语义（三维度的综合判定
    由前端 checkConsistency 做，这里只声明金额差口径供 F-SHELL 消费）。
    """
    return delivery_amount - invoice_amount


def d4_15_sum_completeness(
    items: list[dict], dimension: str
) -> Decimal:
    """D4-15 合计行：发货单/发票/记账凭证金额 SUM。

    dimension: 'delivery' | 'invoice' | 'voucher'
    """
    total = Decimal("0")
    for item in items:
        dim_data = item.get(dimension, {})
        total += _safe_decimal(dim_data.get("amount", 0))
    return total


# ── D4-16 出口核对 ────────────────────────────────────────────────────────────

def d4_16_ports_diff(book_amount: Decimal, ports_amount: Decimal) -> Decimal:
    """D4-16 口岸差异 = 账面出口收入金额 − 电子口岸结关金额。

    与前端 `row.portsDiff = row.bookAmount - row.portsAmount` 完全同定义。
    """
    return book_amount - ports_amount


def d4_16_tax_diff(book_amount: Decimal, tax_report_amount: Decimal) -> Decimal:
    """D4-16 申报差异 = 账面出口收入金额 − 免抵退税申报外营收入。

    与前端 `row.taxDiff = row.bookAmount - row.taxReportAmount` 完全同定义。
    """
    return book_amount - tax_report_amount


def d4_16_sum_diffs(rows: list[dict], field: str) -> Decimal:
    """D4-16 差异合计 SUM。

    field: 'portsDiff' | 'taxDiff'
    与前端 `totalPortsDiff/totalTaxDiff` computed 同定义。
    """
    total = Decimal("0")
    for row in rows:
        total += _safe_decimal(row.get(field, 0))
    return total


# ── 统一裁决入口 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InspectionFormulaResult:
    """检查表公式执行结果（含 verdict + 双模式 gate 状态）。"""

    verdict: FormulaCellVerdict
    dual_mode_gate: DualModeGateStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.to_dict(),
            "dualModeGate": self.dual_mode_gate,
        }


def resolve_and_execute(
    wp_id: str,
    stable_sheet_key: str,
    row_key: str,
    field_key: str,
    *,
    computed_value: Decimal | None = None,
    errors: list[str] | None = None,
    custom_expression: str | None = None,
    preset_entries: list | None = None,
    preset_index: dict | None = None,
) -> InspectionFormulaResult:
    """解析 + 执行 + 裁决，返回 InspectionFormulaResult。

    1. 通过 `resolve_effective_formula` 从预设库取 expression/refs/params。
    2. 调用方已按同定义纯函数算出 `computed_value`（或传 errors）。
    3. 通过 `verdict_from_evaluation` 裁决：失败 → value=None（保留原值不转零）。
    4. 附带 dual_mode_gate 状态。

    注：本模块的纯函数与前端同定义，调用方先算好 computed_value 再经裁决，
    不在这里重新 eval expression 字符串（避免 eval 安全风险）。
    """
    key = make_formula_key(
        wp_id=wp_id,
        stable_sheet_key=stable_sheet_key,
        row_key=row_key,
        field_key=field_key,
    )

    eff = resolve_effective_formula(
        key,
        custom_expression=custom_expression,
        preset_entries=preset_entries,
        preset_index=preset_index,
    )

    verdict = verdict_from_evaluation(
        eff,
        value=computed_value,
        errors=errors,
    )

    return InspectionFormulaResult(
        verdict=verdict,
        dual_mode_gate=DUAL_MODE_STATUS,
    )
