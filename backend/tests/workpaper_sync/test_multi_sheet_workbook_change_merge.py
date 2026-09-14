"""合并多趟 materialize 的 workbook 级位移声明（并集 + 去重 + 冲突检测）。

spec: multi-sheet-materialize-defined-name-shift-normalization · 批次 1

═══ 判的是什么 ═══

`merge_workbook_row_change_propagations` 是纯函数:把多个 `WorkbookRowChangePlan`（各趟 materialize
自己的 workbook 级传播声明）合并成一份 `MaterializeWorkbookChangeSet`,供 verify 消费。
真实缺陷:多 sheet materialize 只保留主 binding 的 plan,sibling 各趟对 workbook.xml own-sheet
definedName（GT_FOOTER_ANCHOR/Print_Area）的合法位移声明被丢 ⇒ verify 判 adapter_unmanaged_region_drift。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync.excel_workbook_row_change import (  # noqa: E402
    MaterializeWorkbookChangeSet,
    PropagationDriftError,
    PropagationEntry,
    RowChangeKind,
    WorkbookRowChangePlan,
    merge_workbook_row_change_propagations,
)


def _entry(
    *,
    part: str,
    locator: str,
    ref_before: str,
    ref_after: str,
    carrier: str = "defined_name",
    row_before: int = 24,
    row_after: int = 36,
) -> PropagationEntry:
    return PropagationEntry(
        carrier=carrier,
        part=part,
        locator=locator,
        ref_before=ref_before,
        ref_after=ref_after,
        row_before=row_before,
        row_after=row_after,
    )


def _plan(managed_sheet_part: str, managed_sheet_name: str, entries: tuple[PropagationEntry, ...]) -> WorkbookRowChangePlan:
    """一份最小合法 insert plan（标量字段仅为通过 __post_init__，verify 不读它们）。"""
    return WorkbookRowChangePlan(
        kind=RowChangeKind.INSERT,
        managed_sheet_name=managed_sheet_name,
        managed_sheet_part=managed_sheet_part,
        at=24,
        count=12,
        style_from=23,
        region_first_row=12,
        region_last_row=23,
        propagations=entries,
    )


def test_union_across_multiple_sheet_trips() -> None:
    """两趟各含不同 part 的条目 ⇒ 合并后条目数 = 两者之和。"""
    d422 = _plan(
        "xl/worksheets/sheet30.xml", "重要指标分析表D4-22",
        (_entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D422",
                ref_before="'重要指标分析表D4-22'!$A$24", ref_after="'重要指标分析表D4-22'!$A$36"),),
    )
    d423 = _plan(
        "xl/worksheets/sheet31.xml", "收入与开具发票金额比较分析D4-23",
        (_entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D423",
                ref_before="'收入与开具发票金额比较分析D4-23'!$A$24", ref_after="'收入与开具发票金额比较分析D4-23'!$A$36"),),
    )
    merged = merge_workbook_row_change_propagations([d422, d423])
    assert isinstance(merged, MaterializeWorkbookChangeSet)
    assert len(merged.propagations) == 2
    parts = {e.part for e in merged.propagations}
    assert parts == {"xl/workbook.xml"}
    locators = {e.locator for e in merged.propagations}
    assert locators == {"GT_FOOTER_ANCHOR_D422", "GT_FOOTER_ANCHOR_D423"}


def test_preserves_reference_side_sheet_entries_not_only_workbook() -> None:
    """R5:引用侧 sheet part 的条目也要保留,不能只留 workbook.xml。"""
    primary = _plan(
        "xl/worksheets/sheet37.xml", "客户信息检查表D4-29",
        (_entry(part="xl/worksheets/sheet6.xml", locator="cell#0",
                carrier="formula",
                ref_before="'客户信息检查表D4-29'!$C$10", ref_after="'客户信息检查表D4-29'!$C$22",
                row_before=10, row_after=22),),
    )
    sibling = _plan(
        "xl/worksheets/sheet30.xml", "重要指标分析表D4-22",
        (_entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D422",
                ref_before="'重要指标分析表D4-22'!$A$24", ref_after="'重要指标分析表D4-22'!$A$36"),),
    )
    merged = merge_workbook_row_change_propagations([primary, sibling])
    assert merged is not None
    parts = {e.part for e in merged.propagations}
    assert parts == {"xl/worksheets/sheet6.xml", "xl/workbook.xml"}, parts


def test_dedup_identical_entries() -> None:
    """两趟含相同 (part,locator,ref_before,ref_after) ⇒ 只保留一份。"""
    e = _entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D422",
               ref_before="'重要指标分析表D4-22'!$A$24", ref_after="'重要指标分析表D4-22'!$A$36")
    p1 = _plan("xl/worksheets/sheet30.xml", "重要指标分析表D4-22", (e,))
    p2 = _plan("xl/worksheets/sheet30.xml", "重要指标分析表D4-22", (e,))
    merged = merge_workbook_row_change_propagations([p1, p2])
    assert merged is not None
    assert len(merged.propagations) == 1


def test_conflict_same_before_two_afters_raises() -> None:
    """同 (part, ref_before) 两个不同 ref_after ⇒ 抛 PropagationDriftError。"""
    p1 = _plan(
        "xl/worksheets/sheet30.xml", "重要指标分析表D4-22",
        (_entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D422",
                ref_before="'重要指标分析表D4-22'!$A$24", ref_after="'重要指标分析表D4-22'!$A$36"),),
    )
    p2 = _plan(
        "xl/worksheets/sheet30.xml", "重要指标分析表D4-22",
        (_entry(part="xl/workbook.xml", locator="GT_FOOTER_ANCHOR_D422_dup",
                ref_before="'重要指标分析表D4-22'!$A$24", ref_after="'重要指标分析表D4-22'!$A$40"),),
    )
    with pytest.raises(PropagationDriftError, match="冲突"):
        merge_workbook_row_change_propagations([p1, p2])


def test_all_none_returns_none() -> None:
    """全 None（或全无 propagations）⇒ 返回 None,保持零传播路径。"""
    assert merge_workbook_row_change_propagations([None, None]) is None
    empty = _plan("xl/worksheets/sheet30.xml", "重要指标分析表D4-22", ())
    assert merge_workbook_row_change_propagations([empty, None]) is None


def test_change_set_zero_mutation_surface_and_duplicate_guard() -> None:
    """MaterializeWorkbookChangeSet 零写入面;且直接构造重复条目被 __post_init__ 拦。"""
    e = _entry(part="xl/workbook.xml", locator="L1",
               ref_before="'S'!$A$1", ref_after="'S'!$A$2", row_before=1, row_after=2)
    ok = MaterializeWorkbookChangeSet(propagations=(e,))
    assert ok.propagations == (e,)
    with pytest.raises(PropagationDriftError, match="重复"):
        MaterializeWorkbookChangeSet(propagations=(e, e))
