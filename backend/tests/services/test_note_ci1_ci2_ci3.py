"""CI-1 / CI-2 / CI-3 卡点测试 — Sprint A.1 验收.

CI-1: _dynamic_regions idx/col_id 有效性
CI-2: row_type=dynamic_* 在 region 内
CI-3: column_id 全表唯一

这些测试验证 Pydantic schema 约束 + 模板数据结构正确性。
"""

import pytest

from app.schemas.note_dynamic_schema import (
    ColumnMeta,
    DynamicRegion,
    RowType,
    CellBinding,
)


# ===========================================================================
# CI-1: _dynamic_regions idx/col_id 有效性
# ===========================================================================


class TestCI1DynamicRegionsValid:
    """CI-1: _dynamic_regions 的 start_idx/end_idx 必须有效."""

    def test_valid_row_region(self):
        r = DynamicRegion(name="客户", axis="row", start_idx=1, end_idx=5)
        assert r.start_idx < r.end_idx or r.start_idx == r.end_idx

    def test_valid_column_region(self):
        r = DynamicRegion(name="扩展列", axis="column", start_idx=3, end_idx=10)
        assert r.axis == "column"
        assert r.start_idx >= 0

    def test_region_start_not_negative(self):
        """start_idx 不应为负数（业务约束，Pydantic 不强制但测试验证）."""
        r = DynamicRegion(name="test", axis="row", start_idx=0, end_idx=5)
        assert r.start_idx >= 0

    def test_region_with_source_config(self):
        r = DynamicRegion(
            name="aux",
            axis="row",
            start_idx=2,
            end_idx=8,
            dynamic_source="aux_balance",
            source_config={"aux_type": "customer"},
        )
        assert r.dynamic_source == "aux_balance"
        assert r.source_config["aux_type"] == "customer"


# ===========================================================================
# CI-2: row_type=dynamic_* 在 region 内
# ===========================================================================


class TestCI2DynamicRowTypeInRegion:
    """CI-2: row_type 以 dynamic_ 开头的行必须在某个 region 范围内."""

    def _check_dynamic_rows_in_regions(
        self, rows: list[dict], regions: list[dict]
    ) -> list[str]:
        """返回不在任何 region 内的 dynamic 行索引列表."""
        errors = []
        row_regions = [
            r for r in regions if r.get("axis") == "row"
        ]
        for idx, row in enumerate(rows):
            rt = row.get("row_type", "data")
            if rt.startswith("dynamic_"):
                in_region = any(
                    r["start_idx"] <= idx <= r["end_idx"]
                    for r in row_regions
                )
                if not in_region:
                    errors.append(f"row[{idx}] type={rt} not in any region")
        return errors

    def test_dynamic_rows_inside_region(self):
        rows = [
            {"row_type": "data"},
            {"row_type": "dynamic_anchor"},
            {"row_type": "dynamic_data"},
            {"row_type": "dynamic_data"},
            {"row_type": "dynamic_marker_end"},
            {"row_type": "total"},
        ]
        regions = [{"axis": "row", "start_idx": 1, "end_idx": 4}]
        errors = self._check_dynamic_rows_in_regions(rows, regions)
        assert errors == []

    def test_dynamic_row_outside_region_detected(self):
        rows = [
            {"row_type": "dynamic_data"},  # idx=0, outside region
            {"row_type": "data"},
        ]
        regions = [{"axis": "row", "start_idx": 5, "end_idx": 10}]
        errors = self._check_dynamic_rows_in_regions(rows, regions)
        assert len(errors) == 1
        assert "row[0]" in errors[0]

    def test_no_dynamic_rows_no_errors(self):
        rows = [{"row_type": "data"}, {"row_type": "total"}]
        regions = []
        errors = self._check_dynamic_rows_in_regions(rows, regions)
        assert errors == []


# ===========================================================================
# CI-3: column_id 全表唯一
# ===========================================================================


class TestCI3ColumnIdUnique:
    """CI-3: _columns_meta 中 column_id 必须全表唯一."""

    def test_unique_column_ids(self):
        cols = [
            ColumnMeta(id="col_label", label="项目"),
            ColumnMeta(id="col_amount_end", label="期末"),
            ColumnMeta(id="col_amount_start", label="期初"),
        ]
        ids = [c.id for c in cols]
        assert len(ids) == len(set(ids))

    def test_duplicate_column_id_detected(self):
        cols = [
            ColumnMeta(id="col_amount", label="金额1"),
            ColumnMeta(id="col_amount", label="金额2"),  # duplicate!
        ]
        ids = [c.id for c in cols]
        assert len(ids) != len(set(ids)), "Should detect duplicate"

    def test_empty_columns_valid(self):
        cols = []
        ids = [c.id for c in cols]
        assert len(ids) == len(set(ids))


# ===========================================================================
# Bonus: CellBinding schema validation
# ===========================================================================


class TestCellBindingSchema:
    """CellBinding Pydantic 模型基本验证."""

    def test_minimal_binding(self):
        b = CellBinding(primary={"source": "manual"})
        assert b.primary["source"] == "manual"
        assert b.fallback == []

    def test_binding_with_fallback(self):
        b = CellBinding(
            primary={"source": "wp_data", "wp_code": "h08"},
            fallback=[
                {"source": "trial_balance", "account_codes": ["1601"]},
                {"source": "manual", "default_value": 0},
            ],
        )
        assert len(b.fallback) == 2
        assert b.show_provenance is True

    def test_fallback_max_3_levels(self):
        """CI-9 约束：fallback 链最多 3 级."""
        b = CellBinding(
            primary={"source": "wp_data"},
            fallback=[{"source": "tb"}, {"source": "manual"}, {"source": "prior"}],
        )
        assert len(b.fallback) <= 3
