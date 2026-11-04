"""spec citar-case-chain-fetch-fixes 导入层：确认映射生效、表头误配、SAP 导出、余额符号、期间写法。"""

from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.services.ledger_import.converter import (
    _resolve_direction,
    convert_balance_rows,
    convert_ledger_rows,
    parse_period_str,
)
from app.services.ledger_import.identifier import _detect_by_headers, _match_header
from app.services.ledger_import.sheet_mapping import find_confirmed, resolve_sheet_mapping


# ── R2：中文 4 字表头差 2 个字不算同一列 ──
@pytest.mark.parametrize("header", ["过账代码", "原因代码", "凭证名称", "业务范围", "过账期间"])
def test_short_headers_two_chars_apart_do_not_match(header):
    assert _match_header(header)[0] is None


@pytest.mark.parametrize("header, field", [
    ("累计余额", "closing_balance"),  # 原编辑距离 2 命中「期初余额」
    ("凭证种类", "voucher_type"),  # 原命中「凭证日期」
    ("业务说明", "summary"),
    ("记账时间", "voucher_date"),
    ("借贷方向", "direction"),
    ("对方科目名称", "counterpart_account"),
    ("科目级次", "level"),  # 差 1 个字仍按编辑距离命中「科目级别」
])
def test_headers_resolve_to_intended_field(header, field):
    assert _match_header(header)[0] == field


# ── R3：SAP 导出 ──
SAP_BALANCE = ["公司代码", "总账科目", "短文本", "货币", "业务范围", "已结转余额", "Bal.p.per.",
               "在制表期间的借方余额", "报表期间的贷方余额", "累计余额"]
SAP_LEDGER = ["总账科目", "利润中心：长文本", "总账科目：长文本", "凭证编号", "凭证抬头文本", "凭证日期", "会计年度/期间",
              "成本中心", "科目表", "客户", "文本", "借/贷标识", "公司代码货币价值", "公司代码货币代码", "成本中心：长文本",
              "公司代码", "过账代码", "过账日期", "凭证名称", "职能范围", "原因代码", "对账科目：长文本", "过账期间", "公司代码"]


def _fields(headers):
    tt, _conf, matches, _ev = _detect_by_headers(headers)
    return tt, {m.column_header: m.standard_field for m in matches if m.standard_field}


def test_sap_balance_export_is_recognized():
    tt, f = _fields(SAP_BALANCE)
    assert tt == "balance"
    assert f["总账科目"] == "account_code" and f["短文本"] == "account_name"
    assert f["已结转余额"] == "opening_balance" and f["累计余额"] == "closing_balance"
    assert f["在制表期间的借方余额"] == "debit_amount" and f["报表期间的贷方余额"] == "credit_amount"
    assert "业务范围" not in f


def test_sap_ledger_export_is_recognized():
    tt, f = _fields(SAP_LEDGER)
    assert tt == "ledger"
    assert f["总账科目"] == "account_code" and f["总账科目：长文本"] == "account_name"
    assert f["公司代码货币价值"] == "amount" and f["借/贷标识"] == "direction"
    assert f["会计年度/期间"] == "accounting_period"
    for wrong in ("过账代码", "原因代码", "凭证名称", "对账科目：长文本"):
        assert wrong not in f, wrong


def test_single_amount_column_split_by_direction_and_sign():
    base = {"voucher_date": "2025-01-02", "voucher_no": "1"}
    rows = [
        {**base, "account_code": "1002", "amount": "100", "direction": "S"},
        {**base, "account_code": "6001", "amount": "-100", "direction": "H"},  # SAP 借正贷负
        {**base, "account_code": "6001", "amount": "30", "direction": "H"},  # 贷方红字（负记账）
        {**base, "account_code": "2221", "amount": "-50", "direction": "H"},
        {**base, "account_code": "1002", "amount": "-5"},  # 无方向列：负数记贷方
    ]
    led, _, _ = convert_ledger_rows(rows)
    got = [(r["account_code"], r["debit_amount"], r["credit_amount"]) for r in led]
    assert got == [("1002", D(100), None), ("6001", None, D(100)), ("6001", None, D(-30)),
                   ("2221", None, D(50)), ("1002", None, D(5))]


def test_unsigned_amount_with_credit_direction_kept_as_is():
    base = {"voucher_date": "2025-01-02", "voucher_no": "1"}
    rows = [{**base, "account_code": "6001", "amount": "80", "direction": "贷"},
            {**base, "account_code": "1002", "amount": "80", "direction": "借"}]
    led, _, _ = convert_ledger_rows(rows)
    assert [(r["debit_amount"], r["credit_amount"]) for r in led] == [(None, D(80)), (D(80), None)]


@pytest.mark.parametrize("raw, month", [
    ("2025.011", 11), ("2025.012", 12), ("2025.013", 12), ("2025.016", 12), ("202511", 11),
    ("2025-03", 3), ("11月", 11), ("2025年3期", 3), ("7", 7), (11, 11), ("abc", None),
])
def test_period_formats(raw, month):
    assert parse_period_str(raw) == month


