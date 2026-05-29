"""Sprint A.2 Batch 1 — dynamic_region_engine 单元测试.

A.2.1 行展开 / A.2.2 列展开 + 多级表头 / A.2.7 label 自动填充 + 纯函数 / 幂等。
Validates: Requirements D1 / D2 / CI-1 / CI-3
"""

from __future__ import annotations

import copy
import logging

from app.services.dynamic_region_engine import (
    auto_populate_row_labels,
    expand_dynamic_columns,
    expand_dynamic_rows,
)


def _row(label, values=None, row_type="data", **extra):
    out = {"label": label, "values": values or [], "row_type": row_type}
    out.update(extra)
    return out


def _col(cid, label="", header_path=None, col_type="fixed", **extra):
    out = {"id": cid, "label": label,
           "header_path": header_path or [label or cid], "col_type": col_type}
    out.update(extra)
    return out


def _rr(name, start, end, source="manual"):
    return {"name": name, "axis": "row", "start_idx": start, "end_idx": end,
            "dynamic_source": source}


def _cr(name, start, end, source="manual"):
    return {"name": name, "axis": "column", "start_idx": start, "end_idx": end,
            "dynamic_source": source}



# A.2.1 行展开 ------------------------------------------------------------


class TestRowExpansion:

    def test_empty_region_no_change(self):
        td = {"rows": [_row("项目", row_type="header_label"),
                       _row("", row_type="dynamic_anchor")],
              "_dynamic_regions": [_rr("客户", 1, 1)]}
        assert expand_dynamic_rows(td, ctx={})["rows"][1]["row_type"] == "dynamic_anchor"

    def test_single_anchor_explode_3_items(self):
        td = {"rows": [
            _row("客户清单", row_type="header_label"),
            _row("", values=[None, None], row_type="dynamic_anchor"),
            _row("合计", values=[0, 0], row_type="total", is_total=True),
        ], "_dynamic_regions": [_rr("客户", 1, 1)]}
        ctx = {"manual": {"客户": [
            {"label": "客户A", "values": [100, 200]},
            {"label": "客户B", "values": [300, 400]},
            {"label": "客户C", "values": [500, 600]},
        ]}}
        result = expand_dynamic_rows(td, ctx=ctx)
        rows = result["rows"]
        assert len(rows) == 6
        assert rows[1]["label"] == "客户A" and rows[1]["values"] == [100, 200]
        assert rows[1]["row_type"] == "dynamic_data"
        assert rows[3]["label"] == "客户C"
        assert rows[4]["row_type"] == "dynamic_marker_end"
        assert rows[5]["label"] == "合计"
        r = result["_dynamic_regions"][0]
        assert r["start_idx"] == 1 and r["end_idx"] == 4



    def test_multiple_regions_independent(self):
        td = {"rows": [
            _row("客户", row_type="header_label"),
            _row("", values=[None], row_type="dynamic_anchor"),
            _row("供应商", row_type="header_label"),
            _row("", values=[None], row_type="dynamic_anchor"),
        ], "_dynamic_regions": [_rr("cust", 1, 1), _rr("supp", 3, 3)]}
        ctx = {"manual": {
            "cust": [{"label": "C1", "values": [10]}, {"label": "C2", "values": [20]}],
            "supp": [{"label": "S1", "values": [30]}],
        }}
        result = expand_dynamic_rows(td, ctx=ctx)
        labels = [r["label"] for r in result["rows"]]
        assert labels == ["客户", "C1", "C2", "", "供应商", "S1", ""]
        regs = result["_dynamic_regions"]
        cust = next(r for r in regs if r["name"] == "cust")
        supp = next(r for r in regs if r["name"] == "supp")
        assert cust["end_idx"] == 3 and supp["start_idx"] == 5

    def test_dynamic_source_manual_top_level_items(self):
        td = {"rows": [_row("", values=[None], row_type="dynamic_anchor")],
              "_dynamic_regions": [_rr("x", 0, 0)]}
        ctx = {"items": [{"label": "a", "values": [1]}, {"label": "b", "values": [2]}]}
        assert [r["label"] for r in expand_dynamic_rows(td, ctx=ctx)["rows"][:2]] == ["a", "b"]

    def test_region_with_subtotal_preserved(self):
        td = {"rows": [
            _row("客户", row_type="header_label"),
            _row("", values=[None, None], row_type="dynamic_anchor"),
            _row("小计", values=[0, 0], row_type="subtotal", is_total=True),
            _row("合计", values=[0, 0], row_type="total", is_total=True),
        ], "_dynamic_regions": [_rr("客户", 1, 1)]}
        ctx = {"manual": {"客户": [{"label": "A", "values": [1, 2]}]}}
        result = expand_dynamic_rows(td, ctx=ctx)
        assert [r["row_type"] for r in result["rows"]] == [
            "header_label", "dynamic_data", "dynamic_marker_end",
            "subtotal", "total",
        ]
        assert result["rows"][3]["label"] == "小计"
        assert result["rows"][4]["label"] == "合计"



# A.2.2 列展开 ------------------------------------------------------------


