# -*- coding: utf-8 -*-
"""G9-2 列同构判据 —— 堵住「猜测映射」。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5
　　　设计依据 `evidence/task8-template-design-logic.md`

═══ 为什么必须有这组判据 ═══

既有判据只校验「**声明与模板几何**一致」（行号 / 列字母 / 公式列），
**不校验**「前端字段语义与模板列语义一致」。Task 8 实测发现的阻塞正是后者：
G9 模板 28 列的骨架是「成本 / 累计公允价值变动 / 公允价值」三联，而改造前的前端是
单值列 + 10 列基本信息 —— `28 == 28` 纯属巧合（3 列真对上 + 15 列前端独有 + 11 列模板独有）。
在那种状态下硬凑一套映射会**通过全部既有判据**却把 A 列的值写进 B 列。

本组判据三层闭环：
  ① provider 的 `header_text` 逐列 == **模板逐格实测值**（模板是权威）
  ② provider 的 `json_key` 集合 == **前端行接口字段**集合（前端与声明不得脱钩）
  ③ 三区过滤（`row_section_field`）读写成对 —— 读得出、且写回落对区
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.phase5_g9_02_detail import (  # noqa: E402
    ALL_SPECS_G902,
    FIELD_SPECS_G902,
    FORMULA_COLUMNS_G902,
    FORMULA_TEMPLATES_G902,
    GRAND_TOTAL_ROW_G902,
    MANAGED_SHEET_G902,
    SECTION_TITLE_ROWS_G902,
    SPEC_G902_R1,
    STORE_ITEM_ID_G902,
    SUBTOTAL_ROWS_G902,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    iter_store_rows,
    merge_projection_into_store_rows,
)

TPL = _BACKEND / "wp_templates" / "G" / "G9 其他非流动金融资产.xlsx"
FE_COMPOSABLE = (
    _REPO / "audit-platform/frontend/src/components/workpaper/composables/useG9Detail.ts"
)

#: 前端行接口里**不受管**的字段（身份 / 显示序号 / 区归属）
_NON_MANAGED_FE_FIELDS = {"rowId", "seq", "section"}


@pytest.fixture(scope="module")
def ws():
    wb = openpyxl.load_workbook(TPL, data_only=False)
    try:
        yield wb[MANAGED_SHEET_G902]
    finally:
        wb.close()


def _frontend_row_fields() -> list[str]:
    """按值抠出 `useG9Detail.G9DetailRow` 的字段名（顺序即声明顺序）。"""
    src = FE_COMPOSABLE.read_text(encoding="utf-8")
    m = re.search(r"export interface G9DetailRow \{(?P<body>.*?)\n\}", src, re.S)
    assert m, "找不到 G9DetailRow 接口 —— 前端结构变了，判据须改写"
    out: list[str] = []
    for line in m.group("body").splitlines():
        fm = re.match(r"\s*(\w+)\??:", line)
        if fm:
            out.append(fm.group(1))
    return out


# ════════════════════════════════════════════════════════════════════════════
# ① header_text 逐列 == 模板逐格实测（模板是权威，FC-5）
# ════════════════════════════════════════════════════════════════════════════
class TestHeaderTextMatchesTemplateCellByCell:
    def test_28_columns_in_excel_order_a_to_ab(self) -> None:
        from openpyxl.utils import get_column_letter

        cols = [f[1] for f in FIELD_SPECS_G902]
        assert cols == [get_column_letter(i) for i in range(1, 29)], (
            f"列序必须是 A..AB 连续 28 列，实得 {cols}"
        )

    @pytest.mark.parametrize("field", FIELD_SPECS_G902, ids=[f[1] for f in FIELD_SPECS_G902])
    def test_header_text_equals_template_cell(self, field, ws) -> None:
        """两级表头：跨两行合并的单列取 R9，分组列取叶子行 R10。"""
        from openpyxl.utils import column_index_from_string

        _key, col, _mode, _vt, _json_key, header_text, group_cell = field
        ci = column_index_from_string(col)
        leaf = ws.cell(row=10, column=ci).value
        group = ws.cell(row=9, column=ci).value
        expect = str(leaf).strip() if (leaf and str(leaf).strip()) else str(group or "").strip()
        assert header_text == expect, (
            f"{col} 列 header_text 实得 {header_text!r}，模板逐格为 {expect!r}"
            f"（R9={group!r} / R10={leaf!r}）"
        )
        # 分组列必须声明 group_header_cell，跨两行的单列必须为空
        if leaf and str(leaf).strip():
            assert group_cell, f"{col} 是分组列（R10 有叶子标题）却未声明 group_header_cell"
        else:
            assert group_cell == "", f"{col} 跨两行合并却声明了 group_header_cell={group_cell!r}"

    def test_group_header_cells_point_at_real_merged_group_starts(self, ws) -> None:
        """每个 `group_header_cell` 必须是模板里真实的一级分组合并区起始格。"""
        starts = {
            f"{rng.coord.split(':')[0]}"
            for rng in ws.merged_cells.ranges
            if rng.min_row == 9 and rng.max_row == 9 and rng.max_col > rng.min_col
        }
        declared = {f[6] for f in FIELD_SPECS_G902 if f[6]}
        assert declared == starts, (
            f"声明的分组起始格 {sorted(declared)} 与模板 R9 横向合并区 {sorted(starts)} 不一致"
        )
        # 实测应恰为七组：期初余额/期初账项调整/期初审定数/本期变动/期末余额/账项调整/期末审定数
        assert len(starts) == 7, f"一级分组实得 {len(starts)} 组"


# ════════════════════════════════════════════════════════════════════════════
# ② json_key 集合 == 前端行接口字段集合（声明与前端不得脱钩）
# ════════════════════════════════════════════════════════════════════════════
class TestJsonKeysMatchFrontendRowInterface:
    def test_declared_json_keys_equal_frontend_managed_fields(self) -> None:
        """🔴 本组判据的核心：**双向**相等，不是单向包含。

        - 前端多出字段 ⇒ 有列没被受管（OO 侧编辑会丢）
        - 声明多出字段 ⇒ 指向前端不存在的键（投影恒空）
        """
        declared = {f[4] for f in FIELD_SPECS_G902}
        frontend = set(_frontend_row_fields()) - _NON_MANAGED_FE_FIELDS
        assert declared == frontend, (
            "声明的 json_key 与前端 G9DetailRow 字段必须**双向相等**。\n"
            f"  前端有而声明缺：{sorted(frontend - declared)}\n"
            f"  声明有而前端缺：{sorted(declared - frontend)}"
        )
        assert len(declared) == 28

    def test_frontend_field_order_matches_excel_column_order(self) -> None:
        """前端字段声明顺序 ≡ 模板列序（A..AB）—— 顺序一致才能逐列人工核对。"""
        fe = [f for f in _frontend_row_fields() if f not in _NON_MANAGED_FE_FIELDS]
        declared = [f[4] for f in FIELD_SPECS_G902]
        assert fe == declared, (
            "前端字段顺序应与模板列序一致（便于逐列核对）。\n"
            f"  前端：{fe}\n  声明：{declared}"
        )

    def test_row_identity_and_section_are_not_managed_columns(self) -> None:
        """`rowId` / `seq` / `section` 都不是受管列（它们不占模板的任何一列）。"""
        declared = {f[4] for f in FIELD_SPECS_G902}
        for f in _NON_MANAGED_FE_FIELDS:
            assert f not in declared, f"{f} 不应出现在 field_specs 里"
        assert SPEC_G902_R1.row_identity_key == "rowId"
        assert SPEC_G902_R1.row_section_field == "section"


# ════════════════════════════════════════════════════════════════════════════
# ③ 公式列与模板公式逐条一致（含「未审线」）
# ════════════════════════════════════════════════════════════════════════════
class TestFormulaColumnsMatchTemplate:
    def test_formula_columns_are_exactly_the_template_formula_cells(self, ws) -> None:
        from openpyxl.utils import get_column_letter

        actual = tuple(
            get_column_letter(c)
            for c in range(1, ws.max_column + 1)
            if isinstance(ws.cell(row=12, column=c).value, str)
            and str(ws.cell(row=12, column=c).value).startswith("=")
        )
        assert FORMULA_COLUMNS_G902 == actual, (
            f"公式列声明 {FORMULA_COLUMNS_G902} 与模板 R12 实测 {actual} 不一致"
        )
        assert len(FORMULA_COLUMNS_G902) == 12
        # 🔴 与几何近同构的 G1-2 区① 多一个跨表 T 列；G9 **无 T**
        assert "T" not in FORMULA_COLUMNS_G902

    @pytest.mark.parametrize("col", sorted(FORMULA_TEMPLATES_G902))
    def test_formula_template_renders_to_the_template_cell(self, col: str, ws) -> None:
        from openpyxl.utils import column_index_from_string

        for row in (12, 19, 26):  # 三区各首行
            got = ws.cell(row=row, column=column_index_from_string(col)).value
            assert got == FORMULA_TEMPLATES_G902[col].format(r=row), (
                f"{col}{row} 模板实得 {got!r}，声明渲染为 "
                f"{FORMULA_TEMPLATES_G902[col].format(r=row)!r}"
            )

    def test_closing_balance_rolls_from_unaudited_line(self) -> None:
        """🔴 `P=C+M` / `Q=D+N` 走**未审线** —— 不得是 `P=H+M`（审定线）。

        这条钉住模板的核心设计意图（被审计单位账面一条线、审计调整一条线）。
        """
        assert FORMULA_TEMPLATES_G902["P"] == "=C{r}+M{r}"
        assert FORMULA_TEMPLATES_G902["Q"] == "=D{r}+N{r}"
        assert "H" not in FORMULA_TEMPLATES_G902["P"]
        assert "I" not in FORMULA_TEMPLATES_G902["Q"]

    def test_three_component_identities(self) -> None:
        """公允价值 = 成本 + 累计公允价值变动，四处重复。"""
        assert FORMULA_TEMPLATES_G902["E"] == "=C{r}+D{r}"
        assert FORMULA_TEMPLATES_G902["J"] == "=H{r}+I{r}"
        assert FORMULA_TEMPLATES_G902["R"] == "=P{r}+Q{r}"
        assert FORMULA_TEMPLATES_G902["W"] == "=U{r}+V{r}"

    def test_dividend_column_o_is_not_in_any_balance_formula(self) -> None:
        """O 列（计入投资收益的股息）是损益项，不参与任何余额公式。"""
        assert "O" not in FORMULA_COLUMNS_G902
        for col, tpl in FORMULA_TEMPLATES_G902.items():
            assert "O{r}" not in tpl, f"{col} 的公式引用了 O 列：{tpl}"


# ════════════════════════════════════════════════════════════════════════════
# ④ 三区几何：区标题行 / 小计行 / 合计行都不在受管区
# ════════════════════════════════════════════════════════════════════════════
class TestThreeSectionGeometry:
    def test_three_specs_share_sheet_key_and_store_item_but_differ_per_section(self) -> None:
        assert len({s.sheet_key for s in ALL_SPECS_G902}) == 1, "三区必须共享单一 sheet_key"
        assert {s.store_item_id for s in ALL_SPECS_G902} == {STORE_ITEM_ID_G902}
        assert len({s.table_key for s in ALL_SPECS_G902}) == 3
        assert len({s.uuid_col for s in ALL_SPECS_G902}) == 3
        assert [s.row_section_value for s in ALL_SPECS_G902] == [
            "main", "mandatory_fvtpl", "designated_fvtpl",
        ]

    def test_data_regions_match_template_and_exclude_title_subtotal_total_rows(self) -> None:
        regions = [(s.first_data_row, s.last_data_row) for s in ALL_SPECS_G902]
        assert regions == [(12, 16), (19, 23), (26, 28)]
        managed = {r for a, b in regions for r in range(a, b + 1)}
        for row in (*SECTION_TITLE_ROWS_G902, *SUBTOTAL_ROWS_G902, GRAND_TOTAL_ROW_G902):
            assert row not in managed, f"R{row}（区标题/小计/合计）不得落在受管区内"

    def test_section_title_rows_carry_text_without_formula(self, ws) -> None:
        for row, expect in zip(
            SECTION_TITLE_ROWS_G902,
            (
                "其他非流动金融资产",
                "划分为以公允价值计量且其变动计入当期损益的金融资产",
                "指定为以公允价值计量且其变动计入当期损益的金融资产",
            ),
        ):
            assert ws.cell(row=row, column=1).value == expect
            has_formula = any(
                isinstance(ws.cell(row=row, column=c).value, str)
                and str(ws.cell(row=row, column=c).value).startswith("=")
                for c in range(1, ws.max_column + 1)
            )
            assert not has_formula, f"R{row} 是区标题行，不应有公式"

    def test_subtotal_rows_are_sum_of_their_own_region(self, ws) -> None:
        for (first, last), sub in zip(
            [(s.first_data_row, s.last_data_row) for s in ALL_SPECS_G902], SUBTOTAL_ROWS_G902
        ):
            assert ws[f"C{sub}"].value == f"=SUM(C{first}:C{last})"

    def test_grand_total_is_enumerated_sum_of_three_subtotals(self, ws) -> None:
        """合计行是**枚举相加** `=SUM(C17,C24,C29)`，不是区间 SUM（插行位移规则不同）。"""
        got = ws[f"C{GRAND_TOTAL_ROW_G902}"].value
        assert got == "=SUM(C17,C24,C29)", f"合计行实得 {got!r}"
        assert ":" not in got, "合计行不得是区间 SUM"


# ════════════════════════════════════════════════════════════════════════════
# ⑤ 三区过滤读写成对（引擎 `row_section_field`）
# ════════════════════════════════════════════════════════════════════════════
class TestSectionFilterReadWritePairing:
    PAYLOAD = [
        {"rowId": "a1", "section": "main", "investTarget": "甲"},
        {"rowId": "b1", "section": "mandatory_fvtpl", "investTarget": "乙"},
        {"rowId": "b2", "section": "mandatory_fvtpl", "investTarget": "丙"},
        {"rowId": "c1", "section": "designated_fvtpl", "investTarget": "丁"},
    ]

    def test_each_spec_reads_only_its_own_section(self) -> None:
        got = {
            s.row_section_value: [rid for rid, _row in iter_store_rows(s, self.PAYLOAD)]
            for s in ALL_SPECS_G902
        }
        assert got == {
            "main": ["a1"],
            "mandatory_fvtpl": ["b1", "b2"],
            "designated_fvtpl": ["c1"],
        }

    def test_duplicate_identity_check_is_scoped_to_the_section(self) -> None:
        """🔴 过滤必须在重复身份校验**之前**：否则三段读同一数组时，
        每段都会把另两段的行算进 `seen`，第二段起必然误报「重复行身份」。
        """
        for s in ALL_SPECS_G902:
            list(iter_store_rows(s, self.PAYLOAD))  # 不抛即通过

    def test_duplicate_within_the_same_section_still_fails_closed(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import RowTableStorePayloadError

        dup = [
            {"rowId": "x", "section": "main"},
            {"rowId": "x", "section": "main"},
        ]
        with pytest.raises(RowTableStorePayloadError, match="重复行身份"):
            list(iter_store_rows(SPEC_G902_R1, dup))

    def test_merge_stamps_section_on_newly_inserted_rows(self) -> None:
        """OO 侧在区② 插的新行，回写时必须带上 `section='mandatory_fvtpl'`。"""

        class _FV:
            def __init__(self, key: str, row_key: str, value):
                self.stable_key = key
                self.row_key = row_key
                self.value = value
                self.is_protected = False

        spec = ALL_SPECS_G902[1]  # 区②
        new_key = f"{spec.table_key}/newrow/invest_target"

        class _Proj:
            def stable_keys(self):
                return [new_key]

            def get(self, key):
                return _FV(key, "newrow", "OO侧新增") if key == new_key else None

        rows, applied, _visited, touched = merge_projection_into_store_rows(
            spec, projection=_Proj(), base_rows=list(self.PAYLOAD)
        )
        assert applied == 1 and touched == {"newrow"}
        added = next(r for r in rows if r["rowId"] == "newrow")
        assert added["section"] == "mandatory_fvtpl", (
            f"新增行未盖上区归属，实得 {added!r} —— 它回到前端会落进默认区"
        )
        assert added["investTarget"] == "OO侧新增"
        # 其它区的行原样保留（本函数按 identity 索引，不属本区的行不受影响）
        assert {r["rowId"] for r in rows} == {"a1", "b1", "b2", "c1", "newrow"}

    def test_existing_rows_keep_their_own_section_on_merge(self) -> None:
        """已有行的 `section` 不被 merge 覆盖（只有新增行才盖）。"""

        class _Proj:
            def stable_keys(self):
                return []

            def get(self, key):
                return None

        spec = ALL_SPECS_G902[0]
        rows, applied, _v, _t = merge_projection_into_store_rows(
            spec, projection=_Proj(), base_rows=list(self.PAYLOAD)
        )
        assert applied == 0
        assert [r["section"] for r in rows] == [
            "main", "mandatory_fvtpl", "mandatory_fvtpl", "designated_fvtpl",
        ]

    def test_filter_is_opt_in_so_existing_providers_are_untouched(self) -> None:
        """`row_section_field` 为空时不过滤 —— 既有 provider 行为逐字不变。"""
        from dataclasses import replace

        plain = replace(SPEC_G902_R1, row_section_field="", row_section_value="")
        assert [rid for rid, _ in iter_store_rows(plain, self.PAYLOAD)] == [
            "a1", "b1", "b2", "c1",
        ]
