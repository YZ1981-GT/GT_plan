# -*- coding: utf-8 -*-
"""`excel_row_shift` 位移纯函数层的属性测试（T1）。

spec: excel-structural-row-insertion-and-shift-aware-verification / Wave 1
Tasks: 4 / 5 / 5.1 / 6 / 6.1 / 7 / 8 / 8.1（另覆盖 Task 13 的成员继承裁决）
Properties: **P1** / **P4** / **P6** / **P7** / **P8** / **P9** / **P10** / **P14**

═══ 为什么这一份必须存在 ═══════════════════════════════════════════════════

`excel_row_shift.py` 交付时**生产零引用、测试零覆盖**。零覆盖的代价已经实测到了：
`_build_inserted_row` 把新插入行做成共享公式**成员**，注释写着「主格 ref 已在阶段
A/E 扩到覆盖新行」—— 那句声称为假，真实 K11 模板上产出 **4 个孤儿成员**
（H26/H27 属 si=1 却落在 `ref=H8:H25` 之外，I26/I27 同理）。

openpyxl 不校验共享公式组自洽性，`structure_fingerprint` 也不看，所以「产物能打开」
把这个缺陷完整地掩盖住了。⇒ 判据必须落在**结构后果**（组自洽 / 逐行号 / 逐列样式），
不能落在「跑通没报错」。

═══ 判据纪律 ═══════════════════════════════════════════════════════════════

1. **fixture 用真实权威模板**（`backend/wp_templates/K/K11 资产减值损失.xlsx`），
   不手搓最小 xlsx —— 手搓的 sheet 没有共享公式、没有 mergeCell、没有跨 sheet 引用，
   本模块四类误命中判据会在空集上恒真。
2. **冻结的模板事实**（行号区间 / 组构成 / 可安全做样式来源的行集）在 :class:`TestFrozenTemplateFacts`
   里逐条断言。模板一变这些先红，而不是让别的用例莫名其妙地红。
3. **每条属性带反向自检**：把判据喂一份刻意做坏的产物，断言它**拒绝**。证明判据
   不是恒真 —— 这一步不做的话，「断言通过」与「断言什么也没查」不可分辨。
4. `@settings(max_examples=...)` 一律显式 `>= 100`：`backend/tests/conftest.py` 的
   默认 profile 是 `max_examples=5`，不显式写就等于每条属性只跑 5 个样例。
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.excel_structure_fingerprint import (
    _normalise_part as normalise_part,
)
from app.services.excel_structure_fingerprint import (
    _parse_workbook_xml as parse_workbook_xml,
)
from app.services.workpaper_sync import excel_row_shift as RS

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"

# ═══════════════════════════════════════════════════════════════════════════
# 0. 冻结的真实模板事实（全部实测得来，不是按模板"应该长什么样"写的）
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE = _BACKEND / "wp_templates" / "K" / "K11 资产减值损失.xlsx"
#: 与 `test_task37_excel_extract.TEMPLATE_SHA` 同一份权威字节。
TEMPLATE_SHA = "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190"
MANAGED_SHEET = "审定表K11-1"

#: 受管区域 = Excel Table `GT_K11_1_ROWS` 的 ref `A7:N25`。
MANAGED_FIRST_ROW = 7
MANAGED_LAST_ROW = 25
#: 合计行：`B26:G26` 是 `SUM(B7:B25)`，`H26` 是 `G26-D26`。**不是** 27
#: （27 行实测是纯文本标签行，`A27` 为 `t="s"`、B27..J27 全空）。
TOTAL_ROW = 26

#: sheet 上的行号区间，实测连续无缺口。
ROW_MIN, ROW_MAX = 1, 37

#: 以第 r 行为样式来源、插入点 r+1 时位移可安全执行的行集（实测 35 / 37）。
SAFE_STYLE_ROWS: tuple[int, ...] = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    21, 22, 23, 24, 25, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37,
)

#: 携带**横向**共享公式组成员的行 —— 新行继承它需要列平移，本 spec 只做行位移
#: ⇒ 必须 fail closed（si=3 `B26:G26`、si=5 `C28:G28`）。
HORIZONTAL_GROUP_ROWS: tuple[int, ...] = (26, 28)

#: si → (主格坐标, ref, 成员数, 主格公式文本)。实测形态，含纵向 / 横向 / 单格三种。
FROZEN_GROUPS: Mapping[int, tuple[str, str, int, str]] = {
    0: ("I7", "I7:I26", 1, "IF(AND(D7=0,G7=0),0,IF(AND(D7=0,G7&gt;0),1,H7/D7))"),
    1: ("H8", "H8:H25", 17, "G8-D8"),
    2: ("I8", "I8:I25", 17, "IF(AND(D8=0,G8=0),0,IF(AND(D8=0,G8&gt;0),1,H8/D8))"),
    3: ("B26", "B26:G26", 5, "SUM(B7:B25)"),
    4: ("H26", "H26", 0, "G26-D26"),
    5: ("C28", "C28:G28", 4, "C26-C27"),
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. fixture 与小工具
# ═══════════════════════════════════════════════════════════════════════════


def _managed_sheet_part(data: bytes) -> str:
    """受管 sheet 的 zip part —— 复用 `excel_structure_fingerprint` 的解析。

    🔴 不手搓正则：sheet 名含中文、`workbook.xml` 属性顺序不保证，手搓对
    B60 / H1 / G7 三个模板实测全部失败。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sheets, _ = parse_workbook_xml(zf)
    for sheet in sheets:
        if sheet["name"] == MANAGED_SHEET:
            return normalise_part(sheet["rel_target"])
    raise AssertionError(
        f"权威模板里找不到受管 sheet {MANAGED_SHEET!r}"
        f"（实测 {[s['name'] for s in sheets]}）—— fixture 已失效"
    )


