# -*- coding: utf-8 -*-
"""`AdjudicationSheetSpec` 判据（Task 31 / E1 前置 B）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 31 · Requirements 5.1 / 6.3 / 6.5
consumed by: e1-sync-coverage-and-first-canary（前置 B）

═══ 判据面 ═══

1. **能表达 D4-1 的真实几何**（2 区 + 双级表头 + footer 三行 + 逐格 mask）——
   证明 spec 类不是纸上抽象，而是从已交付审定表反推出来的。
2. **同 sheet 多区 uuid_col 重复必抛**（D4-1 主营 W / 其他 X 的实测教训：同列会让行身份串区）。
3. **派生格不可 OO 直写**（需求 6.3 / E1 需求 4.5）：cross_sheet / cross_volume / tb_derived /
   computed 四种来源的 `is_oo_writable` 必须为 False。
4. **格级 mask 判定**（不是整列）：与 `merge._protection._mask_spans_data_column` 同口径。
5. **受管数据格落 mask 必抛**（D4-1 踩过的 fail-closed 缺陷：改了写不回且无提示）。
6. 三种 row_mode 都能构造（dynamic_identity / fixed_rows / slot_driven）。
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

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)


def _spec_d41() -> AdjudicationSheetSpec:
    """按 D4-1 已交付实现的真实几何构造（phase5_d4_adjudication_sheet 实测常量）。"""
    return AdjudicationSheetSpec(
        managed_sheet="营业收入审定表D4-1",
        sheet_key="d41-managed",
        template_id="D41",
        header_rows=(5, 6),
        sections=(
            AdjudicationSection(
                section_key="main-revenue",
                table_key="adjudication_main_rows",
                title_row=7,
                first_data_row=8,
                last_data_row=11,
                subtotal_row=12,
                uuid_col="W",
                table_name="GT_D41_MAIN_ROWS",
                template_id="D41MAIN",
            ),
            AdjudicationSection(
                section_key="other-revenue",
                table_key="adjudication_other_rows",
                title_row=13,
                first_data_row=14,
                last_data_row=17,
                subtotal_row=18,
                uuid_col="X",
                table_name="GT_D41_OTHER_ROWS",
                template_id="D41OTHER",
            ),
        ),
        row_mode=AdjudicationRowMode.dynamic_identity,
        total_row=19,
        tb_row=20,
        diff_row=21,
        store_item_id="D4-1-rows",
        row_identity_key="rowId",
        field_specs=(
            ("label", "A", "editable", "text", "label", "项目", ""),
            ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "本期未审", ""),
            ("current_aje", "C", "editable", "amount", "currentAje", "账项调整", ""),
            ("current_rje", "D", "editable", "amount", "currentRje", "重分类调整", ""),
            ("current_audited", "E", "formula", "amount", "currentAudited", "本期审定", ""),
            ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "上期未审", ""),
            ("prior_aje", "G", "editable", "amount", "priorAje", "账项调整", ""),
            ("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整", ""),
            ("prior_audited", "I", "formula", "amount", "priorAudited", "上期审定", ""),
        ),
        # 逐格 mask：审定列 E/I 的数据行 + 小计/合计/TB/差异行的 B–I（D4-1 实测形态）
        cell_mask=tuple(
            [f"E{r}" for r in (8, 9, 10, 11, 14, 15, 16, 17)]
            + [f"I{r}" for r in (8, 9, 10, 11, 14, 15, 16, 17)]
            + [f"{c}{r}" for r in (12, 18, 19, 20, 21) for c in "BCDEFGHI"]
        ),
        value_sources={
            "current_unadjusted": AdjudicationValueSource.tb_derived,
            "current_audited": AdjudicationValueSource.computed,
            "prior_audited": AdjudicationValueSource.computed,
        },
    )


def test_expresses_d41_real_geometry() -> None:
    """能表达 D4-1 真实几何：2 区 / 数据行 8 行 / computed 行 = 2 小计 + 3 footer。"""
    spec = _spec_d41()
    assert len(spec.sections) == 2
    assert spec.data_rows == (8, 9, 10, 11, 14, 15, 16, 17)
    assert spec.computed_rows == (12, 18, 19, 20, 21)
    assert spec.section("main-revenue").uuid_col == "W"
    assert spec.section("other-revenue").uuid_col == "X"
    assert spec.section("nope") is None


def test_duplicate_uuid_col_across_sections_raises() -> None:
    """同 sheet 多区共用 UUID 列 ⇒ 行身份串区 ⇒ 构造即抛（D4-1 实测教训）。"""
    with pytest.raises(ValueError, match="隐藏身份列重复"):
        AdjudicationSheetSpec(
            managed_sheet="x",
            sheet_key="x",
            template_id="X",
            header_rows=(1,),
            sections=(
                AdjudicationSection("a", "ta", 1, 2, 3, 4, uuid_col="W"),
                AdjudicationSection("b", "tb", 5, 6, 7, 8, uuid_col="W"),
            ),
            row_mode=AdjudicationRowMode.dynamic_identity,
        )


def test_duplicate_table_key_raises() -> None:
    with pytest.raises(ValueError, match="table_key 重复"):
        AdjudicationSheetSpec(
            managed_sheet="x",
            sheet_key="x",
            template_id="X",
            header_rows=(1,),
            sections=(
                AdjudicationSection("a", "same", 1, 2, 3, 4, uuid_col="W"),
                AdjudicationSection("b", "same", 5, 6, 7, 8, uuid_col="X"),
            ),
            row_mode=AdjudicationRowMode.dynamic_identity,
        )


def test_derived_cells_are_not_oo_writable() -> None:
    """需求 6.3 / E1 需求 4.5：派生格不可 OO 直写（否则覆盖聚合结果 ⇒ 静默丢数据）。"""
    spec = _spec_d41()
    assert spec.is_oo_writable("current_aje") is True       # manual（默认）
    assert spec.is_oo_writable("current_unadjusted") is False  # tb_derived
    assert spec.is_oo_writable("current_audited") is False     # computed
    assert spec.is_oo_writable("prior_audited") is False       # computed


def test_all_derived_source_kinds_are_blocked() -> None:
    """四种派生来源全部不可 OO 直写（含 E1 独有的 cross_volume 跨册）。"""
    for src in (
        AdjudicationValueSource.cross_sheet,
        AdjudicationValueSource.cross_volume,
        AdjudicationValueSource.tb_derived,
        AdjudicationValueSource.computed,
    ):
        spec = AdjudicationSheetSpec(
            managed_sheet="x",
            sheet_key="x",
            template_id="X",
            header_rows=(1,),
            sections=(AdjudicationSection("a", "ta", 1, 2, 3, 4, uuid_col="W"),),
            row_mode=AdjudicationRowMode.dynamic_identity,
            value_sources={"f": src},
        )
        assert spec.is_oo_writable("f") is False, f"{src} 应被挡住"


def test_cell_mask_is_cell_level_not_column_level() -> None:
    """格级判定：E 列在数据行被 mask，但 B 列在数据行**不**被 mask（尽管 B12 小计行被 mask）。"""
    spec = _spec_d41()
    assert spec.is_cell_masked("E", 8) is True     # 审定列数据行 = 公式格
    assert spec.is_cell_masked("B", 12) is True    # 小计行 = 公式格
    assert spec.is_cell_masked("B", 8) is False    # 🔴 受管数据格：同列但不同行 ⇒ 不得判只读
    assert spec.is_cell_masked("b", 12) is True    # 大小写无关


def test_masked_managed_data_cell_raises() -> None:
    """受管数据格落进 mask ⇒ 自检必抛（D4-1 踩过：改了写不回且无提示）。"""
    spec = _spec_d41()
    spec.assert_data_cells_not_masked()  # 正确声明不抛

    bad = AdjudicationSheetSpec(
        managed_sheet="x",
        sheet_key="x",
        template_id="X",
        header_rows=(1,),
        sections=(AdjudicationSection("a", "ta", 1, 2, 5, 6, uuid_col="W"),),
        row_mode=AdjudicationRowMode.dynamic_identity,
        field_specs=(("amt", "B", "editable", "amount", "amt", "金额", ""),),
        cell_mask=("B2", "B3"),  # 🔴 B 是 editable 受管列，B2/B3 是数据行
    )
    with pytest.raises(ValueError, match="受管数据格落进了 formula mask"):
        bad.assert_data_cells_not_masked()


def test_slot_driven_mode_allows_zero_sections() -> None:
    """E1-1 的槽位驱动形态（per-cell + E1_SLOT_ORDER）不需要 section。"""
    spec = AdjudicationSheetSpec(
        managed_sheet="货币资金审定表E1-1",
        sheet_key="e11-managed",
        template_id="E11",
        header_rows=(5, 6),
        sections=(),
        row_mode=AdjudicationRowMode.slot_driven,
        slot_order=("institution", "finance", "other"),
        per_cell_key_template="E1-adj-{item}-{field}",
    )
    assert spec.row_mode is AdjudicationRowMode.slot_driven
    assert spec.slot_order == ("institution", "finance", "other")
    assert spec.data_rows == ()


def test_non_slot_mode_requires_sections() -> None:
    with pytest.raises(ValueError, match="必须至少声明一个 section"):
        AdjudicationSheetSpec(
            managed_sheet="x",
            sheet_key="x",
            template_id="X",
            header_rows=(1,),
            sections=(),
            row_mode=AdjudicationRowMode.fixed_rows,
        )


def test_fixed_rows_mode_constructs() -> None:
    """D2-1 的写死 4 行形态。"""
    spec = AdjudicationSheetSpec(
        managed_sheet="应收账款审定表D2-1",
        sheet_key="d21-managed",
        template_id="D21",
        header_rows=(9, 10),
        sections=(AdjudicationSection("credit-risk", "adjudication_rows", 10, 11, 14, 15, uuid_col="Q"),),
        row_mode=AdjudicationRowMode.fixed_rows,
        per_cell_key_template="D2-adj-{slug}-{field}",
    )
    assert spec.row_mode is AdjudicationRowMode.fixed_rows
    assert spec.data_rows == (11, 12, 13, 14)
