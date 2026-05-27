"""Unit tests for backend/app/services/note_cell_merge.py.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.5
Design: D1 引擎重生成规则三态：auto / manual / locked

覆盖场景（≥ 12 用例）：
  1. 全 auto：合并后等价于直接用 new
  2. 全 manual：合并后 values 全等于 old.values；_cell_meta.manual_value 备份原始 old
  3. 全 locked：合并后 values 全等于 old.values；_cell_meta 不变
  4. 混合模式：每列不同 mode 都正确处理
  5. 长度不匹配：new > old → 多出来的列按 auto 处理
  6. 长度不匹配：new < old → 取 new 长度（按 new 权威）
  7. row label 对齐合并
  8. row label 不同 → index 兜底对齐
  9. 多表 schema (_tables) 正确处理
  10. 边界：None / {} / 缺 rows / 缺 values
  11. _cell_modes 缺 key 默认 auto
  12. manual_value 已存在不被覆盖（重复合并幂等）
  13. _legacy_row 标记：old 独有 row 追加并标 _legacy_row=True
  14. 现有字段 (formula_type / is_total / row_type) 保留
"""

from __future__ import annotations

import pytest

from app.services.note_cell_merge import (
    merge_row_preserving_cell_modes,
    merge_table_data_preserving_cell_modes,
)


# ---------------------------------------------------------------------------
# 单行合并：三态基本行为
# ---------------------------------------------------------------------------


def test_all_auto_uses_new_values() -> None:
    """场景 1：全 auto → 合并后所有 values = new.values."""
    old_row = {
        "label": "银行存款",
        "values": [100.0, 200.0],
        "_cell_modes": {"0": "auto", "1": "auto"},
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": "B-OLD-0"},
            "1": {"manual_value": None, "semantic": None, "binding_id": "B-OLD-1"},
        },
    }
    new_row = {
        "label": "银行存款",
        "values": [150.0, 250.0],
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": "closing_balance", "binding_id": "B-NEW-0"},
            "1": {"manual_value": None, "semantic": "opening_balance", "binding_id": "B-NEW-1"},
        },
    }

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert merged["values"] == [150.0, 250.0]
    # binding_id 应跟新算的
    assert merged["_cell_meta"]["0"]["binding_id"] == "B-NEW-0"
    assert merged["_cell_meta"]["1"]["binding_id"] == "B-NEW-1"
    # _cell_modes 复制 old
    assert merged["_cell_modes"] == {"0": "auto", "1": "auto"}


def test_all_manual_keeps_old_and_backs_up_manual_value() -> None:
    """场景 2：全 manual → 保留 old.values + manual_value 备份."""
    old_row = {
        "label": "银行存款",
        "values": [11000.0, 12000.0],
        "_cell_modes": {"0": "manual", "1": "manual"},
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": None},
            "1": {"manual_value": None, "semantic": None, "binding_id": None},
        },
    }
    new_row = {
        "label": "银行存款",
        "values": [99999.0, 88888.0],
    }

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert merged["values"] == [11000.0, 12000.0]
    # manual_value 备份
    assert merged["_cell_meta"]["0"]["manual_value"] == 11000.0
    assert merged["_cell_meta"]["1"]["manual_value"] == 12000.0


def test_all_locked_keeps_old_values_and_meta_untouched() -> None:
    """场景 3：全 locked → 保留 old.values；_cell_meta 不变（manual_value 不被回填）."""
    old_row = {
        "label": "银行存款",
        "values": [1000.0, 2000.0],
        "_cell_modes": {"0": "locked", "1": "locked"},
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": "B-OLD-0"},
            "1": {"manual_value": None, "semantic": None, "binding_id": "B-OLD-1"},
        },
    }
    new_row = {
        "label": "银行存款",
        "values": [3000.0, 4000.0],
    }

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert merged["values"] == [1000.0, 2000.0]
    # manual_value 不被填（locked 不动 _cell_meta）
    assert merged["_cell_meta"]["0"]["manual_value"] is None
    assert merged["_cell_meta"]["1"]["manual_value"] is None


