# -*- coding: utf-8 -*-
"""D4-9 导入导出（本期/上期 + 总额 + 专用 parser）—— 行为级验证（judge-first）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 10
Requirements 6.1/6.2/6.3/6.4/6.5 · Property 8

判据：
1. 导出行：本期/上期两区数据行 + 各一条总额行，带 _period/_seq/_isTotal/_totalAmount。
2. _parse_d4_9_row：判本期/上期；普通行补 rowId + name/amount/quantity/priorRank；
   总额行返回 _isTotal + amount/quantity；占比列不解析。
3. 表头含期间标识 + 占比列 + 总额（覆盖 序号/客户名称/销售金额/销售金额占比/销售数量/
   销售数量占比/上期排名）。
"""
from __future__ import annotations

from app.routers.wp_render_strategies import _d4_import_export as m


def test_headers_cover_period_ratio_and_columns() -> None:
    headers = m._SHEET_HEADERS["D4-9"]
    for col in ("期间", "序号", "客户名称", "销售金额", "销售金额占比", "销售数量", "销售数量占比", "上期排名"):
        assert col in headers, f"D4-9 表头缺列 {col}"


def test_build_export_rows_two_regions_with_totals() -> None:
    parsed = {
        "current": {
            "rows": [
                {"rowId": "c1", "name": "客户A", "amount": 600, "quantity": 30, "priorRank": "1"},
                {"rowId": "c2", "name": "客户B", "amount": 400, "quantity": 20, "priorRank": "2"},
            ],
            "totalAmount": 1000, "totalQuantity": 50,
        },
        "prior": {
            "rows": [{"rowId": "p1", "name": "客户C", "amount": 500, "quantity": 25, "priorRank": "1"}],
            "totalAmount": 500, "totalQuantity": 25,
        },
    }
    rows = m._build_d4_9_export_rows(parsed)
    # 本期 2 数据 + 1 总额 + 上期 1 数据 + 1 总额 = 5
    assert len(rows) == 5
    cur = [r for r in rows if r["_period"] == "本期"]
    pri = [r for r in rows if r["_period"] == "上期"]
    assert len([r for r in cur if not r.get("_isTotal")]) == 2
    assert len([r for r in cur if r.get("_isTotal")]) == 1
    assert len([r for r in pri if not r.get("_isTotal")]) == 1
    # 数据行带总额供占比计算
    first = cur[0]
    assert first["_totalAmount"] == 1000
    assert first["_seq"] == 1


def test_parse_row_current_data_gets_rowid() -> None:
    headers = list(m._SHEET_HEADERS["D4-9"])
    # 期间/序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名
    row = ("本期", 1, "客户A", 600, 0.6, 30, 0.6, "2")
    parsed = m._parse_d4_9_row(row, headers)
    assert parsed["_period"] == "本期"
    assert parsed["name"] == "客户A"
    assert parsed["amount"] == 600
    assert parsed["quantity"] == 30
    assert parsed["priorRank"] == "2"
    assert parsed.get("rowId"), "普通行必须补 rowId"
    assert not parsed.get("_isTotal")
    # 占比列不进 store（不可回导）
    assert "amountRatio" not in parsed
    assert "quantityRatio" not in parsed


def test_parse_row_prior_period() -> None:
    headers = list(m._SHEET_HEADERS["D4-9"])
    row = ("上期", 1, "客户C", 500, 1.0, 25, 1.0, "1")
    parsed = m._parse_d4_9_row(row, headers)
    assert parsed["_period"] == "上期"
    assert parsed["name"] == "客户C"


def test_parse_total_row_detected() -> None:
    headers = list(m._SHEET_HEADERS["D4-9"])
    row = ("本期", "", "本期销售总额", 1000, "", 50, "", "")
    parsed = m._parse_d4_9_row(row, headers)
    assert parsed["_isTotal"] is True
    assert parsed["_period"] == "本期"
    assert parsed["amount"] == 1000
    assert parsed["quantity"] == 50
    assert "rowId" not in parsed


def test_export_then_parse_roundtrip_regions_and_totals() -> None:
    """导出 → 逐行 parse → 还原本期/上期数据行数与总额（离线 roundtrip）。"""
    parsed_store = {
        "current": {
            "rows": [{"rowId": "c1", "name": "A", "amount": 600, "quantity": 30, "priorRank": "1"}],
            "totalAmount": 1000, "totalQuantity": 50,
        },
        "prior": {
            "rows": [{"rowId": "p1", "name": "C", "amount": 500, "quantity": 25, "priorRank": "1"}],
            "totalAmount": 500, "totalQuantity": 25,
        },
    }
    headers = list(m._SHEET_HEADERS["D4-9"])
    export_rows = m._build_d4_9_export_rows(parsed_store)

    # 把导出行转成 xlsx tuple（按 header 顺序），再 parse 回来。
    def _to_tuple(r):
        if r.get("_isTotal"):
            name = "本期销售总额" if r["_period"] == "本期" else "上期销售总额"
            return (r["_period"], "", name, r["_totalAmount"], "", r["_totalQuantity"], "", "")
        ta, tq = r["_totalAmount"], r["_totalQuantity"]
        return (
            r["_period"], r["_seq"], r["name"], r["amount"],
            (r["amount"] / ta if ta else 0), r["quantity"],
            (r["quantity"] / tq if tq else 0), r.get("priorRank", ""),
        )

    reparsed = [m._parse_d4_9_row(_to_tuple(r), headers) for r in export_rows]
    cur_data = [r for r in reparsed if not r.get("_isTotal") and r["_period"] == "本期"]
    pri_data = [r for r in reparsed if not r.get("_isTotal") and r["_period"] == "上期"]
    cur_total = [r for r in reparsed if r.get("_isTotal") and r["_period"] == "本期"][0]
    assert len(cur_data) == 1 and cur_data[0]["name"] == "A" and cur_data[0]["amount"] == 600
    assert len(pri_data) == 1 and pri_data[0]["name"] == "C"
    assert cur_total["amount"] == 1000 and cur_total["quantity"] == 50
