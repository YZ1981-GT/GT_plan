# -*- coding: utf-8 -*-
"""D7-7 期后结转 / D6-5 关联方表导入导出跟模板走（spec oo-writeback-template-parity-closure R3 批 B2a）。

- D7-7 区②（期后结转检查）模板 G34 是「借方金额」（合同负债期后结转是借方），前端随本批由 creditAmount 改存
  debitAmount：导出写「借方金额」（没重新保存过的旧行只有 creditAmount，照样导出）；导入读「借方金额」，
  旧版导出文件只有「贷方金额」时按它读（不能把旧文件拒掉）。
- D6-5 模板 J 列「发生原因（款项性质）」前端补了 transactionReason：导出写出、导入读回；旧文件缺该列照常导入。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.routers.wp_render_strategies import _d6_import_export as d6  # noqa: E402
from app.routers.wp_render_strategies import _d7_import_export as d7  # noqa: E402

_POST = "D7-7-post"
_ROW = {
    "customerName": "甲公司", "date": "2026-01-15", "voucherNo": "记-12", "businessContent": "结转收入",
    "counterAccount": "主营业务收入", "counterDetail": "产品A", "supportDocs": "验收单",
    "checkItems": [True, False, True, False, False], "indexRef": "D7-2", "isAbnormal": False, "remark": "已核",
}


def test_post_zone_amount_column_is_debit() -> None:
    headers = d7._get_headers(_POST)
    assert "借方金额" in headers and "贷方金额" not in headers
    assert headers.index("借方金额") == headers.index("对方明细") + 1
    assert "借方金额" not in d7._required_import_headers(_POST)  # 旧文件只有「贷方金额」


def test_post_zone_round_trips_debit_amount() -> None:
    headers = d7._get_headers(_POST)
    exported = d7._export_row(_POST, {**_ROW, "debitAmount": 300.0}, headers)
    assert len(exported) == len(headers)
    assert exported[headers.index("借方金额")] == 300.0
    parsed = d7._parse_row(_POST, tuple(exported), headers)
    assert parsed["debitAmount"] == 300.0
    assert "creditAmount" not in parsed
    assert parsed["checkItems"] == [True, False, True, False, False]


def test_post_zone_legacy_row_and_legacy_file() -> None:
    headers = d7._get_headers(_POST)
    legacy = d7._export_row(_POST, {**_ROW, "creditAmount": 200.0}, headers)  # 没重新保存过的旧行
    assert legacy[headers.index("借方金额")] == 200.0
    old_headers = [("贷方金额" if h == "借方金额" else h) for h in headers]  # 旧版导出文件
    parsed = d7._parse_row(_POST, tuple(legacy), old_headers)
    assert parsed["debitAmount"] == 200.0


def test_period_zone_keeps_both_amounts() -> None:
    headers = d7._get_headers("D7-7-period")
    row = {**_ROW, "debitAmount": 5.0, "creditAmount": 7.0}
    parsed = d7._parse_row("D7-7-period", tuple(d7._export_row("D7-7-period", row, headers)), headers)
    assert (parsed["debitAmount"], parsed["creditAmount"]) == (5.0, 7.0)


def test_d6_5_transaction_reason_round_trips_and_is_optional() -> None:
    headers = d6._get_headers("D6-5")
    col = "发生原因（款项性质）"
    assert headers.index(col) == headers.index("发生时间及账龄") + 1
    assert col in d6._OPTIONAL_IMPORT_HEADERS["D6-5"]
    data = {"partyName": "乙公司", "priorBalance": 100.0, "debitAmount": 20.0, "creditAmount": 5.0,
            "impairment": 1.0, "agingAndTiming": "1年以内", "transactionReason": "货款", "indexRef": "D6-2"}
    exported = d6._export_row("D6-5", data, headers)
    assert len(exported) == len(headers)
    parsed = d6._parse_row("D6-5", tuple(exported), headers)
    assert parsed["transactionReason"] == "货款"
    assert parsed["endBalance"] == 115.0 and parsed["bookValue"] == 114.0
    old_headers = [h for h in headers if h != col]
    old_row = tuple(v for h, v in zip(headers, exported) if h != col)
    assert d6._parse_row("D6-5", old_row, old_headers)["transactionReason"] == ""