def test_mixed_modes_each_cell_correct() -> None:
    """场景 4：混合 — col0 auto / col1 manual / col2 locked / col3 缺 key (默认 auto)."""
    old_row = {
        "label": "银行存款",
        "values": [10.0, 20.0, 30.0, 40.0],
        "_cell_modes": {"0": "auto", "1": "manual", "2": "locked"},  # col3 缺
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": "OLD-0"},
            "1": {"manual_value": None, "semantic": None, "binding_id": None},
            "2": {"manual_value": None, "semantic": None, "binding_id": None},
            "3": {"manual_value": None, "semantic": None, "binding_id": None},
        },
    }
    new_row = {
        "label": "银行存款",
        "values": [11.0, 22.0, 33.0, 44.0],
    }

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert merged["values"] == [11.0, 20.0, 30.0, 44.0]
    # col1 manual_value 备份
    assert merged["_cell_meta"]["1"]["manual_value"] == 20.0
    # col2 locked → manual_value 不动
    assert merged["_cell_meta"]["2"]["manual_value"] is None


# ---------------------------------------------------------------------------
# 长度不匹配
# ---------------------------------------------------------------------------


def test_new_more_columns_than_old_extras_use_new() -> None:
    """场景 5：new 比 old 多列 → 多出来的列按 auto（new 值）."""
    old_row = {
        "label": "X",
        "values": [1.0, 2.0],
        "_cell_modes": {"0": "manual", "1": "manual"},
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": None},
            "1": {"manual_value": None, "semantic": None, "binding_id": None},
        },
    }
    new_row = {"label": "X", "values": [10.0, 20.0, 30.0, 40.0]}

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert len(merged["values"]) == 4
    assert merged["values"][0] == 1.0  # manual
    assert merged["values"][1] == 2.0  # manual
    assert merged["values"][2] == 30.0  # 新出现的，auto 默认
    assert merged["values"][3] == 40.0


def test_new_fewer_columns_than_old_uses_new_length() -> None:
    """场景 6：new 比 old 少列 → 取 new 长度."""
    old_row = {
        "label": "X",
        "values": [1.0, 2.0, 3.0, 4.0],
        "_cell_modes": {"0": "manual", "1": "manual", "2": "manual", "3": "manual"},
        "_cell_meta": {
            str(i): {"manual_value": None, "semantic": None, "binding_id": None}
            for i in range(4)
        },
    }
    new_row = {"label": "X", "values": [10.0, 20.0]}

    merged = merge_row_preserving_cell_modes(old_row, new_row)

    assert len(merged["values"]) == 2
    assert merged["values"] == [1.0, 2.0]


# ---------------------------------------------------------------------------
# 边界
# ---------------------------------------------------------------------------


def test_old_row_none_returns_deepcopy_of_new() -> None:
    """场景 10：old 为 None → 返回 new 的深拷贝（auto 默认）."""
    new_row = {"label": "X", "values": [1.0, 2.0]}
    merged = merge_row_preserving_cell_modes(None, new_row)
    assert merged["values"] == [1.0, 2.0]
    assert merged["_cell_modes"] == {}
    assert merged["_cell_meta"] == {}
    # 独立对象
    merged["values"][0] = 999
    assert new_row["values"][0] == 1.0


def test_both_none_returns_empty_dict() -> None:
    """场景 10：双 None → 空 dict."""
    assert merge_row_preserving_cell_modes(None, None) == {}


def test_old_row_empty_dict_safe() -> None:
    """场景 10：old 是空 dict → 等价于 None."""
    new_row = {"label": "X", "values": [1.0]}
    merged = merge_row_preserving_cell_modes({}, new_row)
    assert merged["values"] == [1.0]


def test_missing_cell_modes_defaults_to_auto() -> None:
    """场景 11：_cell_modes 完全缺失 → 全 auto 等价行为."""
    old_row = {"label": "X", "values": [99.0]}
    new_row = {"label": "X", "values": [42.0]}
    merged = merge_row_preserving_cell_modes(old_row, new_row)
    # 没有 modes → auto → 用 new
    assert merged["values"] == [42.0]


def test_manual_value_idempotent_on_repeated_merge() -> None:
    """场景 12：重复合并不重复覆盖 manual_value（应保持首次备份的原始值）."""
    old_row = {
        "label": "X",
        "values": [100.0],
        "_cell_modes": {"0": "manual"},
        "_cell_meta": {
            "0": {"manual_value": None, "semantic": None, "binding_id": None},
        },
    }
    new_row = {"label": "X", "values": [999.0]}

    # 第一次合并
    merged1 = merge_row_preserving_cell_modes(old_row, new_row)
    assert merged1["values"] == [100.0]
    assert merged1["_cell_meta"]["0"]["manual_value"] == 100.0

    # 模拟用户在前端把 values[0] 改成 200 — 但 manual_value 备份保留原始 100
    merged1["values"][0] = 200.0

    # 第二次合并 — manual_value 应保持 100（不被 200 覆盖）
    merged2 = merge_row_preserving_cell_modes(merged1, new_row)
    assert merged2["values"] == [200.0]
    assert merged2["_cell_meta"]["0"]["manual_value"] == 100.0


