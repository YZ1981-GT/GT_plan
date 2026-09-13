# -*- coding: utf-8 -*-
"""D4-9 Task 10 守卫：导入导出本期/上期 + 总额 + 专用 parser（行为级）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 10
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

from app.routers.wp_render_strategies import _d4_import_export as M


class _FakeWs:
    def __init__(self) -> None:
        self.rows: list[list] = []

    def append(self, row: list) -> None:
        self.rows.append(list(row))


D4_9_HEADERS = M._SHEET_HEADERS["D4-9"]


def _row(**kw) -> tuple:
    """按 D4-9 表头顺序造一行 tuple。"""
    order = ["期间", "序号", "客户名称", "销售金额", "销售金额占比", "销售数量", "销售数量占比", "上期排名"]
    return tuple(kw.get(h) for h in order)


class TestHeaders:
    def test_headers_have_period_ratio_and_columns(self) -> None:
        assert D4_9_HEADERS == ["期间", "序号", "客户名称", "销售金额", "销售金额占比", "销售数量", "销售数量占比", "上期排名"]

    def test_item_id_maps_to_data(self) -> None:
        assert M._resolve_item_id("D4-9") == "D4-9-data"

    def test_d4_9_supported(self) -> None:
        assert "D4-9" in M._SUPPORTED_SHEETS


class TestExport:
    def test_export_two_regions_with_totals(self) -> None:
        store = {
            "current": {
                "rows": [
                    {"rowId": "c1", "name": "客户甲", "amount": 1000, "quantity": 5, "priorRank": "2"},
                    {"rowId": "c2", "name": "客户乙", "amount": 3000, "quantity": 5, "priorRank": "1"},
                ],
                "totalAmount": 4000,
                "totalQuantity": 10,
            },
            "prior": {
                "rows": [{"rowId": "p1", "name": "客户丙", "amount": 500, "quantity": 3, "priorRank": ""}],
                "totalAmount": 500,
                "totalQuantity": 3,
            },
        }
        ws = _FakeWs()
        M._export_d4_9_rows(ws, store)
        periods = [r[0] for r in ws.rows]
        assert periods.count("本期") == 3  # 2 明细 + 1 总额
        assert periods.count("上期") == 2  # 1 明细 + 1 总额
        # 本期第一行占比 = 1000/4000 = 0.25。
        first = ws.rows[0]
        assert first[2] == "客户甲" and first[3] == 1000 and abs(first[4] - 0.25) < 1e-9
        # 总额行：客户名称=销售总额、占比列留空。
        total_rows = [r for r in ws.rows if r[2] == "销售总额"]
        assert len(total_rows) == 2
        cur_total = next(r for r in total_rows if r[0] == "本期")
        assert cur_total[3] == 4000 and cur_total[4] == "" and cur_total[5] == 10


class TestParseAndAssemble:
    def test_parse_current_detail(self) -> None:
        d = M._parse_d4_9_row(_row(期间="本期", 序号=1, 客户名称="客户甲", 销售金额=1000, 销售数量=5, 上期排名="2"), D4_9_HEADERS)
        assert d["_period"] == "current" and d["_isTotal"] is False
        assert d["name"] == "客户甲" and d["amount"] == 1000 and d["quantity"] == 5 and d["priorRank"] == "2"

    def test_parse_prior_detail(self) -> None:
        d = M._parse_d4_9_row(_row(期间="上期", 客户名称="客户丙", 销售金额=500, 销售数量=3), D4_9_HEADERS)
        assert d["_period"] == "prior"

    def test_parse_total_row(self) -> None:
        d = M._parse_d4_9_row(_row(期间="本期", 客户名称="销售总额", 销售金额=4000, 销售数量=10), D4_9_HEADERS)
        assert d["_isTotal"] is True and d["totalAmount"] == 4000 and d["totalQuantity"] == 10

    def test_ratio_columns_ignored(self) -> None:
        # 占比列有值也不进解析结果（派生列不回导）。
        d = M._parse_d4_9_row(_row(期间="本期", 客户名称="甲", 销售金额=1, 销售数量=1, 销售金额占比=0.9, 销售数量占比=0.9), D4_9_HEADERS)
        assert "amountRatio" not in d and "quantityRatio" not in d

    def test_empty_row_skipped(self) -> None:
        assert M._parse_d4_9_row(_row(期间="本期", 客户名称="", 销售金额=0, 销售数量=0), D4_9_HEADERS) is None

    def test_assemble_nested_with_rowid(self) -> None:
        flat = [
            {"_period": "current", "_isTotal": False, "name": "甲", "amount": 1000, "quantity": 5, "priorRank": "2"},
            {"_period": "current", "_isTotal": True, "totalAmount": 1000, "totalQuantity": 5},
            {"_period": "prior", "_isTotal": False, "name": "丙", "amount": 500, "quantity": 3, "priorRank": ""},
            {"_period": "prior", "_isTotal": True, "totalAmount": 500, "totalQuantity": 3},
        ]
        payload = M._assemble_d4_9_payload(flat)
        assert payload["current"]["totalAmount"] == 1000
        assert payload["prior"]["totalQuantity"] == 3
        assert len(payload["current"]["rows"]) == 1 and len(payload["prior"]["rows"]) == 1
        # 每明细行补了 rowId。
        assert payload["current"]["rows"][0]["rowId"]
        assert payload["current"]["rows"][0]["name"] == "甲"
        # 两行 rowId 不同。
        assert payload["current"]["rows"][0]["rowId"] != payload["prior"]["rows"][0]["rowId"]


class TestRoundtrip:
    def test_export_then_import_preserves_business_values(self) -> None:
        store = {
            "current": {
                "rows": [{"rowId": "c1", "name": "客户甲", "amount": 1000, "quantity": 5, "priorRank": "2"}],
                "totalAmount": 1000, "totalQuantity": 5,
            },
            "prior": {
                "rows": [{"rowId": "p1", "name": "客户丙", "amount": 500, "quantity": 3, "priorRank": "1"}],
                "totalAmount": 500, "totalQuantity": 3,
            },
        }
        ws = _FakeWs()
        M._export_d4_9_rows(ws, store)
        # 把导出的行当作导入源（跳过总额行的占比空值即可）。
        parsed = [M._parse_d4_9_row(tuple(r), D4_9_HEADERS) for r in ws.rows]
        parsed = [p for p in parsed if p is not None]
        payload = M._assemble_d4_9_payload(parsed)
        assert payload["current"]["rows"][0]["name"] == "客户甲"
        assert payload["current"]["rows"][0]["amount"] == 1000
        assert payload["current"]["totalAmount"] == 1000
        assert payload["prior"]["rows"][0]["name"] == "客户丙"
        assert payload["prior"]["totalQuantity"] == 3
