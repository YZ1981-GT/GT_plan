# -*- coding: utf-8 -*-
"""删行的位移载体与工作簿级声明（Properties 1/2/3/5/6 + 结构锁）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 5.2 · 6.1 · 6.3 · 6.4 · 7.1~7.4
Requirements: 1.1~1.13 · 6.6

═══ 为什么这批判据要在真 zip 上跑 ═══

`plan_workbook_row_change_for_delete` 的四步（entries → 内存 zip → `_parse_workbook_xml`
→ `scan_reference_carriers`）里，前两步只在**真 zip** 上才有意义：拿 mock 的
`ReferenceScan` 喂门面会把「扫描口径对不对」整段跳过，而那恰是「声明与执行同源」的地基。
所以本文件自建一个最小但**非退化**的工作簿：一张受管 sheet + 一张引用侧 sheet +
`definedName`，引用侧对受管 sheet 的三类形态（删除点之上 / 之下 / 跨区间）各有样本。

═══ hypothesis 配置 ═══

`max_examples=5`（用户明确要求，禁默认 100）。
"""

from __future__ import annotations

import ast
import inspect
import io
import os
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

PBT = settings(max_examples=5, deadline=None)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PNS = "http://schemas.openxmlformats.org/package/2006/relationships"

MANAGED_SHEET = "受管表"
MANAGED_PART = "xl/worksheets/sheet1.xml"
REF_SHEET = "引用表"
REF_PART = "xl/worksheets/sheet2.xml"
REGION_FIRST = 7
REGION_LAST = 25
FOOTER_ROW = 26


# ═══════════════════════════════════════════════════════════════════════════
# 1. 最小非退化工作簿
# ═══════════════════════════════════════════════════════════════════════════


def _managed_sheet_xml(*, footer_formula: str = "SUM(B7:B25)") -> str:
    rows: list[str] = []
    for row in range(REGION_FIRST, REGION_LAST + 1):
        rows.append(
            f'<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>行{row}</t></is></c>'
            f'<c r="B{row}"><v>{row}</v></c><c r="W{row}" t="inlineStr">'
            f"<is><t>GTROW-SYN-{row:04d}</t></is></c></row>"
        )
    rows.append(
        f'<row r="{FOOTER_ROW}"><c r="A{FOOTER_ROW}" t="inlineStr"><is><t>合计</t></is></c>'
        f'<c r="B{FOOTER_ROW}"><f>{footer_formula}</f><v>0</v></c></row>'
    )
    return (
        f'<worksheet xmlns="{NS}"><dimension ref="A1:W{FOOTER_ROW}"/>'
        f'<sheetData>{"".join(rows)}</sheetData></worksheet>'
    )


def _reference_sheet_xml() -> str:
    """引用侧三类形态各一条 + 一条**指向被删行的单格引用**（悬空判据用）。"""
    cells = [
        # ① 删除点之上（逐字不动）
        f'<c r="A1"><f>\'{MANAGED_SHEET}\'!B8</f><v>0</v></c>',
        # ② 删除点之下（上移）
        f'<c r="A2"><f>\'{MANAGED_SHEET}\'!B24</f><v>0</v></c>',
        # ③ 跨区间的区间引用（收缩）
        f'<c r="A3"><f>SUM(\'{MANAGED_SHEET}\'!$B$7:$B$25)</f><v>0</v></c>',
        # ④ 指向 r=20 的单格引用（DanglingReferenceError 的靶子）
        f'<c r="A4"><f>\'{MANAGED_SHEET}\'!B20</f><v>0</v></c>',
    ]
    return (
        f'<worksheet xmlns="{NS}"><sheetData>'
        f'<row r="1">{cells[0]}</row><row r="2">{cells[1]}</row>'
        f'<row r="3">{cells[2]}</row><row r="4">{cells[3]}</row>'
        f"</sheetData></worksheet>"
    )