def test_counterpart_account_passes_through():
    rows = [{"voucher_date": "2025-01-02", "voucher_no": "1", "account_code": "1002",
             "debit_amount": "1", "counterpart_account": "主营业务收入"}]
    assert convert_ledger_rows(rows)[0][0]["counterpart_account"] == "主营业务收入"


# ── R4：「借贷方向」是科目方向，金额相对它带符号 ──
def test_direction_keeps_amount_sign():
    assert _resolve_direction("贷", D("-8690")) == D("8690")  # 贷方科目借方余额
    assert _resolve_direction("贷", D("100")) == D("-100")
    assert _resolve_direction("借", D("-5")) == D("-5")


def test_credit_account_with_debit_balance_reads_as_debit():
    rows = [{"account_code": "3141", "account_name": "利润分配", "direction": "贷",
             "opening_balance": "-9016882.51", "closing_balance": "-5010411.91"}]
    bal, _ = convert_balance_rows(rows)
    r = bal[0]
    assert r["closing_direction"] == "debit" and abs(r["closing_balance"]) == D("5010411.91")


# ── R1：确认映射 ──
def _sheet(headers, mappings, table_type="ledger", sheet_name="Sheet1"):
    cms = [SimpleNamespace(column_index=i, column_header=h, standard_field=f, confidence=90)
           for i, (h, f) in enumerate(zip(headers, mappings))]
    return SimpleNamespace(sheet_name=sheet_name, table_type=table_type, column_mappings=cms,
                           detection_evidence={"header_cells": headers}, preview_rows=[])


def test_confirmed_mapping_entries_override_auto_and_match_stored_name():
    headers = ["公司代码", "过账代码", "总账科目", "公司代码"]
    sheet = _sheet(headers, ["company_code", "account_code", None, "company_code"])
    confirmed = [{"file_name": "01_序时账.xlsx", "sheet_name": "Sheet1", "table_type": "ledger",
                  "mapping_entries": [{"column_index": 2, "original_header": "总账科目",
                                       "canonical_header": "总账科目", "standard_field": "account_code"}]}]
    plan = resolve_sheet_mapping(sheet, "序时账.xlsx", confirmed)  # pipeline 用的是去掉存储前缀的原名
    assert plan.source == "confirmed"
    assert plan.col_mapping == {"总账科目": "account_code"}
    assert plan.ff_cols == [2]
    # 重复表头去重后不再互相覆盖
    assert plan.headers == ["公司代码#0", "过账代码", "总账科目", "公司代码#3"]


def test_confirmed_table_type_wins_and_auto_used_when_absent():
    sheet = _sheet(["科目编码", "期末余额"], ["account_code", "closing_balance"], table_type="unknown")
    plan = resolve_sheet_mapping(sheet, "a.xlsx", [{"file_name": "a.xlsx", "sheet_name": "Sheet1",
                                                    "table_type": "balance", "mapping_entries": [
                                                        {"column_index": 0, "standard_field": "account_code"},
                                                        {"column_index": 1, "standard_field": "closing_balance"}]}])
    assert plan.table_type == "balance"
    auto = resolve_sheet_mapping(sheet, "a.xlsx", [])
    assert auto.source == "auto" and auto.col_mapping == {"科目编码": "account_code", "期末余额": "closing_balance"}


def test_find_confirmed_ambiguous_sheet_name_returns_none():
    items = [{"file_name": "00_a.xlsx", "sheet_name": "Sheet1"}, {"file_name": "01_b.xlsx", "sheet_name": "Sheet1"}]
    assert find_confirmed("c.xlsx", "Sheet1", items) is None
    assert find_confirmed("b.xlsx", "Sheet1", items) is items[1]


# ── 合并单元格向下填充：合计行不填 ──
def _plan(headers, mapping, ff):
    from app.services.ledger_import.sheet_mapping import SheetPlan
    return SheetPlan("balance", headers, mapping, ff)


def test_forward_fill_skips_total_rows_but_fills_detail_rows():
    from app.services.ledger_import.sheet_mapping import ForwardFill
    headers = ["科目编码", "科目名称", "核算项目", "期末余额"]
    filler = ForwardFill(_plan(headers, {"科目编码": "account_code", "科目名称": "account_name",
                                         "核算项目": "aux_dimensions", "期末余额": "closing_balance"}, [0, 1]))
    rows = [
        {"科目编码": "1122", "科目名称": "应收账款", "核算项目": "客户:A", "期末余额": 10},
        {"科目编码": None, "科目名称": None, "核算项目": "客户:B", "期末余额": 20},  # 合并单元格 → 填
        {"科目编码": None, "科目名称": "", "核算项目": None, "期末余额": 30},  # 合计行 → 不填
    ]
    filler.apply(rows[:2])
    filler.apply(rows[2:])  # 跨 chunk
    assert rows[1]["科目编码"] == "1122" and rows[1]["科目名称"] == "应收账款"
    assert rows[2]["科目编码"] is None