class TestColumnExpansion:

    def test_empty_column_region_no_change(self):
        td = {"_columns_meta": [_col("c1", "项目"), _col("c2", "金额")],
              "rows": [_row("a", values=["A", 100])],
              "_dynamic_regions": [_cr("扩展", 2, 2)]}
        result = expand_dynamic_columns(td, ctx={})
        assert len(result["_columns_meta"]) == 2
        assert result["rows"][0]["values"] == ["A", 100]

    def test_add_2_columns_extends_meta_and_values(self):
        td = {"_columns_meta": [_col("c_label", "项目"), _col("c_amount", "金额")],
              "rows": [_row("X", values=["X", 10]), _row("Y", values=["Y", 20])],
              "_dynamic_regions": [_cr("ext", 2, 2)]}
        ctx = {"columns": {"ext": [
            _col("c_new1", "新列1", col_type="dynamic"),
            _col("c_new2", "新列2", col_type="dynamic"),
        ]}}
        result = expand_dynamic_columns(td, ctx=ctx)
        assert [c["id"] for c in result["_columns_meta"]] == [
            "c_label", "c_amount", "c_new1", "c_new2"]
        assert result["rows"][0]["values"] == ["X", 10, None, None]
        assert result["rows"][1]["values"] == ["Y", 20, None, None]
        assert result["_dynamic_regions"][0]["end_idx"] == 3

    def test_multi_level_header_preserved(self):
        td = {"_columns_meta": [_col("c_label", "项目")],
              "rows": [_row("A", values=["A"])],
              "_dynamic_regions": [_cr("y", 1, 1)]}
        ctx = {"columns": {"y": [
            {"id": "c_2024_end", "label": "期末",
             "header_path": ["本年", "期末"], "col_type": "dynamic"},
            {"id": "c_2024_start", "label": "期初",
             "header_path": ["本年", "期初"], "col_type": "dynamic"},
        ]}}
        result = expand_dynamic_columns(td, ctx=ctx)
        assert result["_columns_meta"][1]["header_path"] == ["本年", "期末"]
        assert result["_columns_meta"][2]["header_path"] == ["本年", "期初"]

    def test_column_id_uniqueness_ci3(self):
        td = {"_columns_meta": [_col("c_label", "项目"), _col("c_dup", "已有")],
              "rows": [_row("A", values=["A", 1])],
              "_dynamic_regions": [_cr("z", 2, 2)]}
        ctx = {"columns": {"z": [
            _col("c_dup", "重复", col_type="dynamic"),
            _col("c_unique", "新增", col_type="dynamic"),
        ]}}
        result = expand_dynamic_columns(td, ctx=ctx)
        ids = [c["id"] for c in result["_columns_meta"]]
        assert len(ids) == len(set(ids))
        assert "c_unique" in ids
        assert ids.count("c_dup") == 1



# A.2.7 label 自动填充 ----------------------------------------------------


class TestAutoPopulateLabels:

    def test_empty_label_filled_from_ctx(self):
        td = {"rows": [_row("", values=[v], row_type="dynamic_data") for v in (1, 2, 3)],
              "_dynamic_regions": [_rr("客户", 0, 2, source="aux_balance")]}
        ctx = {"labels": {"客户": ["客户A", "客户B", "客户C"]}}
        result = auto_populate_row_labels(td, ctx=ctx)
        assert [r["label"] for r in result["rows"]] == ["客户A", "客户B", "客户C"]

    def test_existing_label_preserved(self):
        td = {"rows": [
            _row("已填", values=[1], row_type="dynamic_data"),
            _row("", values=[2], row_type="dynamic_data"),
        ], "_dynamic_regions": [_rr("x", 0, 1)]}
        ctx = {"labels": {"x": ["新A", "新B"]}}
        result = auto_populate_row_labels(td, ctx=ctx)
        assert result["rows"][0]["label"] == "已填"
        assert result["rows"][1]["label"] == "新A"

    def test_mismatched_count_partial_fill(self, caplog):
        td = {"rows": [_row("", values=[v], row_type="dynamic_data") for v in (1, 2, 3)],
              "_dynamic_regions": [_rr("x", 0, 2)]}
        ctx = {"labels": {"x": ["A"]}}
        with caplog.at_level(logging.WARNING, logger="app.services.dynamic_region_engine"):
            result = auto_populate_row_labels(td, ctx=ctx)
        assert [r["label"] for r in result["rows"]] == ["A", "", ""]
        assert any("partial fill" in m for m in caplog.messages)



# 纯函数 / 幂等 / round-trip ----------------------------------------------


class TestPurityAndIdempotent:

    def test_input_unchanged_after_call_pure(self):
        td = {"rows": [
            _row("", values=[None], row_type="dynamic_anchor"),
            _row("合计", values=[0], row_type="total", is_total=True),
        ], "_dynamic_regions": [_rr("x", 0, 0)]}
        original = copy.deepcopy(td)
        ctx = {"manual": {"x": [{"label": "A", "values": [1]}]}}
        _ = expand_dynamic_rows(td, ctx=ctx)
        assert td == original

    def test_idempotent_double_expansion(self):
        td = {"rows": [_row("", values=[None], row_type="dynamic_anchor")],
              "_dynamic_regions": [_rr("x", 0, 0)]}
        ctx = {"manual": {"x": [
            {"label": "A", "values": [1]},
            {"label": "B", "values": [2]},
        ]}}
        first = expand_dynamic_rows(td, ctx=ctx)
        second = expand_dynamic_rows(first, ctx=ctx)
        assert first["rows"] == second["rows"]
        assert first["_dynamic_regions"] == second["_dynamic_regions"]

    def test_round_trip_expand_reload_expand(self):
        td = {"_columns_meta": [_col("c_label", "项目"), _col("c_amt", "金额")],
              "rows": [
                  _row("", values=[None, None], row_type="dynamic_anchor"),
                  _row("合计", values=[0, 0], row_type="total", is_total=True),
              ], "_dynamic_regions": [_rr("x", 0, 0)]}
        ctx = {"manual": {"x": [
            {"label": "A", "values": [1, 2]},
            {"label": "B", "values": [3, 4]},
        ]}}
        out1 = expand_dynamic_rows(td, ctx=ctx)
        out2 = expand_dynamic_rows(copy.deepcopy(out1), ctx=ctx)
        assert out1["rows"] == out2["rows"]
        assert out1["_dynamic_regions"] == out2["_dynamic_regions"]
