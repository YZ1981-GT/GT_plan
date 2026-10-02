# -*- coding: utf-8 -*-
"""materialize 的 `_apply_workbook_propagation` 对 **NCR 编码的 CJK sheet 名**传播守卫。

spec: l6-true-bidirectional-2026-10-01 · 第6步（真 OO 往返抓到的 materialize 引擎缺口）

缺口：某些 Excel 保存路径把公式里的 CJK sheet 名序列化成数字字符引用
`'&#26126;&#32454;&#34920;L6-2'!P20`（L6 的 附注披露（国企）信息 sheet5 / 检查表L6-4
sheet8 实测如此）。计划期 `PropagationEntry.ref_before` 由**解码后**的 XML 得到裸中文
`'明细表L6-2'!P20`，而 apply 侧 `_apply_workbook_propagation` 对 part 文本做 `text.count()`
—— part 文本里是 `&#...;` 形态，裸中文 count 恒 0 ⇒ 声明 N 处实际改 0 处 ⇒ 误报
`PropagationDriftError`（真 OO 往返 L6 四条真栈 P20/Q20/R20/S20）。

修复：apply 候选集补「NCR 形态」（`&apos;` 单引号候选的正交补充），只编码非 ASCII 字符。

🔴 本测试与 `excel_workbook_row_change.apply_workbook_row_change`（N1 模块自带的 NCR 处理，
见 test_workbook_row_change_apply.py::test_numeric_character_reference_...）是**两条独立
apply 路径**：materialize 走 `_apply_workbook_propagation`（本测试），N1 走它自己的改写器。
两者都需要 NCR 支持；此前只有后者有。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_materialize as EM  # noqa: E402
from app.services.workpaper_sync.excel_workbook_row_change import (  # noqa: E402
    PropagationEntry,
)


@dataclass
class _Change:
    propagations: tuple[PropagationEntry, ...]


@dataclass
class _Plan:
    workbook_row_change: object | None
    deletion_change: object | None = None
    sheet_part: str = "xl/worksheets/sheet6.xml"


def _ncr(s: str) -> str:
    return "".join(ch if ord(ch) < 128 else f"&#{ord(ch)};" for ch in s)


def _entry() -> PropagationEntry:
    # 插行 +2：'明细表L6-2'!P20 → P22（L6 附注国企 B15 的 footer 总额引用）。
    return PropagationEntry(
        carrier="formula",
        part="xl/worksheets/sheet5.xml",
        locator="B15",
        ref_before="'明细表L6-2'!P20",
        ref_after="'明细表L6-2'!P22",
        row_before=20,
        row_after=22,
    )


def test_ncr_encoded_cjk_sheet_name_is_propagated() -> None:
    """part 文本把 CJK sheet 名写成 &#N;，裸中文 ref_before 仍应命中并位移 +2。"""
    entry = _entry()
    assert entry.ref_before == "'明细表L6-2'!P20"
    assert entry.ref_after == "'明细表L6-2'!P22"

    # part 文本按 Excel 的 NCR 序列化（CJK → &#N;），模拟 L6 sheet5 的真实形态。
    raw = f"<c r=\"B15\"><f>{_ncr(entry.ref_before)}-SUM({_ncr('明细表L6-2')}!P10:{_ncr('明细表L6-2')}!P14)</f></c>"
    assert "'明细表L6-2'!P20" not in raw  # 裸中文确实不在原文（否则测试空转）
    entries = {"xl/worksheets/sheet5.xml": raw.encode("utf-8")}
    plan = _Plan(workbook_row_change=_Change(propagations=(entry,)))

    out = EM._apply_workbook_propagation(dict(entries), plan=plan)
    result = out["xl/worksheets/sheet5.xml"].decode("utf-8")
    # P20 → P22（footer 总额引用随插行 +2），SUM 范围 P10:P14 不动（在插行点之上/之内未变）。
    assert "P22" in result and "P20" not in result, result
    assert "P10:" in result and "P14" in result, "SUM 范围被误动"


def test_mutation_without_ncr_candidate_would_drift() -> None:
    """反向：若 part 文本是**裸中文**（非 NCR），既有候选即可命中（证明 NCR 候选是增量不是替换）。"""
    entry = _entry()
    raw = f"<c r=\"B15\"><f>{entry.ref_before}-SUM('明细表L6-2'!P10:'明细表L6-2'!P14)</f></c>"
    entries = {"xl/worksheets/sheet5.xml": raw.encode("utf-8")}
    plan = _Plan(workbook_row_change=_Change(propagations=(entry,)))
    out = EM._apply_workbook_propagation(dict(entries), plan=plan)
    result = out["xl/worksheets/sheet5.xml"].decode("utf-8")
    assert "P22" in result and "'明细表L6-2'!P20" not in result