@pytest.fixture(scope="module")
def template_bytes() -> bytes:
    assert TEMPLATE.is_file(), f"权威模板不存在: {TEMPLATE}"
    return TEMPLATE.read_bytes()


@pytest.fixture(scope="module")
def sheet_xml(template_bytes: bytes) -> str:
    part = _managed_sheet_part(template_bytes)
    with zipfile.ZipFile(io.BytesIO(template_bytes)) as zf:
        return zf.read(part).decode("utf-8")


_ROW_ATTR_RE = re.compile(r'<row\b[^>]*?\br="(\d+)"')
_CELL_ATTR_RE = re.compile(r'<c\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)', re.S)
_ROW_BLOCK_RE = re.compile(r"<row\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</row>)", re.S)
_COORD_RE = re.compile(r"^(?P<col>[A-Z]{1,3})(?P<row>\d+)$")


def _rows_of(xml: str) -> list[int]:
    return [int(value) for value in _ROW_ATTR_RE.findall(xml)]


def _row_block(xml: str, row: int) -> str:
    for match in _ROW_BLOCK_RE.finditer(xml):
        attrs = match.group("attrs") or ""
        found = re.search(r'\br="(\d+)"', attrs)
        if found and int(found.group(1)) == row:
            return match.group(0)
    raise AssertionError(f"XML 里没有第 {row} 行")


def _cells_of_row(xml: str, row: int) -> dict[str, dict[str, str | None]]:
    """`{列标: {"style": s, "body": 内容}}`。"""
    out: dict[str, dict[str, str | None]] = {}
    block = _row_block(xml, row)
    body = re.sub(r"^<row\b[^>]*>|</row>$", "", block)
    for cell in _CELL_ATTR_RE.finditer(body):
        attrs = cell.group("attrs") or ""
        coord = re.search(r'\br="([A-Z]{1,3}\d+)"', attrs)
        if coord is None:
            continue
        parsed = _COORD_RE.match(coord.group(1))
        assert parsed is not None
        style = re.search(r'\bs="([^"]*)"', attrs)
        out[parsed.group("col")] = {
            "style": style.group(1) if style else None,
            "body": cell.group("body"),
        }
    return out


def _orphan_members(xml: str) -> list[str]:
    """成员坐标落在自己组的 `ref` 行区间之外的清单。非空 = 产物不自洽。"""
    stray: list[str] = []
    for si, group in RS.shared_formula_groups(xml).items():
        first, last = group.ref_rows
        for coord in group.member_coords:
            parsed = _COORD_RE.match(coord)
            if parsed is None:
                continue
            if not (first <= int(parsed.group("row")) <= last):
                stray.append(f"si={si} {coord} 不在 ref={group.ref}")
    return stray


