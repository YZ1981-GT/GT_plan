# -*- coding: utf-8 -*-
"""G1-2 列同构判据 —— 五层闭环。

spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13（九条最后一条）

═══ G1 与 G9 的唯一结构差异 ═══

G9 三区公式列完全相同 → 共用一份 `formula_columns`。
G1 区① 有跨表 `T` 列公式（引 `公允价值测试表G1-6!H10..H14`），区②③ 的 T **整格无公式**。
⇒ 区① 公式列 **13** 个、区②③ **12** 个，差集恰 `{T}`。

判据在 ③ 里对此**逐格比对**（含跨表公式逐行）。
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

from app.services.workpaper_sync.phase5_g1_02_detail import (  # noqa: E402
    ALL_SPECS_G102,
    BOOLEAN_COLUMNS_G102,
    FIELD_SPECS_G102,
    FORMULA_COLUMNS_R1_G102,
    FORMULA_COLUMNS_R23_G102,
    FORMULA_TEMPLATES_G102,
    FRONTEND_ONLY_FIELDS_G102,
    GRAND_TOTAL_ROW_G102,
    MANAGED_SHEET_G102,
    ROW_SECTION_FIELD_G102,
    SECTION_TITLE_ROWS_G102,
    SPEC_G102_R1,
    SPEC_G102_R2,
    SPEC_G102_R3,
    STORE_ITEM_ID_G102,
    SUBTOTAL_ROWS_G102,
    TEMPLATE_CROSS_SHEET_FORMULAS_G102,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    iter_store_rows,
    merge_projection_into_store_rows,
)

TPL = _BACKEND / "wp_templates" / "G" / "G1 交易性金融资产.xlsx"
FE_COMPOSABLE = (
    _REPO
    / "audit-platform/frontend/src/components/workpaper/composables/useG1Detail.ts"
)

#: 前端行接口里**不受管**的字段
_NON_MANAGED_FE_FIELDS: frozenset[str] = frozenset(FRONTEND_ONLY_FIELDS_G102)


@pytest.fixture(scope="module")
def ws():
    wb = openpyxl.load_workbook(TPL, data_only=False)
    try:
        yield wb[MANAGED_SHEET_G102]
    finally:
        wb.close()


def _frontend_row_fields() -> list[str]:
    """按值抠出 `useG1Detail.TradingDetailRow` 的字段名（顺序即声明顺序）。"""
    src = FE_COMPOSABLE.read_text(encoding="utf-8")
    m = re.search(
        r"export interface TradingDetailRow \{(?P<body>.*?)\n\}", src, re.S
    )
    assert m, "找不到 TradingDetailRow 接口 —— 前端结构变了，判据须改写"
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
    def test_27_columns_in_excel_order_a_to_aa(self) -> None:
        """有效列 27 个（A..AA），max_column=35 但尾 8 列空。"""
        from openpyxl.utils import get_column_letter

        cols = [f[1] for f in FIELD_SPECS_G102]
        assert cols == [get_column_letter(i) for i in range(1, 28)]
        assert len(cols) == 27

    @pytest.mark.parametrize(
        "field", FIELD_SPECS_G102, ids=[f[1] for f in FIELD_SPECS_G102]
    )
    def test_header_text_equals_template_cell(self, field, ws) -> None:
        """两级表头：跨两行合并的单列取 R9，分组列取叶子行 R10。"""
        from openpyxl.utils import column_index_from_string

        _name, col, _mode, _vtype, _jk, header_text, group_cell = field
        ci = column_index_from_string(col)
        # 先试叶子行 R10
        leaf = ws.cell(row=10, column=ci).value
        if leaf is not None:
            assert str(leaf).strip() == header_text, (
                f"列 {col} 叶子行 R10 文本不匹配"
            )
        else:
            # 纵向合并列取 R9
            group = ws.cell(row=9, column=ci).value
            assert group is not None, f"列 {col} 在 R9/R10 均为 None"
            assert str(group).strip() == header_text, (
                f"列 {col} 分组行 R9 文本不匹配"
            )

        # group_header_cell 空 → 纵向合并列（R9:R10 连续合并）
        if group_cell == "":
            # 此列应是纵向合并：R10 无值
            assert leaf is None or str(leaf).strip() == header_text, (
                f"列 {col} 声明为纵向合并列但 R10 有独立叶子值"
            )

    def test_group_header_cells_point_at_real_merged_group_starts(self, ws) -> None:
        """每个 `group_header_cell` 必须是模板里真实的一级分组合并区起始格。"""
        starts = {
            f[6] for f in FIELD_SPECS_G102 if f[6] != ""
        }
        for cell_ref in starts:
            cell = ws[cell_ref]
            assert cell.value is not None, (
                f"group_header_cell={cell_ref} 在模板里是空格"
            )

    def test_horizontal_group_count_is_7(self, ws) -> None:
        """两级表头有 7 个横向分组合并区（C9:E9 F9:G9 H9:J9 M9:O9 P9:R9 S9:T9 U9:W9）。"""
        groups = sorted({f[6] for f in FIELD_SPECS_G102 if f[6] != ""})
        assert len(groups) == 7

    def test_vertical_merge_count_is_8(self) -> None:
        """纵向合并列 8 个（A B K L X Y Z AA），group_header_cell 全空。"""
        verticals = [f[1] for f in FIELD_SPECS_G102 if f[6] == ""]
        assert verticals == ["A", "B", "K", "L", "X", "Y", "Z", "AA"]
        assert len(verticals) == 8


# ════════════════════════════════════════════════════════════════════════════
# ② json_key 集合 == 前端行接口字段集合（声明与前端不得脱钩）
# ════════════════════════════════════════════════════════════════════════════
class TestJsonKeysMatchFrontendRowInterface:
    def test_declared_json_keys_equal_frontend_managed_fields(self) -> None:
        """🔴 **双向**相等，不是单向包含。"""
        fe_all = set(_frontend_row_fields())
        declared = {f[4] for f in FIELD_SPECS_G102}
        # 前端里受管的 = 全字段 − 非受管
        fe_managed = fe_all - _NON_MANAGED_FE_FIELDS
        assert declared == fe_managed, (
            f"只在声明: {declared - fe_managed}, 只在前端: {fe_managed - declared}"
        )
        assert len(declared) == 27

    def test_frontend_field_order_matches_excel_column_order(self) -> None:
        """前端字段声明顺序 ≡ 模板列序（A..AA）—— 顺序一致才能逐列人工核对。"""
        fe = [f for f in _frontend_row_fields() if f not in _NON_MANAGED_FE_FIELDS]
        spec_keys = [f[4] for f in FIELD_SPECS_G102]
        assert fe == spec_keys, (
            "前端受管字段的出现顺序与 FIELD_SPECS_G102 的 Excel 列序不一致\n"
            f"期望: {spec_keys}\n实际: {fe}"
        )

    def test_row_identity_and_section_are_not_managed_columns(self) -> None:
        """`id` / `seq` / `acctClass` 中只有 `acctClass` 是受管列（模板 A 列），
        `id`/`seq` 不占模板的任何一列。"""
        declared = {f[4] for f in FIELD_SPECS_G102}
        assert "acctClass" in declared, "acctClass 映射模板 A 列，必须是受管列"
        assert "id" not in declared
        assert "seq" not in declared

    def test_non_managed_fields_count(self) -> None:
        """前端行接口有 31 个非受管字段（id/seq + 29 个非模板列）。"""
        fe_all = set(_frontend_row_fields())
        declared = {f[4] for f in FIELD_SPECS_G102}
        non_managed = fe_all - declared
        # id + seq + 29 FRONTEND_ONLY_FIELDS（含 id/seq）= 31
        assert len(non_managed) == len(FRONTEND_ONLY_FIELDS_G102)


# ════════════════════════════════════════════════════════════════════════════
# ③ 公式列与模板公式逐条一致 + 🔴 区①②③ 差集恰 {T}
# ════════════════════════════════════════════════════════════════════════════
class TestFormulaColumnsMatchTemplate:
    def test_r1_formula_columns_are_exactly_the_template_formula_cells(
        self, ws
    ) -> None:
        """区① R12-R16：公式列逐格实测。"""
        from openpyxl.utils import get_column_letter

        data_row = SPEC_G102_R1.first_data_row
        formula_cols: set[str] = set()
        for ci in range(1, 28):  # A..AA
            cell = ws.cell(row=data_row, column=ci)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formula_cols.add(get_column_letter(ci))
        assert formula_cols == set(FORMULA_COLUMNS_R1_G102), (
            f"区① 公式列不匹配: 模板={formula_cols}, 声明={set(FORMULA_COLUMNS_R1_G102)}"
        )

    def test_r2_formula_columns_exclude_t(self, ws) -> None:
        """区② R19-R23：T 列整格无公式。"""
        from openpyxl.utils import get_column_letter

        data_row = SPEC_G102_R2.first_data_row
        formula_cols: set[str] = set()
        for ci in range(1, 28):
            cell = ws.cell(row=data_row, column=ci)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formula_cols.add(get_column_letter(ci))
        assert formula_cols == set(FORMULA_COLUMNS_R23_G102)
        assert "T" not in formula_cols, "区② T 列不应有公式"

    def test_r3_formula_columns_exclude_t(self, ws) -> None:
        """区③ R26-R28：T 列整格无公式。"""
        from openpyxl.utils import get_column_letter

        data_row = SPEC_G102_R3.first_data_row
        formula_cols: set[str] = set()
        for ci in range(1, 28):
            cell = ws.cell(row=data_row, column=ci)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formula_cols.add(get_column_letter(ci))
        assert formula_cols == set(FORMULA_COLUMNS_R23_G102)
        assert "T" not in formula_cols

    def test_formula_difference_between_r1_and_r23_is_exactly_t(self) -> None:
        """G1 与 G9 的唯一不等点。"""
        diff = set(FORMULA_COLUMNS_R1_G102) - set(FORMULA_COLUMNS_R23_G102)
        assert diff == {"T"}

    @pytest.mark.parametrize(
        "col", sorted(FORMULA_TEMPLATES_G102), ids=sorted(FORMULA_TEMPLATES_G102)
    )
    def test_formula_template_renders_to_the_template_cell(
        self, col: str, ws
    ) -> None:
        from openpyxl.utils import column_index_from_string

        ci = column_index_from_string(col)
        row = SPEC_G102_R1.first_data_row
        expected = FORMULA_TEMPLATES_G102[col].format(r=row)
        got = ws.cell(row=row, column=ci).value
        assert got == expected, (
            f"列 {col} R{row}: 模板={got!r}, 声明={expected!r}"
        )

    def test_cross_sheet_t_formulas_match_template_row_by_row(self, ws) -> None:
        """🔴 区① T 列跨表公式逐行比对（引 `公允价值测试表G1-6!H10..H14`）。"""
        from openpyxl.utils import column_index_from_string

        ci = column_index_from_string("T")
        for row, expected in TEMPLATE_CROSS_SHEET_FORMULAS_G102.items():
            got = ws.cell(row=row, column=ci).value
            assert got == expected, (
                f"T{row}: 模板={got!r}, 声明={expected!r}"
            )

    def test_t_column_is_none_in_region_2_and_3(self, ws) -> None:
        """区②③ 的 T 列 8 格全 None（不是空字符串、不是零）。"""
        from openpyxl.utils import column_index_from_string

        ci = column_index_from_string("T")
        for spec in (SPEC_G102_R2, SPEC_G102_R3):
            for row in range(spec.first_data_row, spec.last_data_row + 1):
                v = ws.cell(row=row, column=ci).value
                assert v is None, (
                    f"T{row}（{spec.error_label}）应为 None，实际={v!r}"
                )

    def test_closing_balance_rolls_from_unaudited_line(self) -> None:
        """🔴 `P=C+M` / `Q=D+N` 走**未审线** —— 不得是 `P=H+M`（审定线）。"""
        assert "C" in FORMULA_TEMPLATES_G102["P"]
        assert "H" not in FORMULA_TEMPLATES_G102["P"]
        assert "D" in FORMULA_TEMPLATES_G102["Q"]
        assert "I" not in FORMULA_TEMPLATES_G102["Q"]

    def test_three_component_identities(self) -> None:
        """公允价值 = 成本 + 累计公允价值变动，四处重复。"""
        assert FORMULA_TEMPLATES_G102["E"] == "=C{r}+D{r}"
        assert FORMULA_TEMPLATES_G102["J"] == "=H{r}+I{r}"
        assert FORMULA_TEMPLATES_G102["R"] == "=P{r}+Q{r}"
        assert FORMULA_TEMPLATES_G102["W"] == "=U{r}+V{r}"

    def test_deduction_uses_addition_not_subtraction(self) -> None:
        """🔴 `L=J+K` / `Y=W+X` 是**加**（K/X 存负数）—— 本轮改齐的 6 处之一。"""
        assert FORMULA_TEMPLATES_G102["L"] == "=J{r}+K{r}"
        assert FORMULA_TEMPLATES_G102["Y"] == "=W{r}+X{r}"

    def test_audited_closing_fv_excludes_aje_rje(self) -> None:
        """🔴 `W=U+V` 不含 aje/rje —— 本轮改齐的 6 处之一。"""
        tpl = FORMULA_TEMPLATES_G102["W"]
        assert "U" in tpl and "V" in tpl
        # 只有两个操作数
        assert tpl.count("{r}") == 2

    def test_dividend_column_o_is_not_in_any_balance_formula(self) -> None:
        """O 列（计入投资收益的股息）是损益项，不参与任何余额公式。"""
        assert "O" not in FORMULA_COLUMNS_R1_G102
        for tpl in FORMULA_TEMPLATES_G102.values():
            assert "O{r}" not in tpl

    def test_boolean_columns_are_not_in_formula_columns(self) -> None:
        """Z/AA 两个布尔列不是公式列。"""
        for col in BOOLEAN_COLUMNS_G102:
            assert col not in FORMULA_COLUMNS_R1_G102
            assert col not in FORMULA_COLUMNS_R23_G102


# ════════════════════════════════════════════════════════════════════════════
# ④ 三区几何：区标题行 / 小计行 / 合计行都不在受管区
# ════════════════════════════════════════════════════════════════════════════
class TestThreeSectionGeometry:
    def test_three_specs_share_sheet_key_and_store_item_but_differ_per_section(
        self,
    ) -> None:
        assert len({s.sheet_key for s in ALL_SPECS_G102}) == 1
        assert {s.store_item_id for s in ALL_SPECS_G102} == {STORE_ITEM_ID_G102}
        # 三区 uuid_col 互不相同
        uuids = [s.uuid_col for s in ALL_SPECS_G102]
        assert len(set(uuids)) == 3, f"uuid_col 应互不相同: {uuids}"
        assert uuids == ["AB", "AC", "AD"]
        # 三区 template_id 互不相同
        tids = [s.template_id for s in ALL_SPECS_G102]
        assert len(set(tids)) == 3

    def test_data_regions_match_template(self) -> None:
        regions = [(s.first_data_row, s.last_data_row) for s in ALL_SPECS_G102]
        assert regions == [(12, 16), (19, 23), (26, 28)]
        managed = set()
        for s in ALL_SPECS_G102:
            managed.update(range(s.first_data_row, s.last_data_row + 1))
        for row in SECTION_TITLE_ROWS_G102:
            assert row not in managed, f"R{row}（区标题）不得在受管区"
        for row in SUBTOTAL_ROWS_G102:
            assert row not in managed, f"R{row}（小计）不得在受管区"
        assert GRAND_TOTAL_ROW_G102 not in managed

    def test_section_title_rows_carry_text_without_formula(self, ws) -> None:
        for row, expect_prefix in zip(
            SECTION_TITLE_ROWS_G102,
            ["交易性金融资产", "划分为以公允价值", "指定为以公允价值"],
        ):
            a = ws.cell(row=row, column=1).value
            assert a is not None and str(a).startswith(expect_prefix), (
                f"R{row} A 列期望以 {expect_prefix!r} 开头，实际={a!r}"
            )
            # 公式列不应有公式
            has_formula = any(
                isinstance(ws.cell(row=row, column=c).value, str)
                and ws.cell(row=row, column=c).value.startswith("=")
                for c in range(3, 28)
            )
            assert not has_formula, f"R{row} 是区标题行，不应有公式"

    def test_subtotal_rows_are_sum_of_their_own_region(self, ws) -> None:
        for spec, sub in zip(ALL_SPECS_G102, SUBTOTAL_ROWS_G102):
            expected = f"=SUM(C{spec.first_data_row}:C{spec.last_data_row})"
            assert ws[f"C{sub}"].value == expected

    def test_grand_total_is_enumerated_sum_of_three_subtotals(self, ws) -> None:
        """合计行 `=SUM(C17,C24,C29)` —— 枚举相加而不是区间 SUM。"""
        got = ws[f"C{GRAND_TOTAL_ROW_G102}"].value
        for sub in SUBTOTAL_ROWS_G102:
            assert f"C{sub}" in str(got), f"合计行缺小计 R{sub}"

    def test_row_section_values_map_to_g1_acct_class(self) -> None:
        """三区 `row_section_value` 映射到前端 `G1AcctClass` 枚举。"""
        values = [s.row_section_value for s in ALL_SPECS_G102]
        assert values == ["trading", "classified_fvpl", "designated_fvpl"]

    def test_ghost_row_anchor_is_column_b(self) -> None:
        """幽灵行锚点指 B 列（投资项目名称），不是默认 [0]=A 列（类别枚举）。"""
        for s in ALL_SPECS_G102:
            assert s.ghost_row_anchor_index == 1


# ════════════════════════════════════════════════════════════════════════════
# ⑤ 三区过滤读写成对（引擎 `row_section_field`）
# ════════════════════════════════════════════════════════════════════════════
class TestSectionFilterReadWritePairing:
    PAYLOAD = [
        {"id": "a1", "acctClass": "trading", "securityName": "甲"},
        {"id": "b1", "acctClass": "classified_fvpl", "securityName": "乙"},
        {"id": "b2", "acctClass": "classified_fvpl", "securityName": "丙"},
        {"id": "c1", "acctClass": "designated_fvpl", "securityName": "丁"},
    ]

    def test_each_spec_reads_only_its_own_section(self) -> None:
        got = {
            s.row_section_value: [
                rid for rid, _row in iter_store_rows(s, self.PAYLOAD)
            ]
            for s in ALL_SPECS_G102
        }
        assert got == {
            "trading": ["a1"],
            "classified_fvpl": ["b1", "b2"],
            "designated_fvpl": ["c1"],
        }

    def test_duplicate_identity_check_is_scoped_to_the_section(self) -> None:
        """过滤在重复身份校验之前 —— 不同区的 id 允许相同值（虽然不推荐）。"""
        for s in ALL_SPECS_G102:
            list(iter_store_rows(s, self.PAYLOAD))  # 不抛即通过

    def test_duplicate_within_the_same_section_still_fails_closed(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            RowTableStorePayloadError,
        )

        dup = [
            {"id": "x1", "acctClass": "trading", "securityName": "甲"},
            {"id": "x1", "acctClass": "trading", "securityName": "乙"},
        ]
        with pytest.raises(RowTableStorePayloadError):
            list(iter_store_rows(SPEC_G102_R1, dup))

    def test_merge_stamps_section_on_newly_inserted_rows(self) -> None:
        """OO 侧在区② 插的新行，回写时必须带上 `acctClass='classified_fvpl'`。"""

        class _FV:
            def __init__(self, key: str, row_key: str, value):
                self.stable_key = key
                self.row_key = row_key
                self.value = value
                self.is_protected = False

        spec = SPEC_G102_R2  # 区②
        # 🔴 ghost_row_anchor_index=1 → specs[1]='security_name' (json_path='securityName')
        #    新行必须在这个路径非空才能通过幽灵行防护
        new_key_name = f"{spec.table_key}/newrow/security_name"
        new_key_cost = f"{spec.table_key}/newrow/closing_cost"

        class _Proj:
            def stable_keys(self):
                return [new_key_name, new_key_cost]

            def get(self, key):
                if key == new_key_name:
                    return _FV(key, "newrow", "OO侧新增")
                if key == new_key_cost:
                    return _FV(key, "newrow", 200)
                return None

        existing = [
            {"id": "b1", "acctClass": "classified_fvpl", "securityName": "乙"},
        ]
        rows, applied, _visited, touched = merge_projection_into_store_rows(
            spec, projection=_Proj(), base_rows=existing
        )
        assert applied >= 1
        new = [r for r in rows if r["id"] == "newrow"]
        assert len(new) == 1
        assert new[0][ROW_SECTION_FIELD_G102] == "classified_fvpl"

    def test_existing_rows_keep_their_own_section_on_merge(self) -> None:
        """已有行的 `acctClass` 不被 merge 覆盖。"""

        class _Proj:
            def stable_keys(self):
                return []

            def get(self, key):
                return None

        existing = [
            {"id": "b1", "acctClass": "classified_fvpl", "securityName": "乙"},
        ]
        rows, applied, *_ = merge_projection_into_store_rows(
            SPEC_G102_R2, projection=_Proj(), base_rows=existing
        )
        assert applied == 0
        assert rows[0]["acctClass"] == "classified_fvpl"

    def test_filter_is_opt_in_so_existing_providers_are_untouched(self) -> None:
        """`row_section_field` 为空时不过滤 —— 既有 provider 行为逐字不变。"""
        from dataclasses import replace

        spec_no_filter = replace(
            SPEC_G102_R1, row_section_field="", row_section_value=""
        )
        all_ids = [rid for rid, _row in iter_store_rows(spec_no_filter, self.PAYLOAD)]
        assert len(all_ids) == 4


# ════════════════════════════════════════════════════════════════════════════
# ⑥ 口径改齐验证（6 处 + M 合并 + AA 新补 —— 本轮改造的核心产出）
# ════════════════════════════════════════════════════════════════════════════
class TestOralignmentSixFixes:
    """验证 FIELD_SPECS_G102 中 6 处口径改齐 + M 合并 + AA 新补。"""

    def test_m_is_single_column_net_amount(self) -> None:
        """模板 M 是净额单列「本期变动（增加为正数）成本」—— 前端从两列合并。"""
        m_field = [f for f in FIELD_SPECS_G102 if f[1] == "M"]
        assert len(m_field) == 1
        assert m_field[0][4] == "periodCostChange"
        assert m_field[0][2] == "editable"

    def test_aa_confirmation_requested_exists(self) -> None:
        """本轮新补的 AA 列「是否函证」—— 前端原先没有。"""
        aa = [f for f in FIELD_SPECS_G102 if f[1] == "AA"]
        assert len(aa) == 1
        assert aa[0][4] == "confirmationRequested"
        assert aa[0][2] == "editable"
        assert aa[0][3] == "boolean"

    def test_p_rolls_from_opening_cost_c_not_audited_h(self) -> None:
        """P=C+M：起点是期初余额成本（C），不是期初审定成本（H）。"""
        assert FORMULA_TEMPLATES_G102["P"] == "=C{r}+M{r}"

    def test_q_rolls_from_opening_cumulative_d_not_audited_i(self) -> None:
        """Q=D+N：起点是期初余额累计 FV（D），不是审定累计 FV（I）。"""
        assert FORMULA_TEMPLATES_G102["Q"] == "=D{r}+N{r}"

    def test_r_is_always_dual_bucket_sum_not_market_override(self) -> None:
        """R=P+Q：恒为双桶合计（市价只做非受管验算）。"""
        assert FORMULA_TEMPLATES_G102["R"] == "=P{r}+Q{r}"

    def test_w_excludes_aje_rje(self) -> None:
        """W=U+V：期末审定公允价值不含 AJE/RJE。"""
        assert FORMULA_TEMPLATES_G102["W"] == "=U{r}+V{r}"

    def test_l_and_y_use_addition(self) -> None:
        """L=J+K / Y=W+X 是加（K/X 存负数 ⇒ 列标签「减：…」）。"""
        assert FORMULA_TEMPLATES_G102["L"] == "=J{r}+K{r}"
        assert FORMULA_TEMPLATES_G102["Y"] == "=W{r}+X{r}"

    def test_frontend_old_fields_removed_from_managed(self) -> None:
        """被合并的 `addedCost`/`reducedCost` 不在受管列里。"""
        declared = {f[4] for f in FIELD_SPECS_G102}
        assert "addedCost" not in declared
        assert "reducedCost" not in declared
