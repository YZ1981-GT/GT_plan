"""Wave 2 / Task 3.1 — G7-2 aux 归集纯函数单测。

覆盖：字段映射、空名跳过、closing 优先、来源串、Persist_First / overwrite 合并、
保留权益法/减值行、行数上限截断。
"""

from __future__ import annotations

from app.routers.wp_render_strategies._g7_long_term_equity_main_import_export import (
    _G7_AUX_ACCOUNT_PREFIX,
    _merge_g7_cost_rows,
    build_g7_detail_rows_from_aux,
)


def _rid_factory():
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        return f"g7cost-{counter['n']}"

    return _make


class TestBuildFromAux:
    def test_maps_fields(self):
        rows = build_g7_detail_rows_from_aux(
            [("子公司甲", 100.0, 30.0, 10.0, 120.0)],
            aux_type="客户",
            row_id_factory=_rid_factory(),
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["section"] == "cost"
        assert r["investeeName"] == "子公司甲"
        assert r["openingAmount"] == 100.0
        assert r["increaseAmount"] == 30.0  # 借方增加
        assert r["decreaseAmount"] == 10.0  # 贷方减少
        assert r["closingAmount"] == 120.0  # closing 优先
        assert _G7_AUX_ACCOUNT_PREFIX in r["remark"] and "客户" in r["remark"]
        # 比例列不取数（宁缺勿造）
        assert r["investmentRatio"] == 0
        assert r["openingRatio"] == 0

    def test_closing_fallback_to_rollforward(self):
        # closing 缺失（0）→ 回退 opening+debit-credit
        rows = build_g7_detail_rows_from_aux(
            [("联营乙", 200.0, 50.0, 30.0, 0.0)],
            aux_type="客户",
            row_id_factory=_rid_factory(),
        )
        assert rows[0]["closingAmount"] == 220.0

    def test_skips_empty_name(self):
        rows = build_g7_detail_rows_from_aux(
            [("", 1.0, 0.0, 0.0, 1.0), ("  ", 2.0, 0.0, 0.0, 2.0), ("有效", 3.0, 0.0, 0.0, 3.0)],
            aux_type="客户",
            row_id_factory=_rid_factory(),
        )
        assert [r["investeeName"] for r in rows] == ["有效"]

    def test_row_limit_truncation(self):
        entries = [(f"单位{i}", 1.0, 0.0, 0.0, 1.0) for i in range(10)]
        rows = build_g7_detail_rows_from_aux(
            entries, aux_type="客户", row_limit=3, row_id_factory=_rid_factory()
        )
        assert len(rows) == 3

    def test_source_note_without_aux_type(self):
        rows = build_g7_detail_rows_from_aux(
            [("甲", 1.0, 0.0, 0.0, 1.0)], row_id_factory=_rid_factory()
        )
        assert rows[0]["remark"] == f"由辅助余额表({_G7_AUX_ACCOUNT_PREFIX})导入"


class TestMergeCostRows:
    def _aux_rows(self):
        return build_g7_detail_rows_from_aux(
            [("子公司甲", 100.0, 0.0, 0.0, 100.0), ("联营乙", 50.0, 0.0, 0.0, 50.0)],
            aux_type="客户",
            row_id_factory=_rid_factory(),
        )

    def test_persist_first_skips_existing(self):
        existing = [
            {"id": "e1", "section": "cost", "investeeName": "子公司甲", "openingAmount": 999.0},
            {"id": "eq1", "section": "equity", "investeeName": "合营丙", "openingAmount": 88.0},
        ]
        merged, affected = _merge_g7_cost_rows(existing, self._aux_rows(), overwrite=False)
        # 已存在的子公司甲不覆盖（保留 999），新增联营乙
        cost_jia = next(r for r in merged if r["investeeName"] == "子公司甲" and r["section"] == "cost")
        assert cost_jia["openingAmount"] == 999.0
        assert affected == 1  # 只新增联营乙
        # 权益法行保留
        assert any(r["section"] == "equity" and r["investeeName"] == "合营丙" for r in merged)

    def test_overwrite_updates_existing(self):
        existing = [{"id": "e1", "section": "cost", "investeeName": "子公司甲", "openingAmount": 999.0}]
        merged, affected = _merge_g7_cost_rows(existing, self._aux_rows(), overwrite=True)
        cost_jia = next(r for r in merged if r["investeeName"] == "子公司甲")
        assert cost_jia["openingAmount"] == 100.0  # 被覆盖
        assert affected == 2  # 覆盖甲 + 新增乙

    def test_name_normalization_matches(self):
        existing = [{"id": "e1", "section": "cost", "investeeName": " 子公司甲 ", "openingAmount": 999.0}]
        merged, affected = _merge_g7_cost_rows(existing, self._aux_rows(), overwrite=False)
        # 带空白的名称应归一化匹配为同一单位（不新增重复行）
        cost_count = sum(1 for r in merged if r["section"] == "cost" and "子公司甲" in r["investeeName"])
        assert cost_count == 1
        assert affected == 1  # 只新增联营乙

    def test_idempotent_second_merge(self):
        aux = self._aux_rows()
        merged1, _ = _merge_g7_cost_rows([], aux, overwrite=False)
        merged2, affected2 = _merge_g7_cost_rows(merged1, aux, overwrite=False)
        assert len(merged1) == len(merged2)  # 幂等，不重复
        assert affected2 == 0