def build_entries(
    *,
    with_dangling_single_cell: bool = False,
    reference_rows_only_above: bool = False,
    no_reference_at_all: bool = False,
    footer_formula: str = "SUM(B7:B25)",
) -> dict[str, bytes]:
    """按需拼一份工作簿 entries。四个开关各对应一条判据的输入形态。

    🔴 **`definedName` 自己也是指向受管 sheet 的载体**，所以「零引用」与「引用全在删除点
    之上」两种输入必须**同时**处理 `definedNames` —— 首版只改了引用侧 sheet，判据当场
    打红（`GT_FOOTER_ANCHOR_SYN` 指 `$A$26`、`Print_Area` 指 `$A$1:$W$26`，两者都在
    删除点之下 ⇒ 声明非空）。那次打红是**生产行为正确**，修的是 fixture。
    """
    if no_reference_at_all:
        ref_xml = f'<worksheet xmlns="{NS}"><sheetData>' f'<row r="1"><c r="A1"><v>1</v></c></row></sheetData></worksheet>'
    elif reference_rows_only_above:
        ref_xml = (
            f'<worksheet xmlns="{NS}"><sheetData><row r="1">'
            f'<c r="A1"><f>\'{MANAGED_SHEET}\'!B8</f><v>0</v></c>'
            f"</row></sheetData></worksheet>"
        )
    else:
        ref_xml = _reference_sheet_xml()
        if not with_dangling_single_cell:
            ref_xml = ref_xml.replace(
                f'<c r="A4"><f>\'{MANAGED_SHEET}\'!B20</f><v>0</v></c>', ""
            )
    if no_reference_at_all:
        defined = ""
    elif reference_rows_only_above:
        # 两个 definedName 都指到**受管区首行之上** ⇒ 与引用侧 sheet 同样「全在删除点之上」
        defined = (
            f'<definedNames><definedName name="GT_FOOTER_ANCHOR_SYN">'
            f"'{MANAGED_SHEET}'!$A$1</definedName>"
            f'<definedName name="_xlnm.Print_Area" localSheetId="0">'
            f"'{MANAGED_SHEET}'!$A$1:$W$2</definedName></definedNames>"
        )
    else:
        defined = (
            f'<definedNames><definedName name="GT_FOOTER_ANCHOR_SYN">'
            f"'{MANAGED_SHEET}'!$A${FOOTER_ROW}</definedName>"
            f'<definedName name="_xlnm.Print_Area" localSheetId="0">'
            f"'{MANAGED_SHEET}'!$A$1:$W${FOOTER_ROW}</definedName></definedNames>"
        )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<workbook xmlns="{NS}" xmlns:r="{RNS}"><sheets>'
        f'<sheet name="{MANAGED_SHEET}" sheetId="1" r:id="rId1"/>'
        f'<sheet name="{REF_SHEET}" sheetId="2" r:id="rId2"/>'
        f"</sheets>{defined}</workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{PNS}">'
        f'<Relationship Id="rId1" Type="{RNS}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{RNS}/worksheet" Target="worksheets/sheet2.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(MANAGED_PART, _managed_sheet_xml(footer_formula=footer_formula))
        zf.writestr(REF_PART, ref_xml)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _uuids(rows: list[int] | tuple[int, ...]) -> dict[int, str]:
    return {row: f"GTROW-SYN-{row:04d}" for row in rows}


def _endpoint_rows(ref_text: str) -> tuple[int, ...]:
    """从一处引用文本里按**出现顺序**取端点行号。

    只取 `!` 之后的目标格部分（sheet 名里可能带数字，如 `明细表D2-2`），
    再按 `:` 切片逐段取行号。单格得 1 项、区间得 2 项。
    """
    import re as _re

    target = ref_text.rsplit("!", 1)[-1]
    out: list[int] = []
    for piece in target.split(":"):
        found = _re.search(r"(\d+)\s*$", piece.replace("$", ""))
        if found is not None:
            out.append(int(found.group(1)))
    return tuple(out)


