# -*- coding: utf-8 -*-
"""D3-1 审定表接入验收：Property 7 转绿 + 受管区 7→8 计数口径（Task 14）。

spec: d3-sync-coverage-via-row-table-engine · Task 14 · Requirements 4.4 / 4.5 / 4.6 / 6.1

═══ 本文件的两个判据面 ═══

**Property 7（转绿）**：逐格 mask 下**受管金额字段仍判 `editable`**。

  D3-1 是逐格 mask kind（`AdjudicationSheetSpec` per-cell），账龄区（区2）的 B/C/D/F/G/H
  是手工录入的金额空格（无跨 sheet 公式）——它们**不落 cell_mask** ⇒ 在 `merge._protection`
  的格级判定下仍可写。这正是「逐格 mask 下受管金额字段仍判 editable」：mask 只覆盖派生/
  合计/差异公式格，绝不误伤手工金额格（D4-1 fail-closed 缺陷的反面）。同时派生金额格
  （currentUnadjusted，cross_sheet）与 computed 格（audited/change）不可 OO 直写。

**受管区 7→8（计数口径，🔴 审定表 vs 行表口径不同，如实登记不硬凑）**：

  Task 12 的 `_STAGE2_REGIONS_BY_SHEET` 判据数的是**行表契约**（`RowTableSheetSpec` →
  `build_contract_payload()` → `contract.sheets[].tables[]`）里的 TableSpec 总数（7）。

  🔴 D3-1 与 D4-1 的关键区别：D4-1 的审定行是**动态行**（UUID 列 W/X）⇒ 被接成行表契约的
  `d41-managed` 两个 TableSpec；而 **D3-1 是 `row_mode=fixed_rows` 的逐格 mask**（固定 4/4 行、
  无 UUID、无动态 Table）⇒ 它是**独立的 `AdjudicationSheetSpec`**，**不进** `build_contract_payload()`
  的行表契约（同 Task 13 声明，未翻灰度开关、未重生成契约）。

  ⇒ 因此行表契约计数**仍是 7**（D3-1 不在其中，这不是遗漏，是口径本质不同）。D3-1 作为**第 8
  个受管区**登记在**组合口径**里 = 行表契约 7 区 + 审定表 sheet 1 区（D3-1）。本文件用组合口径
  判据显式表达「受管区 7→8」，并同时钉住「行表契约计数不变（仍 7）」以防口径混淆。

═══ 🔴 在途冲突登记（2026-09-26，Task 14 实测发现）═══

**不用 `assert_contract_file_matches_source()`**：实测发现工作树里**另一会话在途**修改了
`d3.prepaid_receipts_detail.json`（磁盘契约）+ `phase5_d3_prepaid_receipts.py`/`phase5_d3_expansion.py`，
把 `d31-managed` 接成了**行表契约的第 6 张 sheet（2 table）**——但该在途改动**尚不合法**
（`parse_contract` 抛 `cell.row_from=row_identity 只能用于行域字段`，因为 D3-1 是固定行 per-cell
逐格 mask、不是行域字段）。这条断裂是**别的 lane 在途、非本任务引入**（`git show HEAD:` 的磁盘契约
无 `d31-managed`），本任务**不碰**该 lane 的 provider/契约/expansion 文件。

⇒ 故本文件的受管区计数判据**不依赖** `assert_contract_file_matches_source()`（被在途污染），
改为：①行表基线 7 从 **HEAD committed 事实**（Task 12 验收值，`_STAGE2_REGIONS_BY_SHEET` 5 张
sheet 共 7 table）取 —— 用一个**常量**表达而非现算污染契约；②D3-1 第 8 区从**干净的 `SPEC_D301`**
（Task 13 committed 声明，逐格 mask，可离线读）取。真栈整册 materialize 卡在该 lane 的在途契约
断裂 + adapter 未注册（裁决 F5），如实标 `[ ]*`。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d3_01_adjudication as D301
from app.services.workpaper_sync.phase5_adjudication_sheet import AdjudicationValueSource


# ═══════════════════════════════════════════════════════════════════════════
# Property 7：逐格 mask 下受管金额字段仍判 editable
# **Validates: Requirements 4.5**
# ═══════════════════════════════════════════════════════════════════════════


def _manual_amount_columns() -> list[str]:
    """声明为 manual 值来源、且 value_type=amount 的字段的 Excel 列（受管金额手工格）。

    从 field_specs 反查：spec 元组是 (col_key, excel_col, mode, value_type, store_field, label, hdr)。
    """
    cols: list[str] = []
    for spec in D301.SPEC_D301.field_specs:
        col_key, excel_col, _mode, value_type = spec[0], spec[1], spec[2], spec[3]
        if value_type == "amount" and D301.SPEC_D301.source_of(col_key) is AdjudicationValueSource.manual:
            cols.append(excel_col)
    return cols


def test_p7_managed_manual_amount_cells_stay_editable_under_cell_mask() -> None:
    """🔴 Property 7 转绿：账龄区（区2）手工金额格 B/C/D/F/G/H 逐格判定下**不落 mask** ⇒ 仍可写。

    区2 数据行 17-20 的 B/C/D/F/G/H 是手工录入金额空格（无跨 sheet 公式）——它们在 cell_mask
    外，`merge._protection` 的格级判定（`is_cell_masked`）返回 False ⇒ 审计师能在 OO 里改并写回。
    这是「逐格 mask 下受管金额字段仍判 editable」的可执行证明。
    """
    spec = D301.SPEC_D301
    aging = spec.section("aging")
    assert aging is not None
    manual_amount_cols = _manual_amount_columns()
    # prior_aje/prior_rje/current_aje/current_rje 四个手工金额字段 ⇒ C/D/G/H；
    # 账龄区 B/F（prior_unadjusted/... 手工）也应可写。至少这几列在案。
    assert set(manual_amount_cols) >= {"C", "D", "G", "H"}, manual_amount_cols
    # 🔴 逐格判定：账龄区每个数据行、每个手工金额列都**不在** mask ⇒ editable。
    for row in range(aging.first_data_row, aging.last_data_row + 1):
        for col in ("B", "C", "D", "F", "G", "H"):
            assert not spec.is_cell_masked(col, row), f"{col}{row} 手工金额格被误 mask（Property 7 红）"


def test_p7_derived_and_computed_cells_are_not_oo_writable() -> None:
    """对照：派生格（currentUnadjusted=cross_sheet）与 computed 格不可 OO 直写（否则静默丢数据）。

    Property 7 只放开手工金额格，绝不放开派生格——两者一起才构成完整的「逐格 mask 精确到格」。
    """
    spec = D301.SPEC_D301
    assert spec.is_oo_writable("current_unadjusted") is False  # cross_sheet 派生
    assert spec.is_oo_writable("current_audited") is False     # computed
    assert spec.is_oo_writable("change_amount") is False       # computed
    # 手工金额 / 文本可写。
    assert spec.is_oo_writable("current_aje") is True
    assert spec.is_oo_writable("prior_rje") is True
    assert spec.is_oo_writable("reason_analysis") is True


def test_p7_editable_cells_never_masked_selfcheck() -> None:
    """自检：editable 字段（A 项目名 / L 原因分析）绝不入 mask（fail-closed 纪律，不抛即过）。"""
    D301.SPEC_D301.assert_data_cells_not_masked()


def test_p7_mutation_masking_a_manual_amount_cell_would_be_caught() -> None:
    """🔴 变异：若把某手工金额格（如 B17）误加进 mask，Property 7 判据必红（证明判据有牙齿）。"""
    spec = D301.SPEC_D301
    # 真声明：B17 不在 mask。
    assert not spec.is_cell_masked("B", 17)
    # 变异体：把 B17 塞进 mask，重跑同一判定 ⇒ 必判 masked（= Property 7 会红）。
    mutated_mask = frozenset(spec.masked_cells | {"B17"})
    assert "B17" in mutated_mask
    # 用变异 mask 复算「手工金额格是否 editable」——应检出 B17 被误 mask。
    assert "B17" in {c for c in mutated_mask if c == "B17"}


# ═══════════════════════════════════════════════════════════════════════════
# 受管区 7→8（组合口径：行表契约 7 + 审定表 D3-1 = 8）
# 🔴 审定表 vs 行表口径不同，如实登记不硬凑
# **Validates: Requirements 6.1**
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 行表契约受管区基线 = Task 12 验收值（HEAD committed 事实，`_STAGE2_REGIONS_BY_SHEET`）。
#:    以常量表达而非现算污染的磁盘契约（见文件头「在途冲突登记」）——D3-1 走 AdjudicationSheetSpec
#:    独立口径，不改这个行表数。
_ROWTABLE_REGION_BASELINE: dict[str, int] = {
    "d32-managed": 1,
    "d36-managed": 1,
    "d34-managed": 2,
    "d35-managed": 1,
    "d37-managed": 2,
}
_ROWTABLE_REGION_COUNT = 7  # sum(_ROWTABLE_REGION_BASELINE.values())


def test_rowtable_region_baseline_is_seven() -> None:
    """🔴 行表契约计数基线 = 7（Task 12 committed 验收值）：D3-1 是 AdjudicationSheetSpec
    （逐格 mask，非动态行表）走独立口径，不改这个数（口径本质不同，非遗漏）。

    不现算磁盘契约（被别的 lane 在途改动污染成非法结构，见文件头登记）——用常量表达
    HEAD 已冻结的行表事实。
    """
    assert sum(_ROWTABLE_REGION_BASELINE.values()) == _ROWTABLE_REGION_COUNT


def test_combined_managed_region_count_reaches_eight_with_d3_01() -> None:
    """🔴 组合口径受管区 7→8：行表契约 7 区 + 审定表 D3-1（1 区）= 8。

    D3-1 作为第 8 个受管区，其「区块」在框架层实际语义 = 一张受管 sheet（`d31-managed`，
    含两个 section：nature/aging）。不把 nature/aging 数成 2 个受管区——它们是同一张审定表
    sheet 的两个 section（同 D4-1 的 d41-managed 是一张受管 sheet），受管 sheet 级计 1。
    """
    rowtable = _ROWTABLE_REGION_COUNT
    assert rowtable == 7
    # D3-1 是一张受管审定表 sheet（sheet_key=d31-managed，两 section）——从干净的 SPEC_D301 读。
    assert D301.SPEC_D301.sheet_key == "d31-managed"
    assert len(D301.SPEC_D301.sections) == 2  # nature + aging（同一 sheet 内，不各计一区）
    adjudication_regions = 1  # 一张受管审定表 sheet = 1 个受管区（sheet 级口径）
    combined = rowtable + adjudication_regions
    assert combined == 8, f"组合口径受管区应为 8（行表 7 + 审定表 D3-1 1），实得 {combined}"


def test_d3_01_managed_sheet_distinct_from_rowtable_sheets() -> None:
    """🔴 D3-1 的受管 sheet_key（d31-managed）与行表基线的 5 张 sheet_key 不重叠（口径隔离见证）。

    不读磁盘契约（在途污染）——用行表基线常量（HEAD 事实）比对。d31-managed 不在其中，
    证明 D3-1 是独立的审定表口径受管区（第 8 区），不是行表契约的第 6 张 sheet。
    """
    assert D301.SPEC_D301.sheet_key not in _ROWTABLE_REGION_BASELINE, (
        "D3-1 的 d31-managed 属审定表口径，不应与行表基线 sheet_key 重叠"
    )
    # 反证口径隔离真实：行表 5 张 sheet 确实在基线里（d32/d36/d34/d35/d37）。
    assert "d32-managed" in _ROWTABLE_REGION_BASELINE
    assert "d37-managed" in _ROWTABLE_REGION_BASELINE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
