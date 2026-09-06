# -*- coding: utf-8 -*-
"""Task 10 + 11 —— 插行传播判据（Property 4 / 5 / 6 / 7 / 8 / 9）。

spec: excel-workbook-wide-row-change-propagation / Wave 2 Task 10, 11
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.4
Properties: **P4** / **P5** / **P6** / **P7** / **P8** / **P9**

═══ 判的是哪一层 ═══

**传播器的输出**，不是落盘产物。所以本文件不依赖 Task 13 的 `apply_workbook_row_change`：
判据形态是「给定受管 sheet 与 `at/count` 声明后，`_rewrite_formula_refs` 对真实模板里
每一处引用的输出」。产物级（能否打开 / 部件完整）是 Wave 5 Task 25 的事。

═══ 两个载体的分工（Wave 0 Gate 1 裁决）═══

| 载体 | 角色 | 为什么 |
|---|---|---|
| **D2** `明细表D2-2` | **首要**、可端到端执行 | 今天唯一既有已审核 per-entry 契约、又有真实跨 sheet 引用的 entry |
| **K11** `审定表K11-1` | **结构**判据，不可执行 | 它**没有** per-entry 契约（`DELIVERED_PER_ENTRY_CONTRACTS` 只有 b60/d2/g7/h1）⇒ 只按「给定受管区声明后传播器的输出」取证，**不得**伪造一份 K11 契约当已审契约用 |

═══ 判据纪律 ═══

* **分母先立**：每条 Property 先断言命中处数 > 0。P9 还要断言总处数**恰为 114**——
  这个数同时防「扫少了」与「扫多了」。
* **3D 用注入**（全库 0 处），**外部工作簿用真实样本**（3,883 处）。两者都要
  ① 输出逐字不变 ② 在 `unpropagated` 里各有一条计数 —— 只验①的话，静默跳过也能过。
* **不复算分母**：D2 的 42/3/1/10 与 K11 的 114/19 已由 Task 8 的载体判据与清册三方锁死，
  这里直接引用 `EXPECTED`，不再各自数一遍（数第二遍就是第二真源）。
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    _rewrite_formula_refs,
    iter_qualified_references,
)

TEMPLATE_ROOT = _BACKEND / "wp_templates"

D2_REL = "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
D2_SHEET = "明细表D2-2"
#: D2 受管区（anchor A11，契约声明）。
D2_REGION = (11, 25)

K11_REL = "K/K11 资产减值损失.xlsx"
K11_SHEET = "审定表K11-1"
#: K11 受管区 `A7:N25`。
K11_REGION = (7, 25)

#: 复用 Task 8 载体判据里已与清册三方锁死的分母，不在本文件重新数一遍。
from tests.workpaper_sync.test_workbook_row_change_carriers import (  # noqa: E402
    EXPECTED,
)


def _remap_for(at: int, count: int) -> Callable[[int], int]:
    """插行位移：`>= at` 的行 `+count`。"""

    def remap(row: int) -> int:
        return row + count if row >= at else row

    return remap


def _scan(rel: str, target: str) -> N1.ReferenceScan:
    path = TEMPLATE_ROOT / rel
    if not path.is_file():  # pragma: no cover - 模板缺失时不冒充通过
        pytest.skip(f"权威模板不在磁盘上：{rel}")
    with zipfile.ZipFile(path) as zf:
        sheets, defined = _parse_workbook_xml(zf)
        parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
        return N1.scan_reference_carriers(
            zf, target_sheet=target, sheet_parts=parts, defined_names=defined
        )


@pytest.fixture(scope="module")
def d2_scan() -> N1.ReferenceScan:
    return _scan(D2_REL, D2_SHEET)


@pytest.fixture(scope="module")
def k11_scan() -> N1.ReferenceScan:
    return _scan(K11_REL, K11_SHEET)


# ═══════════════════════════════════════════════════════════════════════════
# Property 4 —— 插行时引用侧向下传播
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4DownwardPropagation:
    """`>= at` 的引用 `+= count`；`< at` 的逐字不变（Requirement 2.1 / 2.2）。"""

    @pytest.mark.parametrize("count", [1, 2, 5])
    def test_rows_at_or_after_insert_point_shift(self, count: int) -> None:
        """多个 count 都测 —— 只测 count=1 时「+1」与「+count」分辨不出来。"""
        at = 13
        propagate = frozenset({D2_SHEET})
        for row, expect in (
            (12, 12),          # < at：不动
            (13, 13 + count),  # == at：动（边界）
            (25, 25 + count),
        ):
            text = f"='{D2_SHEET}'!F{row}"
            out, changed = _rewrite_formula_refs(
                text, remap=_remap_for(at, count), propagate_sheets=propagate
            )
            assert out == f"='{D2_SHEET}'!F{expect}", (row, count, out)
            assert changed == (0 if expect == row else 1)

    def test_boundary_row_at_minus_one_is_untouched(self) -> None:
        """🔴 `at - 1` 必须不动 —— 判据写成 `> at` 时这条会红。

        插行的语义是「新行占据 `at`，原来 `>= at` 的行被推下去」⇒ `at - 1` 仍在原位。
        """
        at = 13
        text = f"='{D2_SHEET}'!F12+'{D2_SHEET}'!F13"
        out, _ = _rewrite_formula_refs(
            text, remap=_remap_for(at, 1), propagate_sheets=frozenset({D2_SHEET})
        )
        assert out == f"='{D2_SHEET}'!F12+'{D2_SHEET}'!F14", out

    def test_d2_real_template_every_site_propagates_correctly(
        self, d2_scan: N1.ReferenceScan
    ) -> None:
        """🔴 D2 真实模板：逐处核对每一个 `sites` 的行号变换。

        不是「抽样看几条」，是把扫描器找到的**全部** 46 处（42 公式 + 3 定义名 +
        1 超链接）逐处过一遍。每处按它自己的行号判：`>= at` 的 `+count`，其余不动。
        """
        at, count = 13, 1
        remap = _remap_for(at, count)
        propagate = frozenset({D2_SHEET})
        assert d2_scan.sites, "扫描无结果，判据空转"

        checked = shifted = untouched = 0
        for site in d2_scan.sites:
            raw = site.reference.raw
            out, _ = _rewrite_formula_refs(
                raw, remap=remap, propagate_sheets=propagate
            )
            refs_after = list(iter_qualified_references(out))
            assert len(refs_after) == 1, (raw, out)
            rows_before = site.rows
            rows_after = refs_after[0].rows
            expected = tuple(sorted({remap(r) for r in rows_before}))
            assert rows_after == expected, (
                f"行号变换错：{raw!r} → {out!r}\n"
                f"  改前行号 {rows_before} / 期望 {expected} / 实得 {rows_after}"
            )
            # sheet 名一个字符都不能动
            assert refs_after[0].sheet_name == D2_SHEET, out
            checked += 1
            if rows_after != rows_before:
                shifted += 1
            else:
                untouched += 1

        assert checked == len(d2_scan.sites)
        assert shifted > 0, "没有任何一处被传播 —— 判据空转"
        assert untouched > 0, (
            "全部都被传播了 ⇒ 语料里没有 `< at` 的引用，「不该动的没动」这半未被取证"
        )

    def test_sheet_name_digits_are_never_touched(self) -> None:
        """🔴 表名里的「字母+数字」不得被当成坐标。

        `明细表D2-2` 里的 `D2` 若被当成「D 列第 2 行」位移成 `D3`，公式会指向一个不存在
        的 sheet，当场死掉。全库实测表名形如 A1 引用的达 16,027 次 ⇒ 这不是边角情况。
        """
        for sheet in ("明细表D2-2", "审定表K11-1", "明细表H8-2", "Sheet1"):
            text = f"='{sheet}'!F20"
            out, _ = _rewrite_formula_refs(
                text, remap=_remap_for(1, 1), propagate_sheets=frozenset({sheet})
            )
            assert out.startswith(f"='{sheet}'!"), (
                f"表名被改动：{text!r} → {out!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 5 —— 绝对行同样传播
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty5AbsoluteRowsPropagate:
    """`'受管表'!$F$20` 在 `at <= 20` 时变 `$F$21`，`$` 保留（Requirement 2.3）。"""

    def test_absolute_row_shifts_and_keeps_dollar(self) -> None:
        """🔴 与 fill-down 相反：插行时 `$` 锁定的行**同样**位移。

        语义差别：`$` 锁的是「这一行」，而插行后那一行**物理上被推下去了** ——
        Excel 自身的插行行为也会改写它。fill-down 是「公式被复制到别处」，那时 `$` 才
        意味着不动。两个场景的正确答案相反，所以必须各有判据。
        """
        out, changed = _rewrite_formula_refs(
            f"='{D2_SHEET}'!$F$20",
            remap=_remap_for(13, 1),
            propagate_sheets=frozenset({D2_SHEET}),
        )
        assert out == f"='{D2_SHEET}'!$F$21", out
        assert changed == 1

    def test_absolute_column_relative_row_and_mixed(self) -> None:
        """四种 `$` 组合都测 —— 只测全绝对时列锁会不会被误动分辨不出来。"""
        cases = [
            ("F20", "F21"),
            ("$F20", "$F21"),
            ("F$20", "F$21"),
            ("$F$20", "$F$21"),
        ]
        for before, after in cases:
            out, _ = _rewrite_formula_refs(
                f"='{D2_SHEET}'!{before}",
                remap=_remap_for(13, 1),
                propagate_sheets=frozenset({D2_SHEET}),
            )
            assert out == f"='{D2_SHEET}'!{after}", (before, out)

    def test_d2_real_absolute_range_shifts(self, d2_scan: N1.ReferenceScan) -> None:
        """真实样本：D2 上的 `$AI$13:$AI$25` 这类全绝对区间必须传播。

        分母：D2 的公式载体里含 `$` 的处数必须 > 0，否则本条空转。
        """
        absolute_sites = [
            s for s in d2_scan.sites if "$" in s.reference.token
        ]
        assert absolute_sites, "D2 上没有带 $ 的引用 ⇒ 本条空转"

        at, count = 13, 1
        remap = _remap_for(at, count)
        for site in absolute_sites:
            out, _ = _rewrite_formula_refs(
                site.reference.raw, remap=remap, propagate_sheets=frozenset({D2_SHEET})
            )
            after = list(iter_qualified_references(out))[0]
            assert after.rows == tuple(sorted({remap(r) for r in site.rows})), (
                site.reference.raw,
                out,
            )
            # `$` 的个数与位置不得变
            assert out.count("$") == site.reference.raw.count("$"), (
                f"$ 的个数变了：{site.reference.raw!r} → {out!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 6 —— 区间引用的首尾各自判定
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty6RangeEndpointsJudgedSeparately:
    """`'受管表'!F10:F30` 在 `at=20` 时变 `F10:F31`（Requirement 2.4）。"""

    def test_range_straddling_insert_point(self) -> None:
        """🔴 首行不动、末行传播 —— 这是「首尾各自判定」的核心形态。

        若实现把整个区间当一个单位（按首行判），`F10:F30` 会整体不动 ⇒ 区间少覆盖新行；
        若按末行判，会整体 +1 ⇒ 首行错位。两种都是静默错值。
        """
        out, changed = _rewrite_formula_refs(
            f"='{D2_SHEET}'!F10:F30",
            remap=_remap_for(20, 1),
            propagate_sheets=frozenset({D2_SHEET}),
        )
        assert out == f"='{D2_SHEET}'!F10:F31", out
        assert changed == 1, "只有末行动了，changed 应为 1"

    @pytest.mark.parametrize(
        "before, at, count, after",
        [
            # 区间完全在插入点之前 ⇒ 都不动
            ("F10:F15", 20, 1, "F10:F15"),
            # 区间完全在插入点之后 ⇒ 都动
            ("F25:F30", 20, 1, "F26:F31"),
            # 跨插入点 ⇒ 首不动、末动
            ("F10:F30", 20, 1, "F10:F31"),
            # 首行恰等于 at ⇒ 都动（边界）
            ("F20:F30", 20, 1, "F21:F31"),
            # 末行恰等于 at - 1 ⇒ 都不动（边界）
            ("F10:F19", 20, 1, "F10:F19"),
            # count > 1
            ("F10:F30", 20, 3, "F10:F33"),
            # 单行区间落在插入点上
            ("F20:F20", 20, 2, "F22:F22"),
        ],
    )
    def test_range_boundaries(
        self, before: str, at: int, count: int, after: str
    ) -> None:
        out, _ = _rewrite_formula_refs(
            f"='{D2_SHEET}'!{before}",
            remap=_remap_for(at, count),
            propagate_sheets=frozenset({D2_SHEET}),
        )
        assert out == f"='{D2_SHEET}'!{after}", (before, at, count, out)

    def test_whole_row_range_endpoints_judged_separately(self) -> None:
        """整行区间（无列标）同样首尾各自判定 —— `$2:$6` 这类 definedNames 形态。

        D2 的 `_xlnm.Print_Titles` 就是 `'明细表D2-2'!$2:$6`。at=4 时应变 `$2:$7`。
        """
        out, _ = _rewrite_formula_refs(
            f"'{D2_SHEET}'!$2:$6",
            remap=_remap_for(4, 1),
            propagate_sheets=frozenset({D2_SHEET}),
        )
        assert out == f"'{D2_SHEET}'!$2:$7", out

        # 整个区间在插入点之上 ⇒ 逐字不动（D2 的真实情形，at=13）
        unchanged, changed = _rewrite_formula_refs(
            f"'{D2_SHEET}'!$2:$6",
            remap=_remap_for(13, 1),
            propagate_sheets=frozenset({D2_SHEET}),
        )
        assert unchanged == f"'{D2_SHEET}'!$2:$6" and changed == 0

    def test_column_only_range_has_no_rows_to_judge(self) -> None:
        """整列区间 `$A:$C` 不含行号 ⇒ 逐字不动（全库 66,059 处的形态）。

        ⚠ 用 `qualified_only=True`（引用侧语义）—— 否则公式里的裸引用 `A1` 会按 remap
        位移，那是**本 sheet 插行**的正确行为，会盖住本条想验的东西。
        """
        text = f"=VLOOKUP(A1,'{D2_SHEET}'!$A:$C,3,0)"
        out, changed = _rewrite_formula_refs(
            text,
            remap=_remap_for(1, 5),
            propagate_sheets=frozenset({D2_SHEET}),
            qualified_only=True,
        )
        assert out == text and changed == 0, out


# ═══════════════════════════════════════════════════════════════════════════
# Property 7 —— 非受管 sheet 的引用逐字不变
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty7OtherSheetsUnchanged:
    """同一公式里混合两种引用时，只有指向受管 sheet 的变（Requirement 2.5）。"""

    def test_mixed_formula_only_target_sheet_changes(self) -> None:
        """🔴 混合形态是最容易出错的：同一条公式里两个引用，一个该动一个不该动。

        实现若「只要 propagate_sheets 非空就把所有限定引用都位移」，本条会红 ——
        而那种实现在只含单一 sheet 引用的公式上完全看不出问题。
        """
        text = f"='审定表D2-1'!F20+'{D2_SHEET}'!F20"
        out, changed = _rewrite_formula_refs(
            text, remap=_remap_for(13, 1), propagate_sheets=frozenset({D2_SHEET})
        )
        assert out == f"='审定表D2-1'!F20+'{D2_SHEET}'!F21", out
        assert changed == 1

    def test_three_sheets_one_declared(self) -> None:
        """三张 sheet 只声明一张 —— 另两张必须逐字不动。"""
        text = (
            f"='审定表D2-1'!A10+'{D2_SHEET}'!B20+'附注披露信息(国企)'!C30"
        )
        out, changed = _rewrite_formula_refs(
            text, remap=_remap_for(5, 2), propagate_sheets=frozenset({D2_SHEET})
        )
        assert out == (
            f"='审定表D2-1'!A10+'{D2_SHEET}'!B22+'附注披露信息(国企)'!C30"
        ), out
        assert changed == 1

    def test_bare_references_in_same_formula_are_untouched(self) -> None:
        """🔴 改写引用侧 sheet 时，同一公式里的**裸**引用不得动（`qualified_only=True`）。

        ═══ 这条判据逼出了一个新参数 ═══

        Task 10 首次实测时本条**红了**：`=SUM(A20:B20)+'明细表D2-2'!F20` 传播后得到
        `=SUM(A21:B21)+'明细表D2-2'!F21` —— 裸引用 `A20:B20` 被一起推走了。

        那是错的：裸引用属于**引用侧** sheet（`审定表D2-1`），没有人在它上面插行。把它们
        推成 `A21:B21` = 引用侧 sheet 自己的坐标全部错位，且产物仍能打开（静默错行）。

        `_rewrite_formula_refs` 原先用**同一个** `remap` 处理裸引用与限定引用，表达不了
        这个区分；恒等 `remap` 也绕不过（那样限定引用也不动，等于没传播）。所以新增了
        `qualified_only` 开关。

        两个方向各有正确答案，不能只测一边：
        * 受管 sheet 自身改写（`shift_sheet_rows`）—— 裸引用**该**动；
        * 引用侧 sheet 改写（本条）—— 裸引用**不该**动。
        """
        text = f"=SUM(A20:B20)+'{D2_SHEET}'!F20"
        out, changed = _rewrite_formula_refs(
            text,
            remap=_remap_for(13, 1),
            propagate_sheets=frozenset({D2_SHEET}),
            qualified_only=True,
        )
        assert out == f"=SUM(A20:B20)+'{D2_SHEET}'!F21", out
        assert changed == 1

    def test_managed_sheet_side_still_shifts_bare_references(self) -> None:
        """🔴 反面对照：不开 `qualified_only` 时裸引用**必须**动。

        缺这条的话，把 `qualified_only` 写成恒为 True（或干脆去掉裸引用分支）也能让上一条
        绿 —— 而那会让受管 sheet 自身插行时坐标全部不动。
        """
        text = "=SUM(A20:B20)"
        out, changed = _rewrite_formula_refs(text, remap=_remap_for(13, 1))
        assert out == "=SUM(A21:B21)", out
        assert changed == 2

    @pytest.mark.parametrize(
        "text",
        [
            "=A20",
            "=SUM(A20:B20)",
            "=SUM(A13:Z99)",
            "=LOG10(A20)",
            "=A20+B21*C22",
        ],
    )
    def test_qualified_only_leaves_pure_bare_formulas_verbatim(self, text: str) -> None:
        """纯裸引用公式在引用侧改写下**整条**逐字不变（含区间与带数字函数名）。

        区间形态单独列出来的理由：实现若只跳过 `head` 而没消费整个 token，会从 token
        中间重新匹配 ⇒ `A13:Z99` 可能变成 `A13:Z100` 这类半改形态。
        """
        out, changed = _rewrite_formula_refs(
            text,
            remap=_remap_for(13, 1),
            propagate_sheets=frozenset({D2_SHEET}),
            qualified_only=True,
        )
        assert out == text and changed == 0, out

    def test_self_qualified_reference_on_other_sheet_is_untouched(self) -> None:
        """引用侧 sheet 的自限定引用（`'审定表D2-1'!A20` 写在 `审定表D2-1` 上）不动。"""
        text = f"='审定表D2-1'!A20+'{D2_SHEET}'!F20"
        out, _ = _rewrite_formula_refs(
            text,
            remap=_remap_for(13, 1),
            current_sheet="审定表D2-1",
            propagate_sheets=frozenset({D2_SHEET}),
        )
        # ⚠ 自限定分支会把 `'审定表D2-1'!A20` 当等价裸引用处理 ⇒ 它会按 remap 动。
        #    这是既有语义（本 sheet 插行时自限定引用确实该动），不是传播造成的。
        #    本条只断言**受管 sheet** 那一处按传播规则动了。
        after = [
            r for r in iter_qualified_references(out) if r.sheet_name == D2_SHEET
        ]
        assert len(after) == 1 and after[0].rows == (21,), out

    def test_string_literal_containing_sheet_name_is_untouched(self) -> None:
        """字符串字面量里的表名+坐标不是引用（两种实体形态都测）。"""
        for text in (
            f'=IF(A1="{D2_SHEET}!F20","是","否")',
            f"=IF(A1=&quot;{D2_SHEET}!F20&quot;,1,0)",
        ):
            out, changed = _rewrite_formula_refs(
                text, remap=_remap_for(13, 1), propagate_sheets=frozenset({D2_SHEET})
            )
            assert out == text and changed == 0, out

    def test_function_name_with_digits_is_untouched(self) -> None:
        """`LOG10(` 不是「LOG 列第 10 行」。"""
        text = f"=LOG10('{D2_SHEET}'!F20)"
        out, _ = _rewrite_formula_refs(
            text, remap=_remap_for(13, 1), propagate_sheets=frozenset({D2_SHEET})
        )
        assert out == f"=LOG10('{D2_SHEET}'!F21)", out

    def test_d2_real_template_other_sheet_refs_stay_verbatim(self) -> None:
        """真实模板：D2 上指向**别的** sheet 的引用逐字不变。

        分母：这类引用必须 > 0，否则本条空转。
        """
        from app.services.workpaper_sync.excel_row_shift import _F_RE

        path = TEMPLATE_ROOT / D2_REL
        if not path.is_file():  # pragma: no cover
            pytest.skip(f"模板不在磁盘上：{D2_REL}")

        at, count = 13, 1
        remap = _remap_for(at, count)
        others_seen = 0
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            sheets, _defined = _parse_workbook_xml(zf)
            for sheet in sheets:
                part = _normalise_part(sheet["rel_target"])
                if part not in names:
                    continue
                xml = zf.read(part).decode("utf-8", "replace")
                for fmatch in _F_RE.finditer(xml):
                    text = N1._unescape(fmatch.group("text") or "")
                    if not text:
                        continue
                    refs = list(
                        iter_qualified_references(text, current_sheet=sheet["name"])
                    )
                    others = [
                        r
                        for r in refs
                        if r.kind == "sheet"
                        and r.sheet_name != D2_SHEET
                        and r.sheet_name != sheet["name"]
                    ]
                    if not others:
                        continue
                    others_seen += len(others)
                    out, _ = _rewrite_formula_refs(
                        text,
                        remap=remap,
                        current_sheet=sheet["name"],
                        propagate_sheets=frozenset({D2_SHEET}),
                    )
                    after = {
                        (r.sheet_name, r.token)
                        for r in iter_qualified_references(
                            out, current_sheet=sheet["name"]
                        )
                        if r.kind == "sheet"
                        and r.sheet_name not in (D2_SHEET, sheet["name"])
                    }
                    before = {(r.sheet_name, r.token) for r in others}
                    assert after == before, (
                        f"指向别的 sheet 的引用被改动了：\n  {text!r}\n  → {out!r}\n"
                        f"  改前 {sorted(before)}\n  改后 {sorted(after)}"
                    )
        assert others_seen > 0, "D2 上没有指向别的 sheet 的引用 ⇒ 本条空转"


# ═══════════════════════════════════════════════════════════════════════════
# Property 8 —— 3D 与外部工作簿登记不传播
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty8ThreeDAndExternalRegistered:
    """两类都要 ① 输出逐字不变 ② 在 `unpropagated` 里各有一条计数（AC 2.6 / 9.4）。

    🔴 **只验①不够**：静默跳过也能让输出逐字不变。②才是「这一类被看见了」的证据。
    """

    @pytest.mark.parametrize(
        "text",
        [
            "=SUM(Sheet1:Sheet3!A20)",
            f"=SUM('{D2_SHEET}:明细表D2-3'!F20)",
        ],
    )
    def test_three_d_stays_verbatim(self, text: str) -> None:
        """3D 全库 **0** 处 ⇒ 注入变体（分母见 `EXPECTED['corpus_three_d_refs']`）。"""
        assert EXPECTED["corpus_three_d_refs"] == 0, (
            "3D 引用在语料里出现了 ⇒ 应改用真实样本，不再依赖注入"
        )
        out, changed = _rewrite_formula_refs(
            text, remap=_remap_for(1, 1), propagate_sheets=frozenset({D2_SHEET})
        )
        assert out == text and changed == 0, out

    def test_three_d_is_registered_in_unpropagated(self) -> None:
        """②：3D 必须在扫描的 `unpropagated` 里有计数。"""
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            f"<f>SUM('{D2_SHEET}:明细表D2-3'!F20)</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted)
        assert scan.counts_by_reason()["three_d_reference"] == 1, scan.as_dict()
        assert scan.sites == (), "3D 不该进传播候选"

    def test_external_workbook_stays_verbatim(self) -> None:
        """外部工作簿有真实样本 **3,883** 处 —— 两种写法都测。"""
        assert EXPECTED["corpus_external_refs"] > 0
        for text in (
            "=[1]Sheet1!A20",
            "=[1]底稿目录!A2",
            "='[31]已审利润纵向分析A1-13-4'!$E$27",
            "='[3]明细表H8-2'!A33:C33",
        ):
            out, changed = _rewrite_formula_refs(
                text,
                remap=_remap_for(1, 1),
                propagate_sheets=frozenset(
                    {D2_SHEET, "Sheet1", "底稿目录",
                     "[31]已审利润纵向分析A1-13-4", "[3]明细表H8-2"}
                ),
            )
            assert out == text and changed == 0, (
                f"外部工作簿引用被传播了：{text!r} → {out!r}"
            )

    def test_external_workbook_is_registered_in_unpropagated(self) -> None:
        """②：外部工作簿必须有计数，两种写法各一条。"""
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            "<f>[1]Sheet1!F29+'[3]明细表H8-2'!A33</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted)
        assert scan.counts_by_reason()["external_workbook"] == 2, scan.as_dict()
        assert scan.sites == ()

    def test_registration_counts_are_not_silently_merged(self) -> None:
        """🔴 3D 与外部工作簿必须**各自**一条，不得合并成「不传播 N 处」。

        合并的后果：人看到「不传播 5 处」无法判断该不该担心 —— 外部工作簿不传播是设计，
        3D 出现则说明语料变了需要重新裁决。两者的处置完全不同。
        """
        crafted = (
            '<worksheet><sheetData><row r="1"><c r="A1">'
            f"<f>[1]Sheet1!F29+SUM('{D2_SHEET}:明细表D2-3'!F20)</f>"
            "</c></row></sheetData></worksheet>"
        )
        scan = self._scan_crafted(crafted)
        reasons = scan.counts_by_reason()
        assert reasons["external_workbook"] == 1, reasons
        assert reasons["three_d_reference"] == 1, reasons
        registered = {c.reason for c in scan.unpropagated}
        assert registered == {"external_workbook", "three_d_reference"}, registered

    @staticmethod
    def _scan_crafted(sheet_xml: str) -> N1.ReferenceScan:
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as zf:
            return N1.scan_reference_carriers(
                zf,
                target_sheet=D2_SHEET,
                sheet_parts={D2_SHEET: "xl/worksheets/sheet1.xml"},
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 9 —— K11 的 114 处引用逐处正确
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9K11EverySiteCorrect:
    """K11 受管区插行后，114 处引用逐处比对（Requirement 2.7）。

    🔴 **K11 是结构判据载体，不是可执行载体** —— 它没有 per-entry 契约
    （`DELIVERED_PER_ENTRY_CONTRACTS` 只有 b60 / d2 / g7 / h1）。所以本类按「给定受管区
    声明后传播器的输出」取证，**不**伪造一份 K11 契约当已审契约用。
    """

    def test_site_count_is_exactly_114(self, k11_scan: N1.ReferenceScan) -> None:
        """分母：**恰为** 114 —— 这个数同时防「扫少了」与「扫多了」。"""
        counts = k11_scan.counts_by_carrier()
        assert counts["formula"] == EXPECTED["k11_formula"] == 114, counts

    def test_every_one_of_114_sites_propagates_correctly(
        self, k11_scan: N1.ReferenceScan
    ) -> None:
        """🔴 逐处核对全部 114 处，不抽样。

        `>= at` 的全部 `+count`，其余不变；总处数仍为 114（传播不得增删引用）。
        """
        at, count = 12, 2
        remap = _remap_for(at, count)
        propagate = frozenset({K11_SHEET})
        formula_sites = [s for s in k11_scan.sites if s.carrier == "formula"]
        assert len(formula_sites) == 114

        shifted = untouched = 0
        for site in formula_sites:
            raw = site.reference.raw
            out, _ = _rewrite_formula_refs(
                raw, remap=remap, propagate_sheets=propagate
            )
            after = list(iter_qualified_references(out))
            assert len(after) == 1, (raw, out)
            assert after[0].sheet_name == K11_SHEET, out
            expected = tuple(sorted({remap(r) for r in site.rows}))
            assert after[0].rows == expected, (
                f"{raw!r} → {out!r}：期望行号 {expected}，实得 {after[0].rows}"
            )
            if after[0].rows != site.rows:
                shifted += 1
            else:
                untouched += 1

        assert shifted + untouched == 114
        assert shifted > 0 and untouched > 0, (
            f"传播 {shifted} 处 / 不动 {untouched} 处 —— 两侧都必须非空，"
            "否则「该动的动了」与「不该动的没动」只有一半被取证"
        )

    def test_referenced_rows_are_the_19_managed_region_rows(
        self, k11_scan: N1.ReferenceScan
    ) -> None:
        """114 处引用落在受管区 `A7:N25` 的 **19** 个不同行上。"""
        region = set(range(K11_REGION[0], K11_REGION[1] + 1))
        assert len(region) == 19
        hit = region & set(k11_scan.referenced_rows)
        assert hit == region, f"未被引用的受管区行：{sorted(region - hit)}"

    def test_propagation_preserves_total_site_count(
        self, k11_scan: N1.ReferenceScan
    ) -> None:
        """🔴 传播后总处数仍为 114 —— 传播只改行号，不得增删引用。

        判据形态：把每处引用改写后重新分词，`sheet` 类引用的总数必须不变。少了说明某处
        被吃掉（公式坏了），多了说明产生了意外的分词结果。
        """
        at, count = 12, 2
        remap = _remap_for(at, count)
        propagate = frozenset({K11_SHEET})
        before = after = 0
        for site in (s for s in k11_scan.sites if s.carrier == "formula"):
            raw = site.reference.raw
            before += len(
                [r for r in iter_qualified_references(raw) if r.kind == "sheet"]
            )
            out, _ = _rewrite_formula_refs(
                raw, remap=remap, propagate_sheets=propagate
            )
            after += len(
                [r for r in iter_qualified_references(out) if r.kind == "sheet"]
            )
        assert before == after == 114, (before, after)

    def test_k11_has_no_per_entry_contract(self) -> None:
        """🔴 把「K11 不可执行」钉成判据 —— 防有人后来伪造一份 K11 契约当已审契约用。

        若哪天 K11 真的有了已审契约，本条会红 —— 那时应该把它升级成可执行载体并补
        端到端判据，而不是删掉本条。
        """
        from app.services.workpaper_sync.adapters import registry as RG

        rows = RG.DELIVERED_PER_ENTRY_CONTRACTS
        assert rows, "交付登记表为空 —— 判据在空集上恒真"
        codes = {
            f"{row.get('entry_id', '')}|{row.get('contract_id', '')}".lower()
            for row in rows
        }
        assert not any("k11" in c for c in codes), (
            f"K11 出现在已审 per-entry 契约里 {sorted(codes)} —— 若确已交付，"
            "本类应升级为端到端判据；否则说明有人伪造了契约"
        )
        assert any("d2" in c for c in codes), (
            f"D2 不在已审契约里 {sorted(codes)} —— 首要载体的前提没了，Gate 1 的裁决失效"
        )