def plan_delete(
    rows: tuple[int, ...] | list[int],
    *,
    entries: dict[str, bytes] | None = None,
    **overrides: Any,
) -> Any:
    kwargs: dict[str, Any] = {
        "managed_sheet_name": MANAGED_SHEET,
        "managed_sheet_part": MANAGED_PART,
        "deleted_rows": tuple(rows),
        "region_first_row": REGION_FIRST,
        "region_last_row": REGION_LAST,
        "row_uuids": _uuids(list(rows)),
    }
    kwargs.update(overrides)
    return N1.plan_workbook_row_change_for_delete(
        entries if entries is not None else build_entries(), **kwargs
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 2：删行位移载体的三条不变量
# ═══════════════════════════════════════════════════════════════════════════

#: 受管区内的行号集合（生成器的取值域）。
_rows = st.lists(
    st.integers(min_value=REGION_FIRST, max_value=REGION_LAST),
    min_size=1,
    max_size=8,
).map(lambda xs: tuple(sorted(set(xs))))


class TestProperty2CarrierInvariants:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 2: 删行位移载体的三条不变量**

    **Validates: Requirements 1.12, 1.13, 6.6**
    """

    @PBT
    @given(deleted=_rows)
    def test_deleted_rows_map_to_none(self, deleted: tuple[int, ...]) -> None:
        """① 被删行的映射结果为空值 —— 「这一行没了」在类型上不可忽略。"""
        shift = N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=REGION_FIRST,
            region_last_row=REGION_LAST,
        )
        for row in deleted:
            assert shift.shift(row) is None, (
                f"被删行 {row} 的 shift 返回了 {shift.shift(row)!r} 而不是 None —— "
                "返回行号会说谎（那个号已被别的行占用）"
            )

    @PBT
    @given(deleted=_rows)
    def test_survivors_move_up_by_deleted_above(self, deleted: tuple[int, ...]) -> None:
        """② 非被删行 = 行号 − 严格位于其上的被删行数。"""
        shift = N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=REGION_FIRST,
            region_last_row=REGION_LAST,
        )
        for row in range(1, REGION_LAST + 20):
            if row in deleted:
                continue
            above = sum(1 for d in deleted if d < row)
            assert shift.shift(row) == row - above, (
                f"行 {row}：上方被删 {above} 行，应上移到 {row - above}，"
                f"实得 {shift.shift(row)}"
            )

    @PBT
    @given(deleted=_rows)
    def test_inserted_rows_is_always_empty(self, deleted: tuple[int, ...]) -> None:
        """③ 新增行集合恒为空集合。

        🔴 这一条是**显式断言**而不是"反正是空的"：`_normalise_cell_ref` 里
        `if row in inserted: return ""` 会静默跳过格。将来若有人把被删行填进
        `inserted_rows`，症状是 after 侧的格被跳过 ⇒ 真实漂移被抹平（假绿）。
        """
        shift = N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=REGION_FIRST,
            region_last_row=REGION_LAST,
        )
        assert shift.inserted_rows == frozenset()
        assert isinstance(shift.inserted_rows, frozenset)

    @PBT
    @given(deleted=_rows)
    def test_unshift_is_the_exact_inverse_on_survivors(
        self, deleted: tuple[int, ...]
    ) -> None:
        """`unshift ∘ shift` 在存活行上是恒等 —— verify 归一化的地基。

        🔴 实现**不是** `row + count`：非连续删除下一个删后行号上方有几个被删行
        取决于它自己的位置。写成 `+ count` 会在「删 20 与 22、看 after 的 20」上算错。
        """
        shift = N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=REGION_FIRST,
            region_last_row=REGION_LAST,
        )
        for row in range(1, REGION_LAST + 20):
            after = shift.shift(row)
            if after is None:
                continue
            assert shift.unshift(after) == row, (
                f"行 {row} → after {after} → unshift {shift.unshift(after)} ≠ {row}"
            )

    def test_non_contiguous_unshift_is_not_plus_count(self) -> None:
        """钉死上一条里那个易错实现：`+ count` 在非连续删除上必错。"""
        shift = N1.RowDeletionShift(
            deleted_rows=(20, 22), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        # after 20 来自 before 21（只有 20 在它上方）⇒ unshift 应为 21，而 `+count` 给 22
        assert shift.unshift(20) == 21
        assert shift.unshift(20) != 20 + shift.count

    def test_range_end_collapses_to_previous_survivor(self) -> None:
        """区间端点落在被删行上 ⇒ 塌到上一存活行（Excel 的区间收缩语义）。"""
        shift = N1.RowDeletionShift(
            deleted_rows=(20, 22), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        assert shift.shift_range_end(22) == 20, "22 被删 ⇒ 塌到 21，21 的删后行号是 20"
        assert shift.shift_range_end(20) == 19, "20 被删 ⇒ 塌到 19，19 上方无被删行"
        assert shift.shift_range_end(25) == 23, "存活行走普通 shift"

    @pytest.mark.parametrize(
        "kwargs,exc",
        [
            (dict(deleted_rows=(), region_first_row=7, region_last_row=25), N1.RowChangeKindError),
            (dict(deleted_rows=(0,), region_first_row=0, region_last_row=25), N1.RowChangeKindError),
            (dict(deleted_rows=(30,), region_first_row=7, region_last_row=25), N1.RowChangeOutOfRegionError),
            (dict(deleted_rows=(8,), region_first_row=25, region_last_row=7), N1.RowChangeOutOfRegionError),
        ],
    )
    def test_construction_fails_closed(self, kwargs: dict[str, Any], exc: type) -> None:
        """空集 / 非法行号 / 区外 / 区首尾颠倒 —— 四条都 fail-closed。

        🔴 空集必须抛而不是「恒等映射」：空载体会让 verify 的归一化静默退化成
        什么都不做，而那正是「判据在空集上恒真」的形态。
        """
        with pytest.raises(exc):
            N1.RowDeletionShift(**kwargs)

    def test_carrier_is_frozen_and_has_no_mutation_surface(self) -> None:
        """与 `WorkbookRowChangePlan` 同一条纪律：冻结 + 零写入面。"""
        import dataclasses

        assert dataclasses.is_dataclass(N1.RowDeletionShift)
        assert N1.RowDeletionShift.__dataclass_params__.frozen  # type: ignore[attr-defined]
        shift = N1.RowDeletionShift(
            deleted_rows=(20,), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            shift.region_first_row = 1  # type: ignore[misc]
        # 构造期已跑过 `assert_no_mutation_surface`；这里再显式跑一次，
        # 防有人把 __post_init__ 里那句删掉（删掉后本断言打红）。
        from app.services.workpaper_sync.adapters.base import assert_no_mutation_surface

        assert_no_mutation_surface(shift, label="RowDeletionShift")
        src = textwrap.dedent(inspect.getsource(N1.RowDeletionShift))
        assert "assert_no_mutation_surface" in src

    def test_duplicates_and_order_are_normalised(self) -> None:
        """入参顺序与重复不作语义 —— 构造后恒为升序去重。"""
        shift = N1.RowDeletionShift(
            deleted_rows=(22, 20, 20, 22), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        assert shift.deleted_rows == (20, 22)
        assert shift.count == 2


# ═══════════════════════════════════════════════════════════════════════════
# 3. 零传播路径的 `None` 契约（Requirements 1.2 / 1.3 的声明侧）
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠ **Property 1（零传播路径恒等）的字节那一半不在本文件**：它要求「产物字节与不产声明时
#    逐字节相同」，而那需要 apply 期的 `MaterializePlan.deletion_change` 字段
#    ⇒ 判据落在 `test_row_deletion_apply.py`。本节只钉住声明侧的 `None` 契约。


class TestZeroPropagationReturnsNone:
    """两种零传播输入都返回 `None`，且**返回 `None` 之前三处 fail-closed 已执行**。"""

    def test_no_reference_to_managed_sheet(self) -> None:
        assert plan_delete((20,), entries=build_entries(no_reference_at_all=True)) is None

    def test_all_references_above_the_deleted_rows(self) -> None:
        """引用全在被删行之上 ⇒ 一条都不需要改 ⇒ `None`。"""
        assert (
            plan_delete((20,), entries=build_entries(reference_rows_only_above=True))
            is None
        )

    def test_none_path_still_runs_the_identity_gate(self) -> None:
        """🔴 `None` ≠ 没做检查：缺业务键时即使零传播也必须抛。

        不这样的话「零传播」会变成绕过留痕的后门：删了行、没有键、也没有声明。
        """
        with pytest.raises(N1.MissingRowIdentityError):
            plan_delete(
                (20,),
                entries=build_entries(no_reference_at_all=True),
                row_uuids={},
                stable_ordinals={},
            )

    def test_none_path_still_runs_the_bare_dangling_gate(self) -> None:
        """同上：受管 sheet 上的裸单格引用指向被删行时，零传播也必须抛。"""
        entries = build_entries(no_reference_at_all=True)
        xml = entries[MANAGED_PART].decode("utf-8")
        xml = xml.replace(
            f'<c r="B{FOOTER_ROW}"><f>SUM(B7:B25)</f>',
            f'<c r="B{FOOTER_ROW}"><f>B20*2</f>',
        )
        entries[MANAGED_PART] = xml.encode("utf-8")
        with pytest.raises(N1.DanglingReferenceError) as err:
            plan_delete((20,), entries=entries)
        assert "裸单格" in str(err.value)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 3：声明与载体同源
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3DeclarationAndCarrierShareOneSource:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 3: 声明与载体同源**

    **Validates: Requirements 1.1, 1.6**
    """

    @PBT
    @given(
        deleted=st.lists(
            st.integers(min_value=REGION_FIRST + 2, max_value=REGION_LAST - 1),
            min_size=1,
            max_size=4,
        ).map(lambda xs: tuple(sorted(set(xs))))
    )
    def test_every_entry_delta_matches_the_carrier(
        self, deleted: tuple[int, ...]
    ) -> None:
        """每条传播条目的行号增量 == 把改前行号喂给同一载体所得。

        单格与区间端点走**不同**的载体方法（`shift` / `shift_range_end`），
        所以同源判据按形态分流 —— 一刀切会在区间端点上假红。
        """
        # 删除点之下的单格引用固定在 B24，删 24 会让它悬空 ⇒ 排除 24。
        deleted = tuple(r for r in deleted if r != 24) or (20,)
        change = plan_delete(deleted)
        assert change is not None, f"deleted={deleted} 应产出声明"
        assert change.propagations, "声明为空 ⇒ 本条判据空转"
        for entry in change.propagations:
            assert entry.delta < 0, f"删行的 delta 必须为负，实得 {entry.delta}"
            before_rows = _endpoint_rows(entry.ref_before)
            after_rows = _endpoint_rows(entry.ref_after)
            assert len(before_rows) == len(after_rows), (
                f"{entry.locator}：改前 {before_rows} 与改后 {after_rows} 端点数不等 —— "
                "改写器把区间改成了单格（或反之）"
            )
            if len(before_rows) == 1:
                assert after_rows[0] == change.shift.shift(before_rows[0]), (
                    f"{entry.locator} 单格 {before_rows[0]}→{after_rows[0]}，"
                    f"载体给 {change.shift.shift(before_rows[0])}"
                )
                continue
            # 🔴 逐端点、按**方向**断言：起点向下塌、终点向上塌。
            head_b, tail_b = before_rows[0], before_rows[-1]
            head_a, tail_a = after_rows[0], after_rows[-1]
            assert head_a == change.shift.shift_range_start(head_b), (
                f"{entry.locator} 起点 {head_b}→{head_a}，"
                f"载体给 {change.shift.shift_range_start(head_b)}"
            )
            assert tail_a == change.shift.shift_range_end(tail_b), (
                f"{entry.locator} 终点 {tail_b}→{tail_a}，"
                f"载体给 {change.shift.shift_range_end(tail_b)}"
            )

    @PBT
    @given(deleted=st.integers(min_value=REGION_FIRST + 2, max_value=REGION_LAST - 2))
    def test_every_entry_points_at_the_managed_sheet(self, deleted: int) -> None:
        change = plan_delete((deleted,))
        assert change is not None
        for entry in change.propagations:
            assert MANAGED_SHEET in entry.ref_before, (
                f"条目 {entry.locator} 的改前文本 {entry.ref_before!r} 不含受管 sheet 名 "
                "—— 声明里混进了不指向受管 sheet 的引用"
            )

    def test_carrier_mismatch_is_refused_at_construction(self) -> None:
        """🔴 手搓一条与载体不同源的条目 ⇒ 构造期 fail-closed。

        这条把「同源」从「我们写对了」变成「写错了会打红」。
        """
        shift = N1.RowDeletionShift(
            deleted_rows=(20,), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        bogus = N1.PropagationEntry(
            carrier="formula",
            part=REF_PART,
            locator="A2#0",
            ref_before=f"'{MANAGED_SHEET}'!B24",
            ref_after=f"'{MANAGED_SHEET}'!B22",  # 应为 B23
            row_before=24,
            row_after=22,
        )
        with pytest.raises(N1.PropagationDriftError) as err:
            N1.RowDeletionChangeSet(propagations=(bogus,), shift=shift)
        assert "不同源" in str(err.value)

    def test_positive_delta_is_refused(self) -> None:
        """方向错了等于把数据指到反方向 ⇒ 构造期拒。"""
        shift = N1.RowDeletionShift(
            deleted_rows=(20,), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        wrong_way = N1.PropagationEntry(
            carrier="formula",
            part=REF_PART,
            locator="A2#0",
            ref_before=f"'{MANAGED_SHEET}'!B24",
            ref_after=f"'{MANAGED_SHEET}'!B25",
            row_before=24,
            row_after=25,
        )
        with pytest.raises(N1.PropagationDriftError) as err:
            N1.RowDeletionChangeSet(propagations=(wrong_way,), shift=shift)
        assert "非负 delta" in str(err.value)

    def test_change_set_declares_no_scalar_at_or_count_of_its_own(self) -> None:
        """🔴 刻意不暴露 `at` —— 非连续删除下它无法诚实表达。

        `count` 允许存在但必须**转发**给载体，不得是独立存的标量（独立存会漂）。
        """
        import dataclasses

        names = {f.name for f in dataclasses.fields(N1.RowDeletionChangeSet)}
        assert "at" not in names, names
        assert "count" not in names, f"count 不得是字段（应为 property 转发）：{names}"
        change = plan_delete((20, 22))
        assert change is not None
        assert change.count == change.shift.count == 2


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 5：悬空引用一律在计划期 fail-closed
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty5DanglingIsRefusedAtPlanTime:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 5: 悬空引用一律在计划期 fail-closed**

    **Validates: Requirements 1.7, 1.8**
    """

    def test_qualified_single_cell_pointing_at_a_deleted_row(self) -> None:
        """跨 sheet 单格引用指向被删行 ⇒ 写盘之前抛，且清单完整。"""
        with pytest.raises(N1.DanglingReferenceError) as err:
            plan_delete((20,), entries=build_entries(with_dangling_single_cell=True))
        text = str(err.value)
        assert "#REF!" in text and "single_cell" in text
        assert "20" in text, "错误里没点名坏在第几行"

    def test_bare_single_cell_on_the_managed_sheet(self) -> None:
        """🔴 受管 sheet 自己的**裸**单格引用 —— `scan_reference_carriers` 覆盖不到这一类。

        它只产限定引用（`propagate_reference_side` 是 `qualified_only=True`），
        所以 `find_dangling_sites` 对裸 `B20` 无能为力。不单独拦就是 fail-open。
        """
        with pytest.raises(N1.DanglingReferenceError) as err:
            plan_delete((20,), entries=build_entries(footer_formula="B20*2"))
        assert "裸单格" in str(err.value)

    def test_bare_range_partially_deleted_is_not_dangling(self) -> None:
        """裸**区间**只被删部分行属正确收缩，不算坏 —— 反向判据，防口径过宽。

        口径过宽的后果不是"更安全"：`SUM(B7:B25)` 是每张审定表的标配，
        把它判成悬空等于删行功能永久失败。
        """
        change = plan_delete((20,), entries=build_entries(footer_formula="SUM(B7:B25)"))
        assert change is not None

    def test_maximal_runs_detect_range_emptied(self) -> None:
        """🔴 逐**极大连续段**而不是逐行：`range_emptied` 只有按段看才能识别。

        `'受管表'!$B$13:$B$14` 在「删 13」与「删 14」各自看都只是收缩；
        合起来（连续段 13..14）才是删光。逐行调用会漏掉它 ⇒ 产物里写 `#REF!`。
        """
        assert N1._maximal_runs([20]) == ((20, 1),)
        assert N1._maximal_runs([13, 14]) == ((13, 2),)
        assert N1._maximal_runs([13, 14, 20, 22, 23, 24]) == ((13, 2), (20, 1), (22, 3))
        assert N1._maximal_runs([]) == ()
        # 入参乱序/重复不作语义
        assert N1._maximal_runs([14, 13, 13]) == ((13, 2),)

    def test_range_emptied_is_refused(self) -> None:
        """整段删光一个跨 sheet 区间引用 ⇒ `range_emptied` 并 fail-closed。"""
        entries = build_entries()
        ref_xml = entries[REF_PART].decode("utf-8")
        ref_xml = ref_xml.replace(
            "</sheetData>",
            f'<row r="9"><c r="A9"><f>SUM(\'{MANAGED_SHEET}\'!$B$13:$B$14)</f>'
            "<v>0</v></c></row></sheetData>",
        )
        entries[REF_PART] = ref_xml.encode("utf-8")
        with pytest.raises(N1.DanglingReferenceError) as err:
            plan_delete((13, 14), entries=entries)
        assert "range_emptied" in str(err.value)

    def test_explicit_opt_in_is_required_to_proceed(self) -> None:
        """只有契约显式放行（`allow_ref_errors=True`）才继续 —— 默认 fail-closed。"""
        entries = build_entries(with_dangling_single_cell=True)
        with pytest.raises(N1.DanglingReferenceError):
            plan_delete((20,), entries=entries)
        change = plan_delete((20,), entries=entries, allow_ref_errors=True)
        assert change is not None
        # 放行之后坏点**不进**传播清单（它们不是「改行号」而是「坏了」）
        assert all(
            entry.ref_before != f"'{MANAGED_SHEET}'!B20"
            for entry in change.propagations
        )

    def test_missing_managed_part_is_refused(self) -> None:
        """受管 sheet part 不在 entries 里 ⇒ 裸引用检测无从执行 ⇒ 抛，不静默跳过。"""
        entries = build_entries()
        del entries[MANAGED_PART]
        with pytest.raises(N1.PropagationDriftError):
            plan_delete((20,), entries=entries)

    def test_bare_scanner_reuses_the_single_a1_entry(self) -> None:
        """🔴 结构锁：裸引用识别走 `remap_a1_rows`，不另写一份 A1 正则。

        另写一份 = 本仓库第二个 A1 识别入口，四类误命中防线要各维护两份。
        """
        src = textwrap.dedent(inspect.getsource(N1._bare_a1_rows))
        assert "remap_a1_rows" in src, src
        # 反向：跨 sheet 引用不得被当成裸引用（那会把别的 sheet 的行号误判成本表的）
        assert N1.find_bare_dangling_rows(
            f'<worksheet><sheetData><row r="1"><c r="A1">'
            f"<f>'{MANAGED_SHEET}'!B20</f></c></row></sheetData></worksheet>",
            deleted_rows=(20,),
        ) == ()
        # 正向变异对照：同一扫描器在裸引用上必须命中（否则上面的空集是恒真）
        hit = N1.find_bare_dangling_rows(
            '<worksheet><sheetData><row r="1"><c r="A1"><f>B20*2</f></c></row>'
            "</sheetData></worksheet>",
            deleted_rows=(20,),
        )
        assert len(hit) == 1 and hit[0][2] == 20, hit

    def test_self_closing_cells_do_not_swallow_the_next_cell(self) -> None:
        """🔴 切片正则必须用**互斥交替**，不能用可选组。

        可选组 `(?:(?P<body>.*?)</c>)?` 在自闭合 `<c r="X"/>` 上会一路吞到下一格的
        `</c>`，被吞掉的那格于是查不到 —— 本 spec 的探针实测踩过，症状是
        「注入的公式读回 None」，差点被写成相反结论。
        """
        xml = (
            '<worksheet><sheetData><row r="1">'
            '<c r="A1" s="8"/><c r="B1"><f>B20*2</f></c>'
            "</row></sheetData></worksheet>"
        )
        hit = N1.find_bare_dangling_rows(xml, deleted_rows=(20,))
        assert [c for c, _t, _r in hit] == ["B1"], (
            f"自闭合格 A1 之后的 B1 没被看到：{hit} —— 切片正则被过度匹配"
        )


class TestBareDanglingSameRowIsNotDangling:
    """**Validates: Requirement 1.8**（悬空检测的假阳类：公式格自己那一行被删）

    🔴 这一条是 A1 覆盖面普查（18 组）当场打红 3 组才挖出来的真缺陷，不是补充判据。

    受管行上「行内自算」的公式是常态 —— 实测 G1-2 `W16 = U16+V16`、
    D1-7 `Q17 = IF(YEAR(C17)=YEAR($B$10)-1,H17,0)`、D3-4 `B17 = B11-B13-B14-B15-B16`。
    前两种引用的就是**同一行**的别的列：删掉那一行时公式格本身也没了，不可能留下
    `#REF!`。按「引用了被删行即悬空」一刀切的话，受管区里**每一行**都判不可删 ⇒
    删行功能在这些底稿上等于不存在，而外观是「一个很严谨的 fail-closed 把正常操作全拒了」。

    第三种（`B17` 在**存活行**上引用被删的 `B15`）才是真悬空，必须继续拦。
    """

    #: `W16` 行内自算（引用同一行的 U/V）；`B17` 在存活行上逐行相减（引用 11/13/15）。
    #: 🔴 `B17` 故意**不**引用 16 —— 否则删 r=16 会经 `B17` 命中，那测的就不是本条了
    #: （首版就这么写错，实测当场打红）。
    _XML = (
        '<worksheet><sheetData>'
        '<row r="16"><c r="W16"><f>U16+V16</f></c></row>'
        '<row r="17"><c r="B17"><f>B11-B13-B15</f></c></row>'
        "</sheetData></worksheet>"
    )

    def test_same_row_self_reference_is_not_dangling(self) -> None:
        """删 r=16：`W16` 引用了 `U16`/`V16`，但它自己也在 r=16 上 ⇒ 不算悬空。"""
        assert N1.find_bare_dangling_rows(self._XML, deleted_rows=(16,)) == (), (
            "行内自算公式被判成悬空 ⇒ 受管区每一行都会不可删"
        )

    def test_reference_from_a_surviving_row_is_still_dangling(self) -> None:
        """🔴 反向：同一份 XML 删 r=13 时，存活行 `B17` 上的 `B13` 必须被拦。

        没有这一条，上一条的「放行」可能只是把整类检查关掉了。
        """
        hit = N1.find_bare_dangling_rows(self._XML, deleted_rows=(13,))
        assert [(c, r) for c, _t, r in hit] == [("B17", 13)], (
            f"存活行上指向被删行的裸单格引用没被拦：{hit}"
        )

    def test_both_rows_deleted_keeps_only_the_surviving_referrer(self) -> None:
        """同时删 16 与 13：`W16` 随行消失（放行），`B17` 仍存活 ⇒ 仍拦它的 `B13`。

        🔴 这条证明过滤是**逐格**按「该格自己那一行」判的，不是「被删行集合非空就整片放行」。
        """
        hit = N1.find_bare_dangling_rows(self._XML, deleted_rows=(13, 16))
        assert [(c, r) for c, _t, r in hit] == [("B17", 13)], hit

    def test_census_would_have_been_blocked_everywhere_without_the_filter(self) -> None:
        """🔴 把缺陷的量级钉住：没有这条过滤，D1-7 最上区**每一行**都判不可删。

        这条是「为什么必须有这个过滤」的量化证据，而不是一句判断。
        """
        import re  # noqa: PLC0415

        import test_row_deletion_sibling_table_ref as CEN  # noqa: PLC0415

        sheet_name = "应收票据备查簿核对D1-7"
        assert sheet_name in CEN._CENSUS_SHEETS, f"{sheet_name} 不在现算普查清单里"
        data = CEN.SIB._instrumented_bytes_for_provider(CEN.SIB._provider_of_sheet(sheet_name))
        entries = CEN._entries_of(data)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            part = CEN.EE._sheet_parts(zf).get(sheet_name)
        assert part, sheet_name
        xml = entries[part].decode("utf-8")
        rows = list(range(13, 18))  # D1-7 最上区现算 13..17

        # ① 加了过滤：整区每一行都可删
        blocked = {r: N1.find_bare_dangling_rows(xml, deleted_rows=(r,)) for r in rows}
        assert not any(blocked.values()), (
            f"D1-7 最上区加了过滤后仍有行被拦：{ {k: v[:1] for k, v in blocked.items() if v} }"
        )

        # ② 没有过滤会拦住哪些行 —— 用**生产的** `_bare_a1_rows` 逐格现算（不手抄第二份
        #    A1 口径）：只要某个公式格的裸单格引用里出现了 r，旧口径就会把 r 判成悬空。
        would_block: dict[int, str] = {}
        for match in N1._CELL_WITH_BODY_RE.finditer(xml):
            body = match.group("body")
            if body is None or "<f" not in body:
                continue
            for formula in re.finditer(r"<f\b[^>]*>(?P<text>.*?)</f>", body, re.S):
                text = formula.group("text") or ""
                for row, is_range in N1._bare_a1_rows(text):
                    if not is_range and row in rows:
                        would_block.setdefault(row, text)
        assert sorted(would_block) == rows, (
            f"旧口径只会拦 {sorted(would_block)}，不是整区 {rows} —— "
            "那这个缺陷的量级就不是『删行功能等于不存在』，结论需重写"
        )
