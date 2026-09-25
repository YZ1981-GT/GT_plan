# -*- coding: utf-8 -*-
"""AdjudicationSheetSpec 框架层判据（Task 31）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 31 · Requirements 5.1 / 6.1~6.5

这个类型是 e1/d2/d3/d567 lane spec 的解阻塞依赖 —— 判据必须覆盖它自己声明的两条硬约束
（同 sheet 多区 UUID 列不重复 / table_key 不重复）与核心方法（`is_oo_writable` 派生格保护 /
`assert_data_cells_not_masked` fail-closed 自检），且用真实变异证明非永绿装饰。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)


def _d1_style_sections() -> tuple[AdjudicationSection, ...]:
    """仿 D1-1 三区（gross/bd/net），几何为示意值不追求逐字节还原真实模板。"""
    return (
        AdjudicationSection(
            section_key="gross", table_key="adj_gross_rows",
            title_row=5, first_data_row=6, last_data_row=10, subtotal_row=11, uuid_col="W",
        ),
        AdjudicationSection(
            section_key="bd", table_key="adj_bd_rows",
            title_row=12, first_data_row=13, last_data_row=17, subtotal_row=18, uuid_col="X",
        ),
        AdjudicationSection(
            section_key="net", table_key="adj_net_rows",
            title_row=19, first_data_row=20, last_data_row=24, subtotal_row=25, uuid_col="Y",
        ),
    )


class TestSectionUniquenessGuards:
    """需求 6.2 隐含的结构完整性：同 sheet 多区 uuid_col / table_key 不得重复。"""

    def test_valid_three_sections_construct_without_error(self) -> None:
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1, 2), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
        )
        assert len(spec.sections) == 3

    def test_duplicate_uuid_col_raises(self) -> None:
        """🔴 D4-1 主营/其他实测教训：同列会让两区行身份串区。"""
        sections = _d1_style_sections()
        dup = (
            sections[0],
            AdjudicationSection(
                section_key="bd", table_key="adj_bd_rows",
                title_row=12, first_data_row=13, last_data_row=17, subtotal_row=18,
                uuid_col="W",  # MUTATION: 与 gross 撞列
            ),
        )
        with pytest.raises(ValueError, match="隐藏身份列重复"):
            AdjudicationSheetSpec(
                managed_sheet="x", sheet_key="x", template_id="x",
                header_rows=(1,), sections=dup,
                row_mode=AdjudicationRowMode.dynamic_identity,
            )

    def test_duplicate_table_key_raises(self) -> None:
        sections = _d1_style_sections()
        dup = (
            sections[0],
            AdjudicationSection(
                section_key="bd", table_key="adj_gross_rows",  # MUTATION: 撞 table_key
                title_row=12, first_data_row=13, last_data_row=17, subtotal_row=18, uuid_col="X",
            ),
        )
        with pytest.raises(ValueError, match="table_key 重复"):
            AdjudicationSheetSpec(
                managed_sheet="x", sheet_key="x", template_id="x",
                header_rows=(1,), sections=dup,
                row_mode=AdjudicationRowMode.dynamic_identity,
            )

    def test_non_slot_driven_requires_at_least_one_section(self) -> None:
        with pytest.raises(ValueError, match="必须至少声明一个 section"):
            AdjudicationSheetSpec(
                managed_sheet="x", sheet_key="x", template_id="x",
                header_rows=(1,), sections=(),
                row_mode=AdjudicationRowMode.dynamic_identity,
            )

    def test_slot_driven_allows_empty_sections(self) -> None:
        """E1-1 范式：slot_driven 不需要 sections。"""
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=(),
            row_mode=AdjudicationRowMode.slot_driven,
            slot_order=("slot-a", "slot-b"),
        )
        assert spec.sections == ()


class TestValueSourceAndOoWritability:
    """派生格不可 OO 直写（D1 需求 6.3 / E1 需求 4.5 同一条纪律）。"""

    def _spec(self) -> AdjudicationSheetSpec:
        return AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            value_sources={
                "prior_aje": AdjudicationValueSource.manual,
                "prior_audited": AdjudicationValueSource.computed,
                "gross_amount": AdjudicationValueSource.cross_sheet,
            },
        )

    def test_manual_field_is_oo_writable(self) -> None:
        assert self._spec().is_oo_writable("prior_aje") is True

    def test_computed_field_is_not_oo_writable(self) -> None:
        assert self._spec().is_oo_writable("prior_audited") is False

    def test_cross_sheet_field_is_not_oo_writable(self) -> None:
        assert self._spec().is_oo_writable("gross_amount") is False

    def test_undeclared_field_defaults_to_manual_and_writable(self) -> None:
        spec = self._spec()
        assert spec.source_of("undeclared_field") is AdjudicationValueSource.manual
        assert spec.is_oo_writable("undeclared_field") is True

    def test_mutation_marking_manual_as_computed_flips_writability(self) -> None:
        """🔴 变异反证：把 manual 字段错标成 computed，可写性判断必须跟着变
        （证明 is_oo_writable 真的读 value_sources，不是恒真/恒假的装饰）。
        """
        mutated = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            value_sources={"prior_aje": AdjudicationValueSource.computed},  # 本应是 manual
        )
        assert mutated.is_oo_writable("prior_aje") is False
        assert self._spec().is_oo_writable("prior_aje") is True  # 对照：未变异的版本仍可写


class TestCellMaskIsPerCellNotColumnar:
    """🔴 核心裁决：cell_mask 是逐格集合，不是列向区间 —— 与 RowTableSheetSpec.formula_mask
    的区间形态形成对照，这正是审定表不进行表引擎的原因之一。
    """

    def _spec_with_mask(self) -> AdjudicationSheetSpec:
        return AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            total_row=26, tb_row=27, diff_row=28,
            cell_mask=("B11", "B18", "B25", "B26", "b27", " B28 "),  # 混大小写/空白验规范化
        )

    def test_masked_cells_normalized_upper_stripped(self) -> None:
        spec = self._spec_with_mask()
        assert spec.masked_cells == {"B11", "B18", "B25", "B26", "B27", "B28"}

    def test_is_cell_masked_case_insensitive(self) -> None:
        spec = self._spec_with_mask()
        assert spec.is_cell_masked("b", 11) is True
        assert spec.is_cell_masked("B", 11) is True

    def test_data_row_is_not_masked_by_default(self) -> None:
        """数据行（非小计/合计/差异行）不应落进 mask —— 否则触发 fail-closed 自检。"""
        spec = self._spec_with_mask()
        assert spec.is_cell_masked("B", 6) is False  # gross 区首个数据行

    def test_computed_rows_are_subtotals_plus_footer(self) -> None:
        spec = self._spec_with_mask()
        assert spec.computed_rows == (11, 18, 25, 26, 27, 28)

    def test_data_rows_span_all_sections_and_exclude_computed(self) -> None:
        spec = self._spec_with_mask()
        data = set(spec.data_rows)
        assert data.isdisjoint(set(spec.computed_rows))
        assert data == set(range(6, 11)) | set(range(13, 18)) | set(range(20, 25))


class TestAssertDataCellsNotMaskedFailClosed:
    """🔴 D4-1 fail-closed 自检：受管数据格绝不能落进 mask，否则审计师改了写不回且无提示。"""

    def test_clean_spec_passes(self) -> None:
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            field_specs=(("prior_aje", "B", "editable", "amount", "priorAje", "账项调整", ""),),
            cell_mask=("B11", "B18", "B25"),  # 只覆盖小计行
        )
        spec.assert_data_cells_not_masked()  # 不应抛

    def test_mutation_mask_spanning_data_row_is_caught(self) -> None:
        """🔴 变异反证：把 mask 错误地扩展到数据行（如整列区间的旧写法），自检必须打红。
        这正是 D4-1 的历史缺陷形态：editable 字段被 mask 误判只读。
        """
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            field_specs=(("prior_aje", "B", "editable", "amount", "priorAje", "账项调整", ""),),
            cell_mask=("B11", "B18", "B25", "B7"),  # B7 落在 gross 区数据行内 —— 错误
        )
        with pytest.raises(ValueError, match="落进了 formula mask"):
            spec.assert_data_cells_not_masked()

    def test_formula_mode_fields_are_not_checked(self) -> None:
        """只检查 editable 字段；formula 字段本就该在 mask 内（审定/合计列）。"""
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
            field_specs=(("audited", "E", "formula", "amount", "audited", "审定数", ""),),
            cell_mask=("E6", "E7", "E8", "E9", "E10"),  # formula 列整段入 mask 合法
        )
        spec.assert_data_cells_not_masked()  # 不应抛


class TestSectionLookup:
    def test_section_returns_matching_section(self) -> None:
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
        )
        found = spec.section("bd")
        assert found is not None
        assert found.table_key == "adj_bd_rows"

    def test_section_returns_none_for_unknown_key(self) -> None:
        spec = AdjudicationSheetSpec(
            managed_sheet="x", sheet_key="x", template_id="x",
            header_rows=(1,), sections=_d1_style_sections(),
            row_mode=AdjudicationRowMode.dynamic_identity,
        )
        assert spec.section("nonexistent") is None


class TestRowModeThreeForms:
    """三循环行模型互不相同（D1-1 dynamic_identity / D2-1 fixed_rows / E1-1 slot_driven）。"""

    @pytest.mark.parametrize(
        "mode",
        [AdjudicationRowMode.dynamic_identity, AdjudicationRowMode.fixed_rows, AdjudicationRowMode.slot_driven],
    )
    def test_each_mode_is_a_distinct_enum_member(self, mode: AdjudicationRowMode) -> None:
        assert isinstance(mode, AdjudicationRowMode)

    def test_three_modes_are_pairwise_distinct(self) -> None:
        modes = {
            AdjudicationRowMode.dynamic_identity,
            AdjudicationRowMode.fixed_rows,
            AdjudicationRowMode.slot_driven,
        }
        assert len(modes) == 3
