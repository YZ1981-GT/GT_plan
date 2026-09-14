"""附注预付款项存量快照回填脚本的纯函数契约。

关键安全边界：``snapshot_has_data`` 必须挡住任何**已有录入数据**的章节
（改由底稿披露表「同步到附注」整表覆盖），只允许重建空骨架。

spec: .kiro/specs/f1-prepayment-disclosure-template-alignment/ R1（存量回填）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from scripts.fix.backfill_note_prepayment_snapshots import (  # noqa: E402
    TARGETS,
    _load_template_section,
    build_tables_from_template,
    rebuild_table_data,
    snapshot_has_data,
)


@pytest.fixture(scope="module")
def soe_section() -> dict[str, Any]:
    file_name, number = TARGETS["八、7"]
    return _load_template_section(file_name, number)


@pytest.fixture(scope="module")
def listed_section() -> dict[str, Any]:
    file_name, number = TARGETS["五、7"]
    return _load_template_section(file_name, number)


# ─── 数据守卫 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "table_data",
    [
        None,
        {},
        {"rows": []},
        {"rows": [{"label": "小计", "values": [None, None]}]},
        {"rows": [{"label": "1年以内", "values": ["", "  "]}]},
        {"_tables": [{"name": "A", "rows": [{"label": "x", "values": [None]}]}]},
        {"sub_table_data": {"表": [{"label": "合计", "is_total": True}]}},
        {"sub_table_data": {"_note_texts": [{"section": "a", "text": "有字但是元数据键"}]}},
    ],
)
def test_snapshot_has_data_false_for_blank(table_data: Any) -> None:
    assert snapshot_has_data(table_data) is False


@pytest.mark.parametrize(
    "table_data",
    [
        {"rows": [{"label": "1年以内", "values": [13576792.21, None]}]},
        {"_tables": [{"name": "A", "rows": [{"label": "x", "values": [None, 1]}]}]},
        {"rows": [{"label": "x", "values": [None], "_cell_meta": {"0": {"manual_value": "3"}}}]},
        {"sub_table_data": {"表": [{"label": "甲", "balance": 100}]}},
    ],
)
def test_snapshot_has_data_true_when_any_value(table_data: Any) -> None:
    assert snapshot_has_data(table_data) is True


# ─── 骨架重建 ────────────────────────────────────────────────────────────────

def test_build_tables_strips_header_label_and_keeps_meta(soe_section: dict[str, Any]) -> None:
    tables = build_tables_from_template(soe_section, "八、7")
    assert [t["name"] for t in tables] == [
        "预付款项按账龄列示",
        "账龄超过1年的大额预付款项",
        "按欠款方归集的期末余额前五名的预付款项",
    ]

    aging = tables[0]
    assert aging["headers"] == ["账  龄", "金 额", "比例（%）", "金 额", "比例（%）"]
    assert [g["group"] for g in aging["_column_groups"]] == ["期末数", "期初数"]
    assert aging["guidance"]
    # 无 header_label 假行；每行 values 长度 = 值列数
    assert all(r["row_type"] != "header_label" for r in aging["rows"])
    assert [r["label"] for r in aging["rows"]][-3:] == ["小计", "减：减值准备", "合计"]
    for r in aging["rows"]:
        assert len(r["values"]) == len(aging["headers"]) - 1

    # 金额列（end_amount / prior_amount）才打 semantic + binding_id
    data_row = next(r for r in aging["rows"] if r["label"] == "1年以内（含1年）")
    assert sorted(data_row["_cell_meta"]) == ["0", "2"]
    assert data_row["_cell_meta"]["0"]["semantic"] == "closing_balance"
    assert data_row["_cell_meta"]["2"]["semantic"] == "opening_balance"
    assert data_row["_cell_meta"]["0"]["binding_id"] == "八、7.1年以内（含1年）.closing_balance"

    # 单级表头表不带父表头
    for t in tables[1:]:
        assert "_column_groups" not in t


def test_rebuild_reports_rename_and_header_change(soe_section: dict[str, Any]) -> None:
    """模拟修订前的存量快照（重名 + 压平表头）→ 重建后表名唯一、表头 5 列。"""
    legacy = {
        "headers": ["账龄", "期末数", "期初数"],
        "rows": [{"label": "账龄", "values": [None, None], "row_type": "header_label"}],
        "_tables": [
            {"name": "预付款项按账龄列示", "headers": ["账龄", "期末数", "期初数"], "rows": []},
            {"name": "账龄超过1年的大额预付款项", "headers": [], "rows": []},
            {"name": "账龄超过1年的大额预付款项", "headers": [], "rows": []},
        ],
    }
    new_data, changes = rebuild_table_data(legacy, soe_section, "八、7")

    names = [t["name"] for t in new_data["_tables"]]
    assert len(set(names)) == 3
    assert names[2] == "按欠款方归集的期末余额前五名的预付款项"
    assert new_data["headers"] == ["账  龄", "金 额", "比例（%）", "金 额", "比例（%）"]
    # 顶层 rows 沿用「= 第一张表」约定，且无 header_label
    assert all(r["row_type"] != "header_label" for r in new_data["rows"])
    assert any("表名" in c for c in changes)
    assert any("headers" in c for c in changes)


def test_rebuild_is_idempotent(soe_section: dict[str, Any]) -> None:
    first, _ = rebuild_table_data({}, soe_section, "八、7")
    second, changes = rebuild_table_data(first, soe_section, "八、7")
    assert changes == []
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_rebuild_drops_obsolete_listed_sub_table_key(listed_section: dict[str, Any]) -> None:
    """上市旧键「单位名称」残留会成为附注空 TAB → 重建时删除。"""
    legacy = {
        "_tables": [],
        "sub_table_data": {"单位名称": [{"label": "甲"}], "保留键": []},
        "_sub_table_columns": {"单位名称": [{"key": "label", "label": "单位名称"}]},
    }
    new_data, changes = rebuild_table_data(legacy, listed_section, "五、7")

    assert "单位名称" not in new_data["sub_table_data"]
    assert "保留键" in new_data["sub_table_data"]
    assert "单位名称" not in new_data["_sub_table_columns"]
    assert sum("单位名称" in c for c in changes) == 2
