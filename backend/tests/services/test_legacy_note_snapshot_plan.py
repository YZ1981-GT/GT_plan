"""legacy 快照迁移计划（纯函数）单测。

被测函数：`scripts/fix/migrate_legacy_note_snapshots.build_note_plan`

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R3 / Task 3.1-3.3
Properties: Property 6（迁移保结构：表数与行数守恒，`header_label` 行除外）
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "fix" / "migrate_legacy_note_snapshots.py"
)
_spec = importlib.util.spec_from_file_location("_legacy_migrate", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
# 必须先注册到 sys.modules：脚本内用了 @dataclass，其 _is_type 会按
# cls.__module__ 反查 sys.modules，未注册时抛 AttributeError
sys.modules["_legacy_migrate"] = mod
_spec.loader.exec_module(mod)


def _tpl(*names: str, with_columns: bool = True) -> list[dict[str, Any]]:
    return [
        {
            "name": n,
            "columns": (
                [{"key": "label", "label": "项目", "is_label": True, "flat": True}]
                if with_columns
                else None
            ),
        }
        for n in names
    ]


def _legacy_table(name: str, n_rows: int, *, headers: list[str] | None = None,
                  header_label_rows: int = 0) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        {"label": f"r{i}", "values": [None]} for i in range(n_rows)
    ]
    for i in range(header_label_rows):
        rows.insert(i, {"label": "表头行", "row_type": "header_label", "values": [None]})
    return {"name": name, "headers": headers or ["项目", "金额"], "rows": rows}


def _plan(table_data: dict[str, Any], template: list[dict[str, Any]] | None) -> Any:
    return mod.build_note_plan(
        note_id="n1",
        project="P",
        note_section="五、9",
        section_title="存货",
        table_data=table_data,
        template_tables=template,
    )


# ════════════════════════════════════════════════════════════════════
# by_name：表名有意义且与模板一一匹配
# ════════════════════════════════════════════════════════════════════


def test_by_name_when_all_names_match_template():
    td = {"_tables": [_legacy_table("存货分类", 3), _legacy_table("开发成本", 2)]}
    p = _plan(td, _tpl("存货分类", "开发成本"))
    assert p.kind == "by_name"
    assert [t.target_name for t in p.tables] == ["存货分类", "开发成本"]
    assert [t.row_count for t in p.tables] == [3, 2]
    assert all(t.columns_from_template for t in p.tables)
    assert p.is_actionable


def test_by_name_preserves_row_counts():
    """Property 6：行数守恒。"""
    td = {"_tables": [_legacy_table("A", 7), _legacy_table("B", 11)]}
    p = _plan(td, _tpl("A", "B"))
    assert p.legacy_row_total == 18
    assert p.planned_row_total == 18


def test_by_name_drops_header_label_rows():
    """Property 6 例外：`header_label` 假数据行必须删。"""
    td = {"_tables": [_legacy_table("A", 5, header_label_rows=2)]}
    p = _plan(td, _tpl("A"))
    assert p.kind == "by_name"
    assert p.tables[0].row_count == 5
    assert p.tables[0].dropped_header_label_rows == 2
    assert p.legacy_row_total == 7  # legacy 含 header_label


def test_by_name_flags_template_without_columns():
    """模板本身没 columns → 标记出来（迁移后投影会降级为只显示行名）。"""
    td = {"_tables": [_legacy_table("A", 1)]}
    p = _plan(td, _tpl("A", with_columns=False))
    assert p.kind == "by_name"
    assert p.tables[0].columns_from_template is False


# ════════════════════════════════════════════════════════════════════
# positional：表名不可用但表数与模板相等
# ════════════════════════════════════════════════════════════════════


def test_positional_when_names_duplicate():
    """实测形态：两张表都叫「项  目」（表头首格被当成表名）。"""
    td = {
        "_tables": [
            _legacy_table("项  目", 13, headers=["项  目", "金额"]),
            _legacy_table("项  目", 13, headers=["项  目", "金额"]),
        ]
    }
    p = _plan(td, _tpl("生产性生物资产", "生产性生物资产（续）"))
    assert p.kind == "positional"
    assert "重名" in p.reason
    assert [t.target_name for t in p.tables] == ["生产性生物资产", "生产性生物资产（续）"]
    assert [t.source_index for t in p.tables] == [0, 1]


def test_positional_when_name_equals_first_header():
    td = {"_tables": [_legacy_table("项目", 4, headers=["项目", "金额"])]}
    p = _plan(td, _tpl("存货分类"))
    assert p.kind == "positional"
    assert "表名非业务名" in p.reason


def test_positional_when_names_not_in_template():
    td = {"_tables": [_legacy_table("老表名", 4)]}
    p = _plan(td, _tpl("新表名"))
    assert p.kind == "positional"
    assert "不在模板中" in p.reason


def test_positional_reason_mentions_manual_check():
    """按序对齐有搬错表的风险 → reason 必须提示人工确认。"""
    td = {"_tables": [_legacy_table("项  目", 1), _legacy_table("项  目", 1)]}
    p = _plan(td, _tpl("A", "B"))
    assert "人工" in p.reason


@pytest.mark.parametrize("bad_name", ["项目", "项  目", "序号", "名称", "类别", "组合", "存货种类", "", "   "])
def test_meaningless_names_detected(bad_name: str):
    assert mod._name_is_meaningful(bad_name, ["X"]) is False


def test_name_equal_to_header0_is_meaningless():
    assert mod._name_is_meaningful("存货分类", ["存货分类", "金额"]) is False


def test_real_table_name_is_meaningful():
    assert mod._name_is_meaningful("确认为存货的数据资源", ["项目", "外购"]) is True


# ════════════════════════════════════════════════════════════════════
# single_row：只有顶层 rows
# ════════════════════════════════════════════════════════════════════


def test_single_row_when_template_has_exactly_one_table():
    td = {"rows": [{"label": "a", "values": [1]}, {"label": "b", "values": [2]}]}
    p = _plan(td, _tpl("唯一表"))
    assert p.kind == "single_row"
    assert p.tables[0].target_name == "唯一表"
    assert p.tables[0].source_index is None
    assert p.tables[0].row_count == 2


def test_single_row_drops_header_label():
    td = {
        "rows": [
            {"label": "表头", "row_type": "header_label", "values": []},
            {"label": "a", "values": [1]},
        ]
    }
    p = _plan(td, _tpl("唯一表"))
    assert p.tables[0].row_count == 1
    assert p.tables[0].dropped_header_label_rows == 1


def test_single_row_becomes_manual_when_template_has_multiple_tables():
    """无法判断这批行属于模板哪张表 → 人工。"""
    td = {"rows": [{"label": "a", "values": [1]}]}
    p = _plan(td, _tpl("A", "B"))
    assert p.kind == "manual"
    assert "无法确定归属" in p.reason


# ════════════════════════════════════════════════════════════════════
# manual：不可安全迁移
# ════════════════════════════════════════════════════════════════════


def test_manual_when_table_count_mismatch():
    td = {"_tables": [_legacy_table("项  目", 1)]}
    p = _plan(td, _tpl("A", "B", "C"))
    assert p.kind == "manual"
    assert "无法安全对齐" in p.reason
    assert p.is_actionable is False


def test_manual_when_template_section_absent():
    td = {"_tables": [_legacy_table("A", 1)]}
    p = _plan(td, None)
    assert p.kind == "manual"
    assert "模板" in p.reason


def test_manual_when_template_has_no_tables():
    td = {"_tables": [_legacy_table("A", 1)]}
    p = _plan(td, [])
    assert p.kind == "manual"


def test_manual_when_no_legacy_content():
    p = _plan({"rows": []}, _tpl("A"))
    assert p.kind == "manual"
    assert "既无" in p.reason


def test_manual_plans_are_not_actionable():
    p = _plan({"_tables": [_legacy_table("X", 1)]}, _tpl("A", "B"))
    assert p.is_actionable is False
    assert p.tables == []


# ════════════════════════════════════════════════════════════════════
# 健壮性
# ════════════════════════════════════════════════════════════════════


def test_ignores_non_dict_legacy_tables():
    td = {"_tables": ["oops", None, _legacy_table("A", 2)]}
    p = _plan(td, _tpl("A"))
    assert p.kind == "by_name"
    assert p.tables[0].row_count == 2


def test_ignores_non_dict_rows():
    td = {"_tables": [{"name": "A", "headers": ["x"], "rows": ["bad", None, {"label": "ok"}]}]}
    p = _plan(td, _tpl("A"))
    assert p.tables[0].row_count == 1


def test_tables_not_a_list_falls_back_to_rows():
    td = {"_tables": "oops", "rows": [{"label": "a"}]}
    p = _plan(td, _tpl("唯一表"))
    assert p.kind == "single_row"


def test_template_entries_without_name_ignored():
    td = {"_tables": [_legacy_table("A", 1)]}
    p = _plan(td, [{"columns": []}, *_tpl("A")])
    assert p.kind == "by_name"


def test_strip_header_labels_is_pure():
    rows = [{"row_type": "header_label"}, {"label": "a"}]
    kept, dropped = mod._strip_header_labels(rows)
    assert dropped == 1 and len(kept) == 1
    assert len(rows) == 2  # 入参未被修改
