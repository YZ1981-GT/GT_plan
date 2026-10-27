# -*- coding: utf-8 -*-
"""D6-3 合同资产减值准备明细表：双区 + 列对齐（spec oo-writeback-template-parity-closure R3 任务 9 批 A2）。

模板 R10/R11 两级表头；单项区数据 R13-16（父行 R12）、组合区数据 R18-21（父行 R17）、合计 R22。
列：A 项目、B/C/D 期初 未审 / 账项调整 / 重分类调整、E = B+C+D、F~J 计提 / 其他增加 / 转回 / 核销 / 其他减少、
K = B + SUM(F:G) − SUM(H:J)、L/M 期末调整、N = K+L+M。前端两区的行存在同一个 `D6-3-rows` 数组里、
行内 `category` = 'single' | 'group'。

锁的缺陷：原声明只受管单项区，B 列接成 `category`、C → priorUnadjusted、D → priorAje、priorRje 没接；
组合区的行全投影进单项区。
"""
from __future__ import annotations

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.phase5_d6_03_impairment import (
    SPEC_D603_GROUP,
    SPEC_D603_SINGLE,
    SPECS_D603,
    STORE_ITEM_ID_D603,
)
from app.services.workpaper_sync.phase5_d6_expansion import managed_row_table_specs
from app.services.workpaper_sync.phase5_row_table_sheet import (
    iter_store_rows,
    merge_projection_into_store_rows,
)

#: 模板列 → 前端 ImpairmentDetailRow 字段（逐列核对权威模板 R10/R11 与 useD6ImpairmentDetail）
TEMPLATE_COLUMNS = {
    "A": "itemName", "B": "priorUnadjusted", "C": "priorAje", "D": "priorRje", "E": "priorAudited",
    "F": "provision", "G": "otherIncrease", "H": "reversal", "I": "writeOff", "J": "otherDecrease",
    "K": "endUnadjusted", "L": "endAje", "M": "endRje", "N": "endAudited",
}


def test_columns_follow_template_and_frontend_names() -> None:
    for spec in SPECS_D603:
        assert {fs[1]: fs[4] for fs in spec.field_specs} == TEMPLATE_COLUMNS
        assert {fs[1] for fs in spec.field_specs if fs[2] == "formula"} == {"E", "K", "N"}
        assert "category" not in {fs[4] for fs in spec.field_specs}, "category 不是模板列，是分区字段"


def test_two_regions_share_store_item_and_split_by_category() -> None:
    single, group = SPEC_D603_SINGLE, SPEC_D603_GROUP
    assert single.store_item_id == group.store_item_id == STORE_ITEM_ID_D603
    assert (single.row_section_field, single.row_section_value) == ("category", "single")
    assert (group.row_section_field, group.row_section_value) == ("category", "group")
    assert (single.first_data_row, single.last_data_row) == (13, 16)
    assert (group.first_data_row, group.last_data_row) == (18, 21)
    assert single.footer_row == group.footer_row == 22
    assert single.uuid_col != group.uuid_col, "两区同一 UUID 列会让行身份串区"
    assert single.table_key != group.table_key and single.template_id != group.template_id
    # 扩容面按 Excel 行序登记两区
    d63 = [s for s in managed_row_table_specs() if s.store_item_id == STORE_ITEM_ID_D603]
    assert d63 == [single, group]


def test_store_rows_land_only_in_their_region() -> None:
    rows = [
        {"rowId": "s1", "category": "single", "itemName": "甲", "priorUnadjusted": 10},
        {"rowId": "g1", "category": "group", "itemName": "乙", "priorUnadjusted": 20},
        {"rowId": "g2", "category": "group", "itemName": "丙", "priorUnadjusted": 30},
    ]
    assert [rid for rid, _ in iter_store_rows(SPEC_D603_SINGLE, rows)] == ["s1"]
    assert [rid for rid, _ in iter_store_rows(SPEC_D603_GROUP, rows)] == ["g1", "g2"]


def _projection(spec, rid: str, values: dict[str, object]) -> Projection:
    by_json = {fs[4]: fs for fs in spec.field_specs}
    out = {}
    for json_key, value in values.items():
        col_key, _col, _mode, vtype, _jk, _hdr, _g = by_json[json_key]
        sk = f"{spec.table_key}/{rid}/{col_key}"
        out[sk] = FieldValue(stable_key=sk, value=value, value_type=ValueType(vtype),
                             mode=FieldMode("editable"), row_key=rid)
    return Projection(contract_id="d6.contract_assets_detail", semantic_version="1.0.0",
                      document_type="xlsx", values=out, row_keys={spec.table_key: (rid,)})


def test_row_added_in_group_region_comes_back_as_group() -> None:
    base = [{"rowId": "s1", "category": "single", "itemName": "甲"}]
    proj = _projection(SPEC_D603_GROUP, "new-1", {"itemName": "组合新行", "priorRje": 5})
    merged, applied, _visited, touched = merge_projection_into_store_rows(
        SPEC_D603_GROUP, projection=proj, base_rows=base,
    )
    new_row = next(r for r in merged if r["rowId"] == "new-1")
    assert new_row["category"] == "group"
    assert new_row["priorRje"] == 5, "D 列重分类调整接到 priorRje（原声明没接）"
    assert touched == {"new-1"} and applied == 2
    # 单项区那一趟不会把组合区的键建成单项行
    merged_single, *_ = merge_projection_into_store_rows(SPEC_D603_SINGLE, projection=proj, base_rows=base)
    assert [r["rowId"] for r in merged_single] == ["s1"]