def test_existing_fields_preserved_from_old_when_new_missing() -> None:
    """场景 14：现有字段 (formula_type / is_total / row_type) — new 缺则用 old 兜底."""
    old_row = {
        "label": "本期合计",
        "values": [1.0],
        "is_total": True,
        "formula_type": "opening_plus_changes",
        "row_type": "subtotal",
        "_cell_modes": {"0": "auto"},
        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
    }
    # new 缺 row_type / formula_type / is_total
    new_row = {"label": "本期合计", "values": [2.0]}
    merged = merge_row_preserving_cell_modes(old_row, new_row)
    assert merged["row_type"] == "subtotal"
    assert merged["formula_type"] == "opening_plus_changes"
    assert merged["is_total"] is True


def test_new_row_type_overrides_old() -> None:
    """row_type new 优先（模板权威）."""
    old_row = {"label": "X", "values": [1.0], "row_type": "data"}
    new_row = {"label": "X", "values": [2.0], "row_type": "subtotal"}
    merged = merge_row_preserving_cell_modes(old_row, new_row)
    assert merged["row_type"] == "subtotal"


def test_pure_function_does_not_mutate_input() -> None:
    """纯函数性：入参不被修改."""
    old_row = {
        "label": "X",
        "values": [10.0],
        "_cell_modes": {"0": "manual"},
        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
    }
    new_row = {"label": "X", "values": [99.0]}
    old_snapshot = {
        "label": "X",
        "values": [10.0],
        "_cell_modes": {"0": "manual"},
        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
    }
    new_snapshot = {"label": "X", "values": [99.0]}

    _ = merge_row_preserving_cell_modes(old_row, new_row)

    assert old_row == old_snapshot
    assert new_row == new_snapshot


# ---------------------------------------------------------------------------
# 表级合并
# ---------------------------------------------------------------------------


def test_table_label_alignment_merges_correct_rows() -> None:
    """场景 7：rows 按 label 对齐合并."""
    old_td = {
        "headers": ["项目", "期末", "期初"],
        "rows": [
            {
                "label": "B",
                "values": [200.0, 220.0],
                "_cell_modes": {"0": "manual", "1": "auto"},
                "_cell_meta": {
                    "0": {"manual_value": None, "semantic": None, "binding_id": None},
                    "1": {"manual_value": None, "semantic": None, "binding_id": None},
                },
            },
            {
                "label": "A",
                "values": [100.0, 120.0],
                "_cell_modes": {"0": "auto", "1": "auto"},
                "_cell_meta": {
                    "0": {"manual_value": None, "semantic": None, "binding_id": None},
                    "1": {"manual_value": None, "semantic": None, "binding_id": None},
                },
            },
        ],
    }
    new_td = {
        "headers": ["项目", "期末", "期初"],
        "rows": [
            {"label": "A", "values": [101.0, 121.0]},
            {"label": "B", "values": [201.0, 221.0]},
        ],
    }

    merged = merge_table_data_preserving_cell_modes(old_td, new_td)

    # A row：全 auto → 用 new
    a_row = merged["rows"][0]
    assert a_row["label"] == "A"
    assert a_row["values"] == [101.0, 121.0]

    # B row：col0 manual → 保留 old.values[0]=200；col1 auto → 用 new
    b_row = merged["rows"][1]
    assert b_row["label"] == "B"
    assert b_row["values"] == [200.0, 221.0]
    assert b_row["_cell_meta"]["0"]["manual_value"] == 200.0


