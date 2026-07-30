"""seed 列元数据贯通到附注 table_data（_carry_seed_column_meta）。

覆盖 design Property 9（缺省无副作用）/ Property 10（不干扰 workpaper 投影）。

spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ R5
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.disclosure_engine import (
    _SEED_COLUMN_META_KEYS,
    _carry_seed_column_meta,
)

LISTED_INVENTORY_COLUMNS: list[dict[str, Any]] = [
    {"key": "label", "label": "项目", "is_label": True},
    {"key": "end_gross", "label": "账面余额", "group": "期末余额"},
    {"key": "end_impairment", "label": "跌价准备/合同履约成本减值准备", "group": "期末余额"},
    {"key": "end_net", "label": "账面价值", "group": "期末余额"},
]
LISTED_INVENTORY_GROUPS: list[dict[str, Any]] = [
    {"group": "期末余额", "start": 1, "span": 3},
]


class TestCarrySeedColumnMeta:
    def test_carries_columns_and_column_groups(self) -> None:
        """R5.1：seed 声明的两级表头元数据透传到生成的 table_data。"""
        seed = {
            "name": "存货分类",
            "headers": ["项目", "账面余额", "跌价准备/合同履约成本减值准备", "账面价值"],
            "columns": LISTED_INVENTORY_COLUMNS,
            "_column_groups": LISTED_INVENTORY_GROUPS,
        }
        built = {"name": "存货分类", "headers": seed["headers"], "rows": []}

        _carry_seed_column_meta(seed, built)

        assert built["columns"] == LISTED_INVENTORY_COLUMNS
        assert built["_column_groups"] == LISTED_INVENTORY_GROUPS

    def test_no_keys_written_when_seed_silent(self) -> None:
        """Property 9：seed 未声明 → 一个键都不写（既有章节零影响）。"""
        seed = {"name": "某表", "headers": ["项目", "期末余额"], "rows": []}
        built = {"name": "某表", "headers": seed["headers"], "rows": []}
        before = dict(built)

        _carry_seed_column_meta(seed, built)

        assert built == before
        for key in _SEED_COLUMN_META_KEYS:
            assert key not in built

    @pytest.mark.parametrize(
        "bad_value",
        [None, [], {}, "columns", 0, False],
        ids=["none", "empty_list", "dict", "str", "int", "bool"],
    )
    def test_illegal_or_empty_values_are_ignored(self, bad_value: Any) -> None:
        """Property 9：空 / 非 list 类型不写入，避免污染 table_data。"""
        seed = {"columns": bad_value, "_column_groups": bad_value}
        built: dict[str, Any] = {"headers": [], "rows": []}

        _carry_seed_column_meta(seed, built)

        for key in _SEED_COLUMN_META_KEYS:
            assert key not in built

    def test_does_not_overwrite_existing_built_meta(self) -> None:
        """built 已有列元数据（如底稿投影已填）→ 不覆盖。"""
        existing = [{"key": "label", "label": "底稿投影列"}]
        seed = {"columns": LISTED_INVENTORY_COLUMNS, "_column_groups": LISTED_INVENTORY_GROUPS}
        built: dict[str, Any] = {"headers": [], "rows": [], "columns": existing}

        _carry_seed_column_meta(seed, built)

        assert built["columns"] == existing
        # 未冲突的键仍补写
        assert built["_column_groups"] == LISTED_INVENTORY_GROUPS

    def test_is_idempotent(self) -> None:
        """Property 8 同源：重复调用结果稳定。"""
        seed = {"columns": LISTED_INVENTORY_COLUMNS, "_column_groups": LISTED_INVENTORY_GROUPS}
        built: dict[str, Any] = {"headers": [], "rows": []}

        _carry_seed_column_meta(seed, built)
        snapshot = {k: v for k, v in built.items()}
        _carry_seed_column_meta(seed, built)

        assert built == snapshot

    @pytest.mark.parametrize(
        "seed,built",
        [(None, {}), ({}, None), ("seed", {}), ({}, [])],
        ids=["seed_none", "built_none", "seed_str", "built_list"],
    )
    def test_tolerates_non_dict_inputs(self, seed: Any, built: Any) -> None:
        """非 dict 入参静默返回，不抛错（生成流程不因此中断）。"""
        _carry_seed_column_meta(seed, built)


class TestWorkpaperProjectionUnaffected:
    """Property 10：workpaper 来源仍走 project_sub_tables，R5 改动不参与。"""

    def test_workpaper_source_still_projected_by_sub_table_projector(self) -> None:
        from app.services.note_sub_table_projector import project_sub_tables

        table_data = {
            "_source": "workpaper",
            "sub_table_data": {
                "存货分类": [
                    {"label": "原材料", "end_gross": 100, "end_impairment": 10, "end_net": 90},
                    {"label": "合计", "end_gross": 100, "end_impairment": 10, "end_net": 90,
                     "is_total": True},
                ],
            },
            "_sub_table_columns": {"存货分类": LISTED_INVENTORY_COLUMNS},
        }

        tables = project_sub_tables(table_data)

        assert tables is not None and len(tables) == 1
        t = tables[0]
        assert t["name"] == "存货分类"
        assert t["headers"] == ["项目", "账面余额", "跌价准备/合同履约成本减值准备", "账面价值"]
        # ColumnDef.group → _column_groups（两级表头由投影器自动产出）
        assert t["_column_groups"] == LISTED_INVENTORY_GROUPS
        assert t["rows"][-1]["is_total"] is True

    def test_non_workpaper_source_returns_none(self) -> None:
        """seed 生成的附注 _source 不在 workpaper 集合 → 投影器不介入（路径互斥）。"""
        from app.services.note_sub_table_projector import project_sub_tables

        assert project_sub_tables({"_source": "template", "sub_table_data": {}}) is None
        assert project_sub_tables({"sub_table_data": {}}) is None