# ═══════════════════════════════════════════════════════════════════════════
# 2. 冻结事实
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenTemplateFacts:
    """模板事实先红，别的用例才不会莫名其妙地红。"""

    def test_authority_template_bytes_are_frozen(self, template_bytes: bytes) -> None:
        assert hashlib.sha256(template_bytes).hexdigest() == TEMPLATE_SHA, (
            "权威模板字节变了 —— 本文件的全部冻结事实都要重新实测，"
            "不得直接改 sha 让它变绿"
        )

    def test_row_range_is_contiguous(self, sheet_xml: str) -> None:
        rows = _rows_of(sheet_xml)
        assert rows == sorted(rows), "模板行号本来就不是升序 —— 位移判据无从建立"
        assert rows == list(range(ROW_MIN, ROW_MAX + 1)), rows[:12]

    def test_total_row_is_26_not_27(self, sheet_xml: str) -> None:
        """合计行是 26 —— 这条冻结的是一个**踩过的坑**。

        `test_task37_excel_extract.FOOTER_ROW = 27` 指的是 footer **anchor**
        （`A27` 的文本标签），不是带合计公式的行。首轮探针把 27 当合计行传进
        `total_formula_rows`，于是扩张分支一处都没执行、`extended` 恒 0，看起来
        像"扩张没实现"。
        """
        cells_26 = _cells_of_row(sheet_xml, 26)
        assert "SUM(B7:B25)" in (cells_26["B"]["body"] or ""), cells_26["B"]
        cells_27 = _cells_of_row(sheet_xml, 27)
        for col in "BCDEFGHIJ":
            assert "<f" not in (cells_27[col]["body"] or ""), (
                f"27 行 {col} 列出现公式 —— 模板变了，合计行的冻结事实需重新实测"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 1：清单与实现双向锁死（Task 4）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1ListedStructuresAreLockedToHandlers:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 1: 位移敏感清单与位移函数双向锁死**

    **Validates: Requirements 1.1, 1.5**
    """

    def test_handlers_cover_the_listed_structures(self) -> None:
        result = RS.assert_shift_handlers_cover_structures()
        handled = set(result["handled"])
        delegated = set(result["delegated"])

        declared = {f"{tag}{attr}" for tag, attr in RS.ROW_BEARING_STRUCTURES}
        assert declared == handled | delegated, (
            "清单与「处理 + 委派」两侧不等 —— 差集: "
            f"{sorted(declared ^ (handled | delegated))}"
        )
        assert not (handled & delegated), "同一项既自己处理又登记为委派 ⇒ 双重位移"
        # 分母断言：清单不是空集，也不是被悄悄削短了。
        # 15 = design.md §Data Model 的 12 项 + 全库实测后补入的 3 个「元素文本里的
        # A1 引用」（`formula` / `formula1` / `formula2`，见生产模块的实测表）。
        assert len(RS.ROW_BEARING_STRUCTURES) == 15, RS.ROW_BEARING_STRUCTURES
        assert delegated == {"table@ref"}, sorted(delegated)
        # `assert_shift_handlers_cover_structures` 的键是 `f"{tag}{attr}"`（无分隔符，
        # 与 `declared` 侧同构），所以 `("formula", "text-a1-ranges")` 拼出来是
        # `formulatext-a1-ranges` —— 上面的 `declared == handled | delegated` 已经逐项比过，
        # 这里再点名三项是为了让「补入 formula/formula1/formula2」这件事本身可 falsify。
        for tag in ("formula", "formula1", "formula2"):
            assert f"{tag}text-a1-ranges" in handled, (tag, sorted(handled))
            assert (tag, "text-a1-ranges") in RS.ROW_BEARING_STRUCTURES, tag

    def test_delegated_entries_each_carry_a_reason(self) -> None:
        """差集必须**逐项**写明由谁承接 —— 空理由等于注释掉一条清单项。"""
        assert RS.HANDLED_BY_IDENTITY_RETENTION_GATE, "差集登记表为空"
        for key, reason in RS.HANDLED_BY_IDENTITY_RETENTION_GATE.items():
            assert key in RS.ROW_BEARING_STRUCTURES, key
            assert len(reason) > 30, f"{key} 的承接理由过短: {reason!r}"

    def test_the_lock_is_not_vacuous(self) -> None:
        """反向自检：往清单里塞一项没人处理的结构 ⇒ 双向锁必须打红。

        直接改模块常量再还原（monkeypatch 语义），证明 `assert_shift_handlers_cover_structures`
        真的在比对，而不是恒返回成功。
        """
        original = RS.ROW_BEARING_STRUCTURES
        try:
            RS.ROW_BEARING_STRUCTURES = original + (("pivotArea", "@ref"),)  # type: ignore[misc]
            with pytest.raises(RS.UnlistedRowBearingStructureError, match="pivotArea"):
                RS.assert_shift_handlers_cover_structures()
        finally:
            RS.ROW_BEARING_STRUCTURES = original  # type: ignore[misc]
        # 还原后必须恢复通过 —— 否则本用例污染了后续用例
        RS.assert_shift_handlers_cover_structures()

    def test_real_template_has_no_unlisted_row_bearing_element(
        self, sheet_xml: str
    ) -> None:
        assert RS.scan_unlisted_row_bearing_elements(sheet_xml) == ()

    def test_unlisted_scan_is_not_vacuous(self, sheet_xml: str) -> None:
        """反向自检：注入一个既不在位移清单也不在无行号清单里的 tag ⇒ 必须被报出。"""
        injected = sheet_xml.replace(
            "</worksheet>", '<pivotArea ref="A1:B2"/></worksheet>'
        )
        assert "pivotArea" in RS.scan_unlisted_row_bearing_elements(injected)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 4：计划的零写入面与非法取值（Task 5.1）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeSession:
    """带 `commit` / `execute` 的形态对象 —— `assert_no_mutation_surface` 的靶子。"""

    def commit(self) -> None:  # pragma: no cover - 只作形态
        raise AssertionError("不该被调用")

    def execute(self, *_: object, **__: object) -> None:  # pragma: no cover
        raise AssertionError("不该被调用")


class TestProperty4PlanHasNoMutationSurface:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 4: `RowShiftPlan` 零写入面且非法取值各抛独立错误**

    **Validates: Requirements 2.2, 2.5, 3.6**
    """

    def test_session_shaped_argument_is_rejected(self) -> None:
        with pytest.raises(Exception) as excinfo:
            RowShift = RS.RowShiftPlan
            RowShift(insert_at=26, count=1, style_from=25, table_key=_FakeSession())  # type: ignore[arg-type]
        assert "RowShiftPlan" in str(excinfo.value) or "mutation" in str(
            excinfo.value
        ).lower(), str(excinfo.value)

    def test_the_three_illegal_shapes_raise_pairwise_distinct_error_codes(
        self, sheet_xml: str
    ) -> None:
        """design.md Property 4 点名的三类非法取值，`error_code` **两两不同**。

        三类的处置完全不同 —— `count<=0` 是调用方该传 `plan is None`；插入点越界是
        计划算错了；样式来源行缺失是模板/计划配不上。合并成一个 code 后它们在诊断里
        不可分辨，而「只断言抛了异常」的守卫对三条短路里的任意两条都判绿。
        """
        codes: dict[str, str] = {}

        with pytest.raises(RS.RowShiftPlanCountError) as count_err:
            RS.RowShiftPlan(insert_at=26, count=0, style_from=25)
        codes["count<=0"] = type(count_err.value).error_code

        with pytest.raises(RS.RowShiftPlanRangeError) as range_err:
            RS.RowShiftPlan(insert_at=0, count=1, style_from=25)
        codes["insert_at 越界"] = type(range_err.value).error_code

        # 样式来源行**缺失**只有在拿到真实 XML 时才可判 ⇒ 由 `shift_sheet_rows` 抛
        with pytest.raises(RS.RowShiftStyleSourceMissingError) as missing_err:
            RS.shift_sheet_rows(
                sheet_xml, RS.RowShiftPlan(insert_at=999, count=1, style_from=998)
            )
        codes["样式来源行缺失"] = type(missing_err.value).error_code

        assert len(set(codes.values())) == 3, codes

    def test_style_source_inside_the_new_row_range_is_rejected(self) -> None:
        """`style_from` 落在**新行区间内**也必须拒绝 —— 首版判据写成 `>= insert_at + count` 时漏过这一例。

        `insert_at=26, count=2, style_from=27`：27 正落在新行区间 26..27 里，
        从一个"还不存在的行"抄样式无法解释。
        """
        with pytest.raises(RS.RowShiftPlanRangeError, match="不小于插入点"):
            RS.RowShiftPlan(insert_at=26, count=2, style_from=27)
        # 合法的紧邻上一行仍必须通过 —— 否则判据从"太松"变成"太紧"
        RS.RowShiftPlan(insert_at=26, count=2, style_from=25)

    def test_negative_count_and_zero_count_are_both_rejected(self) -> None:
        for bad in (0, -1, -99):
            with pytest.raises(RS.RowShiftPlanCountError):
                RS.RowShiftPlan(insert_at=26, count=bad, style_from=25)

    @settings(max_examples=200, deadline=None)
    @given(
        insert_at=st.integers(min_value=2, max_value=500),
        count=st.integers(min_value=1, max_value=20),
    )
    def test_shift_and_unshift_are_inverse_above_the_insertion_point(
        self, insert_at: int, count: int
    ) -> None:
        """`unshift(shift(r)) == r` 对**任意** r >= 1 成立。

        以及新行区间的定义域边界：`unshift` 在新行上是**恒等映射**，于是新行会与
        before 侧同号的原始行别名 —— 这正是「新行不得进入需要归一化的集合」
        （Requirement 6.5）的真实理由。首版把理由写成"落回插入点之前"，被本条
        hypothesis 用例 `insert_at=2, count=1` 反证（`unshift(2) == 2`），
        生产模块的 docstring 同处已一并更正。
        """
        plan = RS.RowShiftPlan(insert_at=insert_at, count=count, style_from=insert_at - 1)
        for row in (1, insert_at - 1, insert_at, insert_at + count, insert_at + count + 7):
            if row < 1:
                continue
            assert plan.unshift(plan.shift(row)) == row, (row, plan.as_dict())
        assert list(plan.inserted_rows) == list(range(insert_at, insert_at + count))

        for new_row in plan.inserted_rows:
            # 恒等映射：新行 unshift 不动
            assert plan.unshift(new_row) == new_row, (new_row, plan.as_dict())
            # 且它落在 before 侧「原来有行」的号段里 ⇒ 会与原始行别名
            assert plan.shift(new_row) != new_row, (
                f"新行 {new_row} 的 shift 也是恒等 ⇒ 别名判据无从建立"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 6 / 7：纯函数与重编号（Task 6.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty6ShiftIsPure:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 6: 位移是纯函数**

    **Validates: Requirements 3.1**
    """

    def test_repeated_calls_are_byte_identical_and_input_untouched(
        self, sheet_xml: str
    ) -> None:
        original = sheet_xml
        plan = RS.RowShiftPlan(insert_at=26, count=3, style_from=25)
        first, report_a = RS.shift_sheet_rows(sheet_xml, plan)
        second, report_b = RS.shift_sheet_rows(sheet_xml, plan)
        assert first == second, "同输入两次调用产物不同 ⇒ 不是纯函数"
        assert report_a.as_dict() == report_b.as_dict()
        assert sheet_xml == original, "入参被改动了"
        assert first != original, "产物与入参相同 ⇒ 位移根本没执行"


class TestProperty7RenumberingIsExact:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 7: 插入点以下行号恰增 count，其余不变，升序无重复**

    **Validates: Requirements 3.3, 3.7**
    """

    @settings(max_examples=120, deadline=None)
    @given(
        style_from=st.sampled_from(SAFE_STYLE_ROWS),
        count=st.integers(min_value=1, max_value=4),
    )
    def test_row_numbers_shift_exactly(
        self, sheet_xml: str, style_from: int, count: int
    ) -> None:
        plan = RS.RowShiftPlan(
            insert_at=style_from + 1, count=count, style_from=style_from
        )
        after, report = RS.shift_sheet_rows(sheet_xml, plan)

        before_rows = _rows_of(sheet_xml)
        after_rows = _rows_of(after)

        assert after_rows == sorted(after_rows), "行号非升序"
        assert len(after_rows) == len(set(after_rows)), "行号有重复"
        assert len(after_rows) == len(before_rows) + count

        expected = sorted(
            [plan.shift(row) for row in before_rows] + list(plan.inserted_rows)
        )
        assert after_rows == expected, (after_rows[:8], expected[:8])

        # 格坐标与所在行一致（阶段 A 漏改 `<c r>` 时这里必红）
        for row in after_rows:
            for col, cell in _cells_of_row(after, row).items():
                block = _row_block(after, row)
                assert f'r="{col}{row}"' in block, (row, col)

        # ShiftReport 不是空转
        assert report.inserted_rows == count
        assert report.renumbered_rows == sum(
            1 for row in before_rows if row >= plan.insert_at
        )

    def test_style_source_row_missing_fails_closed(self, sheet_xml: str) -> None:
        plan = RS.RowShiftPlan(insert_at=999, count=1, style_from=998)
        with pytest.raises(RS.RowShiftStyleSourceMissingError, match="998"):
            RS.shift_sheet_rows(sheet_xml, plan)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 8：新行样式继承且无业务值（Task 6.1）
# ═══════════════════════════════════════════════════════════════════════════


def _assert_inserted_rows_inherit_styles(
    before: str, after: str, plan: RS.RowShiftPlan
) -> None:
    """判据本体，抽出来是为了能对它做反向自检（喂坏产物必须拒绝）。"""
    source = _cells_of_row(before, plan.style_from)
    assert source, f"样式来源行 {plan.style_from} 一个格都没有 ⇒ 判据会空转"
    for new_row in plan.inserted_rows:
        target = _cells_of_row(after, new_row)
        assert set(target) == set(source), (
            f"新行 {new_row} 的列集与样式来源行不一致: "
            f"{sorted(set(target) ^ set(source))}"
        )
        for col, cell in source.items():
            assert target[col]["style"] == cell["style"], (
                f"新行 {new_row} 的 {col} 列样式 {target[col]['style']!r} "
                f"≠ 来源行 {cell['style']!r}"
            )
        # row 级属性（高度 / customFormat / 行样式）同样继承
        source_attrs = re.sub(
            r'\br="\d+"', "", re.match(r"<row\b[^>]*", _row_block(before, plan.style_from)).group(0)
        )
        target_attrs = re.sub(
            r'\br="\d+"', "", re.match(r"<row\b[^>]*", _row_block(after, new_row)).group(0)
        )
        assert source_attrs == target_attrs, (source_attrs, target_attrs)


def _assert_inserted_rows_carry_no_business_value(
    after: str, plan: RS.RowShiftPlan
) -> None:
    for new_row in plan.inserted_rows:
        for col, cell in _cells_of_row(after, new_row).items():
            body = cell["body"] or ""
            assert "<v>" not in body, (
                f"新行 {new_row} 的 {col} 列带了业务值 {body!r} —— "
                "值应由随后的写格阶段按 projection 落入（Requirement 3.5）"
            )
            assert "<is>" not in body and "<t>" not in body, (new_row, col, body)


class TestProperty8InsertedRowsInheritStyleWithoutValues:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 8: 新插入行样式与来源行同列相等且无业务值**

    **Validates: Requirements 3.4, 3.5**
    """

    @settings(max_examples=120, deadline=None)
    @given(
        style_from=st.sampled_from(
            tuple(r for r in SAFE_STYLE_ROWS if MANAGED_FIRST_ROW <= r <= MANAGED_LAST_ROW)
        ),
        count=st.integers(min_value=1, max_value=3),
    )
    def test_styles_are_inherited_and_values_are_not(
        self, sheet_xml: str, style_from: int, count: int
    ) -> None:
        plan = RS.RowShiftPlan(
            insert_at=style_from + 1, count=count, style_from=style_from
        )
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)
        _assert_inserted_rows_inherit_styles(sheet_xml, after, plan)
        _assert_inserted_rows_carry_no_business_value(after, plan)

    def test_style_judgement_is_not_vacuous(self, sheet_xml: str) -> None:
        """反向自检：把新行的 `s=` 全抹掉 ⇒ 样式判据必须拒绝。

        对应 tasks.md Task 6.1 的「把样式继承改成 `style=""` ⇒ 本条必须打红」，
        但做法是喂坏**产物**而不是改生产源 —— 前者可在单测里复现，后者属 Task 20 变异脚本。
        """
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)
        _assert_inserted_rows_inherit_styles(sheet_xml, after, plan)  # 先证明本来是过的

        broken = after
        for new_row in plan.inserted_rows:
            block = _row_block(broken, new_row)
            broken = broken.replace(block, re.sub(r'\bs="[^"]*"', "", block), 1)
        with pytest.raises(AssertionError, match="样式"):
            _assert_inserted_rows_inherit_styles(sheet_xml, broken, plan)

    def test_value_judgement_is_not_vacuous(self, sheet_xml: str) -> None:
        """反向自检：给新行塞一个 `<v>` ⇒ 无业务值判据必须拒绝。"""
        plan = RS.RowShiftPlan(insert_at=26, count=1, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)
        _assert_inserted_rows_carry_no_business_value(after, plan)

        block = _row_block(after, 26)
        broken = after.replace(block, block.replace("/></row>", "><v>42</v></c></row>"), 1)
        with pytest.raises(AssertionError, match="业务值"):
            _assert_inserted_rows_carry_no_business_value(broken, plan)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 9：dimension 末行（Task 7）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9DimensionCoversActualMaxRow:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 9: 位移后 `dimension@ref` 末行不小于实际最大行号**

    **Validates: Requirements 3.8**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        style_from=st.sampled_from(SAFE_STYLE_ROWS),
        count=st.integers(min_value=1, max_value=5),
    )
    def test_dimension_last_row_is_not_below_max_row(
        self, sheet_xml: str, style_from: int, count: int
    ) -> None:
        plan = RS.RowShiftPlan(
            insert_at=style_from + 1, count=count, style_from=style_from
        )
        after, report = RS.shift_sheet_rows(sheet_xml, plan)

        found = re.search(r'<dimension\b[^>]*?\bref="([^"]+)"', after)
        assert found is not None, "产物丢了 <dimension> —— 阶段 F 把它删了"
        ref = found.group(1)
        tail = ref.split(":")[-1]
        parsed = _COORD_RE.match(tail)
        assert parsed is not None, ref
        assert int(parsed.group("row")) >= max(_rows_of(after)), (ref, max(_rows_of(after)))
        assert report.dimension_updated is True

    def test_other_ref_carrying_structures_move_with_their_rows(
        self, sheet_xml: str
    ) -> None:
        """受管区**之下**的 `mergeCell` 必须跟着走 —— K11 实测有 `E30:F30`。

        它是「位移敏感清单不能只覆盖受管区内」的活证人：漏了它，位移后合并区仍盖在
        旧行上，表格视觉错位而 verifier（补入 `mergeCells` 之前）一声不响。
        """
        merges_before = re.findall(r'<mergeCell ref="([^"]+)"', sheet_xml)
        assert any(
            (_COORD_RE.match(ref.split(":")[0]) or _COORD_RE.match("A1")).group("row")
            and int(_COORD_RE.match(ref.split(":")[0]).group("row")) > MANAGED_LAST_ROW
            for ref in merges_before
        ), f"模板里没有受管区之下的 mergeCell —— 本判据会空转: {merges_before}"

        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        after, report = RS.shift_sheet_rows(sheet_xml, plan)
        merges_after = re.findall(r'<mergeCell ref="([^"]+)"', after)

        assert len(merges_after) == len(merges_before)
        assert report.shifted_refs.get("mergeCell@ref", 0) >= 1, report.as_dict()
        for ref in merges_before:
            head = _COORD_RE.match(ref.split(":")[0])
            assert head is not None
            if int(head.group("row")) > MANAGED_LAST_ROW:
                assert ref not in merges_after, (
                    f"{ref} 在受管区之下却没被位移 —— 合并区会盖在旧行上"
                )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 10：si 索引（Task 8.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty10SharedFormulaIndexIsCorrect:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 10: `si` 索引对真实模板解析正确且主格成员可区分**

    **Validates: Requirements 4.1**
    """

    def test_index_matches_the_frozen_real_groups(self, sheet_xml: str) -> None:
        groups = RS.shared_formula_groups(sheet_xml)
        assert set(groups) == set(FROZEN_GROUPS), sorted(groups)
        for si, (master, ref, member_count, text) in FROZEN_GROUPS.items():
            group = groups[si]
            assert group.master_coord == master, (si, group.master_coord)
            assert group.ref == ref, (si, group.ref)
            assert len(group.member_coords) == member_count, (si, group.member_coords)
            assert group.master_text == text, (si, group.master_text)
            # 主格恰一个、且不在成员集合里 —— 两者可区分
            assert group.master_coord not in group.member_coords, si

    def test_vertical_and_horizontal_groups_are_both_present_and_classified(
        self, sheet_xml: str
    ) -> None:
        """分母断言：三种形态（纵向 / 横向 / 单格）都在，判据不在空集上恒真。"""
        groups = RS.shared_formula_groups(sheet_xml)
        vertical = {si for si, g in groups.items() if g.member_coords and g.is_vertical}
        horizontal = {
            si for si, g in groups.items() if g.member_coords and not g.is_vertical
        }
        single = {si for si, g in groups.items() if ":" not in g.ref}
        assert vertical == {0, 1, 2}, sorted(vertical)
        assert horizontal == {3, 5}, sorted(horizontal)
        assert single == {4}, sorted(single)

    def test_master_judgement_is_not_vacuous(self, sheet_xml: str) -> None:
        """反向自检：把主格的 `ref=` 摘掉 ⇒ 该组必须从索引里消失。

        对应 tasks.md Task 8.1 的「把主格判据改成"任何带 si 的都是主格" ⇒ 必须打红」：
        主格的判别依据是 `ref` 而不是 `si`，去掉 `ref` 后它退化成成员。
        """
        assert 1 in RS.shared_formula_groups(sheet_xml)
        broken = sheet_xml.replace('<f t="shared" ref="H8:H25" si="1">', '<f t="shared" si="1">', 1)
        assert broken != sheet_xml, "替换没命中 —— fixture 形态变了"
        groups = RS.shared_formula_groups(broken)
        assert 1 not in groups, "摘掉 ref 后仍被当成主格 ⇒ 主格判据用的是 si 不是 ref"

    def test_members_outside_master_ref_fail_closed_on_input(
        self, sheet_xml: str
    ) -> None:
        """入参本来就不自洽（成员在 ref 之外）⇒ 位移前就 fail closed。"""
        broken = sheet_xml.replace('ref="H8:H25"', 'ref="H8:H12"', 1)
        assert broken != sheet_xml
        plan = RS.RowShiftPlan(insert_at=26, count=1, style_from=25)
        with pytest.raises(RS.SharedFormulaSpanError, match="位移前"):
            RS.shift_sheet_rows(broken, plan)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 14：出口自洽 + 主格永不换字面量（Task 13 的成员继承裁决）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty14SharedFormulaStaysConsistent:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 14: 主格 `ref` 改写后成员跨度一致，且主格永不被替换成字面量**

    **Validates: Requirements 4.7, 4.8**

    本类守的是一个**已实测发生过**的缺陷：新插入行被做成共享公式成员，而主格
    `ref` 没扩到覆盖它们 ⇒ K11 上 4 个孤儿成员（H26/H27/I26/I27）。
    openpyxl 与 `structure_fingerprint` 都不校验这一点，所以"产物能打开"完全掩盖了它。
    """

    @settings(max_examples=120, deadline=None)
    @given(
        style_from=st.sampled_from(SAFE_STYLE_ROWS),
        count=st.integers(min_value=1, max_value=4),
    )
    def test_product_has_no_orphan_members(
        self, sheet_xml: str, style_from: int, count: int
    ) -> None:
        plan = RS.RowShiftPlan(
            insert_at=style_from + 1, count=count, style_from=style_from
        )
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)
        assert _orphan_members(after) == [], _orphan_members(after)

    def test_orphan_detector_is_not_vacuous(self, sheet_xml: str) -> None:
        """反向自检：手工把一个成员挪到组外 ⇒ 探测器必须报出来。"""
        assert _orphan_members(sheet_xml) == []
        broken = sheet_xml.replace('ref="H8:H25"', 'ref="H8:H20"', 1)
        stray = _orphan_members(broken)
        assert stray, "把 ref 收窄后仍报无孤儿 ⇒ 探测器恒真"
        assert any("si=1" in item for item in stray), stray

    def test_new_rows_get_standalone_formulas_translated_from_the_master(
        self, sheet_xml: str
    ) -> None:
        """新行不加入既有组，而是拿到从主格 fill-down 翻译来的**独立**公式。

        实测：si=1 主格 H8 文本 `G8-D8` ⇒ 新行 26 得 `G26-D26`；
        si=2 主格 I8 的 `IF(AND(D8=0,...),...,H8/D8)` ⇒ 新行 26 得 `...H26/D26`。
        """
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)

        for new_row in plan.inserted_rows:
            cells = _cells_of_row(after, new_row)
            h_body = cells["H"]["body"] or ""
            i_body = cells["I"]["body"] or ""
            assert f"<f>G{new_row}-D{new_row}</f>" == h_body, (new_row, h_body)
            assert 't="shared"' not in h_body, (new_row, h_body)
            assert 'si=' not in h_body, (new_row, h_body)
            assert f"H{new_row}/D{new_row}" in i_body, (new_row, i_body)
            assert 't="shared"' not in i_body, (new_row, i_body)

    def test_masters_are_never_replaced_by_literals(self, sheet_xml: str) -> None:
        """Requirement 4.8：位移前后主格集合一一对应，且每个主格仍带公式文本。"""
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan)

        before_groups = RS.shared_formula_groups(sheet_xml)
        after_groups = RS.shared_formula_groups(after)
        assert set(before_groups) == set(after_groups), (
            f"主格组数变了: {sorted(set(before_groups) ^ set(after_groups))} —— "
            "有主格被换成了字面量或被删"
        )
        for si, group in after_groups.items():
            assert group.master_text, f"si={si} 主格 {group.master_coord} 没有公式文本"
            expected_row = plan.shift(
                int(_COORD_RE.match(before_groups[si].master_coord).group("row"))
            )
            assert int(_COORD_RE.match(group.master_coord).group("row")) == expected_row, (
                si,
                before_groups[si].master_coord,
                group.master_coord,
            )

    @pytest.mark.parametrize("style_from", HORIZONTAL_GROUP_ROWS)
    def test_horizontal_group_style_source_fails_closed(
        self, sheet_xml: str, style_from: int
    ) -> None:
        """样式来源行携带**横向**组成员 ⇒ fail closed，不猜列偏移。

        K11 实测：26 行是 si=3（`B26:G26`）、28 行是 si=5（`C28:G28`）。继承它们
        需要把主格公式按**列**平移，而本 spec 只做行位移；猜一个列偏移会产出一张
        每格都算错的表。
        """
        plan = RS.RowShiftPlan(
            insert_at=style_from + 1, count=1, style_from=style_from
        )
        with pytest.raises(RS.SharedFormulaOrientationError, match="横向组"):
            RS.shift_sheet_rows(sheet_xml, plan)

    def test_orientation_error_code_is_distinct(self) -> None:
        codes = {
            RS.RowShiftPlanCountError.error_code,
            RS.RowShiftPlanRangeError.error_code,
            RS.RowShiftStyleSourceMissingError.error_code,
            RS.UnlistedRowBearingStructureError.error_code,
            RS.SharedFormulaSpanError.error_code,
            RS.SharedFormulaOrientationError.error_code,
        }
        assert len(codes) == 6, sorted(codes)


# ═══════════════════════════════════════════════════════════════════════════
# 10. 合计扩张的门（Task 13 第二条：扩张只在契约声明时发生）
# ═══════════════════════════════════════════════════════════════════════════


class TestTotalFormulaExtensionIsGated:
    """合计区间扩张**只**在调用方声明合计行时发生（Requirement 4.6 的位移函数侧）。

    这条是**对照实证**而不是"跑通"：同一份输入、同一个计划，只改
    `total_formula_rows` 一个参数，比对两侧产物。
    """

    def test_declared_total_row_extends_the_range(self, sheet_xml: str) -> None:
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)

        gated, gated_report = RS.shift_sheet_rows(sheet_xml, plan)
        declared, declared_report = RS.shift_sheet_rows(
            sheet_xml, plan, total_formula_rows=(TOTAL_ROW,)
        )

        # 未声明 ⇒ 合计区间逐字不变（只位移主格 ref 与所在行）
        assert "SUM(B7:B25)" in _cells_of_row(gated, 28)["B"]["body"]
        assert gated_report.extended_shared_formulas == 0, gated_report.as_dict()

        # 声明 ⇒ 末行 +count，恰好覆盖新插入的 26/27 行
        assert "SUM(B7:B27)" in _cells_of_row(declared, 28)["B"]["body"]
        assert declared_report.extended_shared_formulas == 1, declared_report.as_dict()

    def test_extension_count_is_measured_not_declared(self, sheet_xml: str) -> None:
        """`extended_shared_formulas` 是**实测**处数，不是「主格行号 ∈ total_rows」的推算。

        K11 合计行 26 上有两个主格：si=3 的 `SUM(B7:B25)`（真扩张）与 si=4 的
        `G26-D26`（只是纯位移到 `G28-D28`）。按声明推会报 2，把纯位移误记成扩张 ⇒
        报告本身成了假绿的帮凶。
        """
        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        _, report = RS.shift_sheet_rows(
            sheet_xml, plan, total_formula_rows=(TOTAL_ROW,)
        )
        masters_on_total_row = [
            si
            for si, g in RS.shared_formula_groups(sheet_xml).items()
            if int(_COORD_RE.match(g.master_coord).group("row")) == TOTAL_ROW
        ]
        assert len(masters_on_total_row) == 2, masters_on_total_row
        assert report.extended_shared_formulas == 1, (
            "扩张处数等于合计行上的主格数 ⇒ 是按声明推的，不是实测的"
        )

    def test_cross_sheet_references_on_existing_rows_stay_verbatim(
        self, sheet_xml: str
    ) -> None:
        """**既有行**上的跨 sheet 引用逐字不动 —— 本 sheet 插行不改变别的 sheet 的行号。

        `'明细表K11-2'!F29` 必须一个字符都不动。表名里的 `K11` 被当成「K 列第 11 行」
        位移成 `K12` 会让公式指向一个不存在的 sheet，当场死掉（全库实测表名形如
        A1 引用的达 16,027 次）。

        ⚠ 本条只管**既有行**。新插入行的跨 sheet 引用**会**随行平移，见
        :meth:`test_cross_sheet_references_on_inserted_rows_are_translated`。
        两者不是矛盾而是两个不同的语义：既有行是「格没搬、别的表也没动」⇒ 不动；
        新行是「公式被复制到别的行」⇒ 相对引用随之平移（Excel 填充柄语义）。

        分母断言：模板上真有 >= 20 处跨 sheet 引用，否则判据空转。
        """
        cross = re.findall(r"'[^']+'!\$?[A-Z]{1,3}\$?\d+", sheet_xml)
        assert len(cross) >= 20, f"模板跨 sheet 引用过少，判据会空转: {len(cross)}"

        plan = RS.RowShiftPlan(insert_at=26, count=2, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan, total_formula_rows=(TOTAL_ROW,))

        checked = 0
        for row in (7, 15, plan.style_from):
            before_refs = _cross_refs_of_row(sheet_xml, row)
            if not before_refs:
                continue
            # 位移后该行的新行号：`< insert_at` 的行原地不动
            assert row < plan.insert_at, row
            assert _cross_refs_of_row(after, row) == before_refs, (
                f"既有行 {row} 上的跨 sheet 引用被改动了 —— 本 sheet 插行不该动别的 "
                f"sheet 的行号：\n  改前 {before_refs}\n  改后 {_cross_refs_of_row(after, row)}"
            )
            checked += 1
        assert checked >= 2, f"只核到 {checked} 行既有跨 sheet 引用，判据偏弱"

    def test_cross_sheet_references_on_inserted_rows_are_translated(
        self, sheet_xml: str
    ) -> None:
        """**新插入行**的跨 sheet 相对引用随行平移（AC 10.1 / Property 37）。

        ═══ 本判据的来历 ═══

        它的前身断言的是**相反**的行为 —— 「新插入行照抄样式来源行的跨 sheet 引用」，
        并把那条登记为已知限制、明写「交 `excel-workbook-wide-row-change-propagation`
        承接」。2026-09-05 该 spec 的 Task 27 落地后按此翻转。

        ═══ 修掉的缺陷是什么 ═══

        照抄导致新行 26/27 与来源行 25 指向**同一个源格**（都取 `F29`）⇒ 静默重复取数。
        Excel 填充柄的真实语义是相对引用随行平移：来源行 25 的 `F29`，到新行 26 应为
        `F30`、到新行 27 应为 `F31`。

        最隐蔽的形态是混合公式 `='明细表K11-2'!F29+G25` —— 修之前裸引用 `G25` 平移了、
        跨 sheet 的 `F29` 没平移，同一条公式里两个引用的行语义不一致，比统一不平移更难
        发现。所以本条按**每个新行的偏移量**逐行核对，而不是只看「变了没变」。
        """
        count = 2
        plan = RS.RowShiftPlan(insert_at=26, count=count, style_from=25)
        after, _ = RS.shift_sheet_rows(sheet_xml, plan, total_formula_rows=(TOTAL_ROW,))

        source_refs = _cross_refs_of_row(sheet_xml, plan.style_from)
        assert source_refs, "样式来源行没有跨 sheet 引用 ⇒ 本条空转"

        ref_re = re.compile(r"(?P<sheet>'[^']+')!(?P<col>\$?[A-Z]{1,3})(?P<abs>\$?)(?P<row>\d+)")
        for new_row in plan.inserted_rows:
            delta = new_row - plan.style_from
            got = _cross_refs_of_row(after, new_row)
            assert len(got) == len(source_refs), (
                f"新行 {new_row} 的跨 sheet 引用条数与来源行不同："
                f"{len(got)} vs {len(source_refs)}"
            )
            for src, dst in zip(source_refs, got):
                m_src, m_dst = ref_re.fullmatch(src), ref_re.fullmatch(dst)
                assert m_src and m_dst, (src, dst)
                assert m_dst.group("sheet") == m_src.group("sheet"), (
                    f"平移把表名改了：{src} → {dst} —— 表名里的「字母+数字」被当成坐标了"
                )
                assert m_dst.group("col") == m_src.group("col"), (
                    f"平移动了列：{src} → {dst}（fill-down 只该动行）"
                )
                if m_src.group("abs"):
                    # `$` 锁定的绝对行不平移（AC 10.2）
                    assert m_dst.group("row") == m_src.group("row"), (
                        f"绝对行被平移了（AC 10.2）：{src} → {dst}"
                    )
                else:
                    want = int(m_src.group("row")) + delta
                    assert int(m_dst.group("row")) == want, (
                        f"新行 {new_row}（距来源行 {delta} 行）的相对引用未按偏移平移："
                        f"{src} → {dst}，期望行号 {want}。"
                        "照抄来源行会让新行与来源行读同一个源格 = 静默重复取数（AC 10.1）"
                    )

        # 🔴 反面对照：两个新行的引用**必须互不相同**，否则就是照抄
        first, second = (
            _cross_refs_of_row(after, r) for r in list(plan.inserted_rows)[:2]
        )
        assert first != second, (
            "两个新插入行的跨 sheet 引用完全相同 —— 说明是照抄样式来源行而非按行平移。"
            f"\n  新行 {plan.insert_at}: {first}\n  新行 {plan.insert_at + 1}: {second}"
        )


def _cross_refs_of_row(xml: str, row: int) -> list[str]:
    return re.findall(r"'[^']+'!\$?[A-Z]{1,3}\$?\d+", _row_block(xml, row))
