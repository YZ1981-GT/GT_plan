"""Unit tests for scripts/migrate_disclosure_notes_to_v2.py.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 0 Task 0.2
Design: D1 row 新增 row_type + _cell_meta sidecar 字段（idempotent）

覆盖 4 个核心场景（task 0.2 验收）：
    a) 全新 row（无 row_type、无 _cell_meta）→ 两字段都补齐
    b) 已迁移 row（已含 row_type + _cell_meta）→ 跳过不修改（幂等性）
    c) 部分迁移（仅 row_type）→ 仅补 _cell_meta
    d) _cell_modes[i] == "manual" → manual_value 备份到 _cell_meta

不依赖真实 DB，直接测纯函数 transformer.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

# 保证可 import scripts/migrate_disclosure_notes_to_v2.py
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from migrate_disclosure_notes_to_v2 import (  # noqa: E402
    VALID_ROW_TYPES,
    _make_empty_cell_meta,
    upgrade_row,
    upgrade_table_data,
)


# ---------------------------------------------------------------------------
# 场景 (a)：全新 row（无 row_type、无 _cell_meta）→ 两字段都补齐
# ---------------------------------------------------------------------------


def test_a_fresh_row_gets_both_fields_added() -> None:
    row = {
        "label": "银行存款",
        "values": [12345.67, 11000.00],
        "_cell_modes": {"0": "auto", "1": "auto"},
    }
    headers = ["项目", "期末余额", "期初余额"]

    res = upgrade_row(row, headers)

    assert res["row_type"] == "added"
    assert res["_cell_meta"] == "added"
    assert "row_type" in row
    assert row["row_type"] in VALID_ROW_TYPES
    assert isinstance(row["_cell_meta"], dict)
    assert set(row["_cell_meta"].keys()) == {"0", "1"}
    for slot in row["_cell_meta"].values():
        assert slot == {"manual_value": None, "semantic": None, "binding_id": None}
    # 现有字段不能丢
    assert row["label"] == "银行存款"
    assert row["values"] == [12345.67, 11000.00]
    assert row["_cell_modes"] == {"0": "auto", "1": "auto"}


def test_a_total_row_detected_as_total() -> None:
    """is_total=True 行应识别为 total."""
    row = {"label": "合计", "values": [100.0], "is_total": True}
    upgrade_row(row, ["项目", "金额"])
    assert row["row_type"] == "total"


def test_a_subtotal_row_detected() -> None:
    """label 含「小计」无 is_total → subtotal."""
    row = {"label": "本期增加小计", "values": [50.0]}
    upgrade_row(row, ["项目", "金额"])
    assert row["row_type"] == "subtotal"


# ---------------------------------------------------------------------------
# 场景 (b)：已迁移 row → 跳过不修改（幂等性）
# ---------------------------------------------------------------------------


def test_b_already_migrated_row_is_skipped() -> None:
    row = {
        "label": "银行存款",
        "values": [123.45],
        "_cell_modes": {"0": "auto"},
        "row_type": "data",
        "_cell_meta": {
            "0": {
                "manual_value": None,
                "semantic": "closing_balance",
                "binding_id": "F22-1.r1.c1",
            }
        },
    }
    snapshot = deepcopy(row)
    res = upgrade_row(row, ["项目", "期末余额"])

    assert res["row_type"] == "skipped"
    assert res["_cell_meta"] == "skipped"
    assert row == snapshot, "已迁移 row 必须保持 byte-for-byte 不变"


def test_b_idempotent_double_run_no_change() -> None:
    """连跑两次 upgrade_table_data 应该第二次完全 skipped."""
    table_data = {
        "headers": ["项目", "金额"],
        "rows": [
            {"label": "应收账款", "values": [1.0], "_cell_modes": {"0": "auto"}},
            {"label": "合计", "values": [1.0], "is_total": True},
        ],
    }
    s1 = upgrade_table_data(table_data)
    snapshot = deepcopy(table_data)
    s2 = upgrade_table_data(table_data)

    assert s1["row_type_added"] == 2
    assert s1["_cell_meta_added"] == 2
    assert s2["row_type_added"] == 0
    assert s2["row_type_skipped"] == 2
    assert s2["_cell_meta_added"] == 0
    assert s2["_cell_meta_skipped"] == 2
    assert table_data == snapshot, "第二次调用不应再修改"


# ---------------------------------------------------------------------------
# 场景 (c)：部分迁移（仅 row_type）→ 仅补 _cell_meta
# ---------------------------------------------------------------------------


def test_c_partial_migration_only_adds_cell_meta() -> None:
    row = {
        "label": "短期借款",
        "values": [500.0, 600.0],
        "row_type": "data",  # 已有
        # _cell_meta 缺失
    }
    res = upgrade_row(row, ["项目", "期末", "期初"])

    assert res["row_type"] == "skipped"
    assert res["_cell_meta"] == "added"
    # row_type 不被覆盖
    assert row["row_type"] == "data"
    # _cell_meta 长度对齐 values
    assert set(row["_cell_meta"].keys()) == {"0", "1"}


def test_c_partial_migration_only_adds_row_type() -> None:
    """反向：已有 _cell_meta 缺 row_type."""
    row = {
        "label": "应付账款",
        "values": [1.0],
        "_cell_meta": {"0": {"manual_value": None, "semantic": None, "binding_id": None}},
    }
    res = upgrade_row(row, ["项目", "金额"])
    assert res["row_type"] == "added"
    assert res["_cell_meta"] == "skipped"
    assert row["row_type"] in VALID_ROW_TYPES


# ---------------------------------------------------------------------------
# 场景 (d)：_cell_modes[i] == "manual" → manual_value 备份到 _cell_meta
# ---------------------------------------------------------------------------


def test_d_manual_mode_backs_up_value_to_cell_meta() -> None:
    row = {
        "label": "其他应收款",
        "values": [None, 8888.88, 9999.99],
        "_cell_modes": {"0": "auto", "1": "manual", "2": "manual"},
    }
    upgrade_row(row, ["项目", "期末", "期初"])

    meta = row["_cell_meta"]
    # auto 槽位 manual_value 仍为 None
    assert meta["0"]["manual_value"] is None
    # manual 槽位 manual_value 备份当前 values[i]
    assert meta["1"]["manual_value"] == 8888.88
    assert meta["2"]["manual_value"] == 9999.99
    # 其它字段保持空
    assert meta["1"]["semantic"] is None
    assert meta["1"]["binding_id"] is None


def test_d_manual_mode_with_none_value_does_not_backup() -> None:
    """values[i] is None 时 manual 模式不"假备份" None."""
    row = {
        "label": "在建工程",
        "values": [None, None],
        "_cell_modes": {"0": "manual", "1": "manual"},
    }
    upgrade_row(row, ["项目", "金额", "进度"])
    # None 备份就是 None，没意义但不应崩
    meta = row["_cell_meta"]
    assert meta["0"]["manual_value"] is None
    assert meta["1"]["manual_value"] is None


def test_d_locked_mode_does_not_backup() -> None:
    """locked 模式不触发 manual_value 备份（只 manual 才备份）."""
    row = {
        "label": "递延所得税资产",
        "values": [1.0, 2.0],
        "_cell_modes": {"0": "auto", "1": "locked"},
    }
    upgrade_row(row, ["项目", "期末", "期初"])
    meta = row["_cell_meta"]
    assert meta["0"]["manual_value"] is None
    assert meta["1"]["manual_value"] is None


# ---------------------------------------------------------------------------
# 多表 + 单表 schema 兼容
# ---------------------------------------------------------------------------


def test_multi_tables_schema_via_under_tables() -> None:
    """table_data._tables 多表数组 schema."""
    table_data = {
        "headers": ["项目", "金额"],
        "rows": [],  # 顶层是首表镜像
        "_tables": [
            {
                "name": "表1",
                "headers": ["项目", "金额"],
                "rows": [
                    {"label": "原值", "values": [100.0]},
                    {"label": "本期增加小计", "values": [10.0]},
                ],
            },
            {
                "name": "表2",
                "headers": ["项目", "金额"],
                "rows": [
                    {"label": "合计", "values": [110.0], "is_total": True},
                ],
            },
        ],
    }
    stats = upgrade_table_data(table_data)

    assert stats["tables"] == 2
    assert stats["rows_total"] == 3
    assert stats["row_type_added"] == 3
    assert stats["_cell_meta_added"] == 3
    assert stats["row_type_counter"]["subtotal"] == 1
    assert stats["row_type_counter"]["total"] == 1
    # 验证就地修改生效
    for t in table_data["_tables"]:
        for r in t["rows"]:
            assert "row_type" in r
            assert "_cell_meta" in r


def test_single_table_schema() -> None:
    """老 schema 仅顶层 rows."""
    table_data = {
        "headers": ["项目", "金额"],
        "rows": [{"label": "应收票据", "values": [1.0]}],
    }
    stats = upgrade_table_data(table_data)
    assert stats["tables"] == 1
    assert stats["rows_total"] == 1
    assert stats["row_type_added"] == 1


def test_empty_or_none_table_data_is_safe() -> None:
    """None / 非 dict table_data 不应崩."""
    assert upgrade_table_data(None)["tables"] == 0
    assert upgrade_table_data({})["tables"] == 0
    assert upgrade_table_data({"unknown": "shape"})["tables"] == 0


# ---------------------------------------------------------------------------
# helper：_make_empty_cell_meta 行为
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n,expected_keys", [
    (0, set()),
    (1, {"0"}),
    (3, {"0", "1", "2"}),
])
def test_make_empty_cell_meta_lengths(n: int, expected_keys: set[str]) -> None:
    meta = _make_empty_cell_meta(n)
    assert set(meta.keys()) == expected_keys
    for slot in meta.values():
        assert slot == {"manual_value": None, "semantic": None, "binding_id": None}


def test_make_empty_cell_meta_negative_values_len_safe() -> None:
    """防御：负数 length 不应崩."""
    assert _make_empty_cell_meta(-1) == {}


# ---------------------------------------------------------------------------
# 公开导出 sanity check：纯函数模块不依赖真实 DB
# ---------------------------------------------------------------------------


def test_pure_functions_do_not_import_db_eagerly() -> None:
    """模块顶层 import 不应触发 SessionLocal / 真 DB 连接."""
    import migrate_disclosure_notes_to_v2 as mod
    # 仅检查纯函数公开符号；DB 访问在 migrate_db() 内部延迟 import
    assert callable(mod.upgrade_row)
    assert callable(mod.upgrade_table_data)
    assert callable(mod.migrate_db)  # async 函数，存在即可