def test_table_index_fallback_when_label_mismatch() -> None:
    """场景 8：rows label 不同 → index 兜底对齐."""
    old_td = {
        "rows": [
            {
                "label": "",  # 空 label
                "values": [10.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
            },
        ],
    }
    new_td = {
        "rows": [
            {"label": "", "values": [99.0]},
        ],
    }

    merged = merge_table_data_preserving_cell_modes(old_td, new_td)

    # 空 label，用 index 0 对齐 → manual 保留 old
    assert merged["rows"][0]["values"] == [10.0]


def test_legacy_row_appended_when_old_extra() -> None:
    """场景 13：old 独有 row → 追加并标 _legacy_row=True."""
    old_td = {
        "rows": [
            {"label": "A", "values": [1.0], "_cell_modes": {"0": "auto"},
             "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}}},
            {"label": "X-USER-ADDED", "values": [99.0], "_cell_modes": {"0": "manual"},
             "_cell_meta": {"0": {"manual_value": 99.0, "semantic": None, "binding_id": None}}},
        ],
    }
    new_td = {
        "rows": [
            {"label": "A", "values": [10.0]},
        ],
    }

    merged = merge_table_data_preserving_cell_modes(old_td, new_td)

    assert len(merged["rows"]) == 2
    assert merged["rows"][0]["label"] == "A"
    assert merged["rows"][1]["label"] == "X-USER-ADDED"
    assert merged["rows"][1]["_legacy_row"] is True
    # 其 manual_value 保留
    assert merged["rows"][1]["_cell_meta"]["0"]["manual_value"] == 99.0


def test_multi_table_schema_merges_each_table() -> None:
    """场景 9：多表 schema (_tables) — 按 _tables[i] 同样规则合并."""
    old_td = {
        "headers": ["x"],
        "rows": [],
        "_tables": [
            {
                "name": "T1",
                "headers": ["项目", "期末"],
                "rows": [
                    {
                        "label": "A",
                        "values": [100.0],
                        "_cell_modes": {"0": "manual"},
                        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
                    }
                ],
            },
            {
                "name": "T2",
                "headers": ["项目", "本期"],
                "rows": [
                    {
                        "label": "B",
                        "values": [50.0],
                        "_cell_modes": {"0": "auto"},
                        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
                    }
                ],
            },
        ],
    }
    new_td = {
        "headers": ["项目", "期末"],
        "rows": [{"label": "A", "values": [999.0]}],
        "_tables": [
            {
                "name": "T1",
                "headers": ["项目", "期末"],
                "rows": [{"label": "A", "values": [999.0]}],
            },
            {
                "name": "T2",
                "headers": ["项目", "本期"],
                "rows": [{"label": "B", "values": [60.0]}],
            },
        ],
    }

    merged = merge_table_data_preserving_cell_modes(old_td, new_td)

    assert len(merged["_tables"]) == 2
    # T1.A col0 manual → 保留 old=100
    t1_a = merged["_tables"][0]["rows"][0]
    assert t1_a["values"] == [100.0]
    assert t1_a["_cell_meta"]["0"]["manual_value"] == 100.0
    # T2.B col0 auto → 用 new=60
    t2_b = merged["_tables"][1]["rows"][0]
    assert t2_b["values"] == [60.0]
    # 顶层 headers/rows 镜像首张表
    assert merged["headers"] == merged["_tables"][0]["headers"]
    assert merged["rows"][0]["values"] == [100.0]


def test_table_data_none_or_empty_safe() -> None:
    """场景 10：None / {} / 缺 rows 都安全."""
    # 双 None → 空 dict
    assert merge_table_data_preserving_cell_modes(None, None) == {}

    # old None → deepcopy(new)
    new_td = {"rows": [{"label": "X", "values": [1.0]}]}
    merged = merge_table_data_preserving_cell_modes(None, new_td)
    assert merged["rows"][0]["values"] == [1.0]

    # new None → deepcopy(old)
    old_td = {"rows": [{"label": "X", "values": [99.0]}]}
    merged2 = merge_table_data_preserving_cell_modes(old_td, None)
    assert merged2["rows"][0]["values"] == [99.0]

    # 缺 rows 字段
    merged3 = merge_table_data_preserving_cell_modes({}, {"headers": ["x"]})
    assert "headers" in merged3


def test_pure_function_does_not_mutate_table_data() -> None:
    """纯函数性：入参 old_td / new_td 不被修改."""
    import copy

    old_td = {
        "rows": [
            {
                "label": "A",
                "values": [1.0],
                "_cell_modes": {"0": "manual"},
                "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
            }
        ],
    }
    new_td = {"rows": [{"label": "A", "values": [99.0]}]}
    old_snap = copy.deepcopy(old_td)
    new_snap = copy.deepcopy(new_td)

    _ = merge_table_data_preserving_cell_modes(old_td, new_td)

    assert old_td == old_snap
    assert new_td == new_snap
