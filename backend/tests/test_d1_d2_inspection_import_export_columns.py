# -*- coding: utf-8 -*-
"""D2-6 / D2-11 / D2-12 / D2-13 与 D1-8T 导入导出带上表单按模板补的列（spec oo-writeback-template-parity-closure R3 批 B2b）。

- D2 四张表：新列进 SHEET_COLUMNS，导出逐列对得上、导入读回；导入只拒未知列 ⇒ 旧文件缺新列照常导入。
  D2-11「原累计已计提」原导出恒空、导入不读，现接 cumulativeProvision。
- D1-8T 背书表原与 D1-8 贴现表共用 16 列（F/K/L/M 是 已计利息 / 贴现银行 / 贴现金额 / 贴现息），现按模板（二）
  前手 / 背书转让单位 / 背书转让日期 / 说明；旧文件（贴现表列）照常导入，旧列读进原键不丢。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import pytest  # noqa: E402

from app.routers.wp_render_strategies import _d2_import_export as d2  # noqa: E402
from app.routers.wp_render_strategies._d1_import_export import _impl as d1  # noqa: E402

_SAMPLES = {
    "D2-6": {"debtorName": "甲公司", "relationType": "子公司", "priorBalance": 100.0, "debitAmount": 30.0,
             "creditAmount": 10.0, "endBalance": 120.0, "badDebtProvision": 2.0, "bookValue": 118.0,
             "transactionType": "销售商品", "isArmsLength": "是", "agingPeriod": "1年以内",
             "postPayment": 50.0, "indexRef": "D2-2", "remark": "备"},
    "D2-11": {"_exportSection": "转回", "debtorName": "乙公司", "reason": "收回", "approvalDoc": "审批单",
              "amount": 8.0, "cumulativeProvision": 9.0, "recoveryMethod": "银行转账", "originalBasis": "单项计提",
              "receivableType": "", "isRelatedParty": "", "isReasonable": "合理", "auditorComment": "已核",
              "indexRef": "D2-3"},
    "D2-12": {"_exportType": "质押", "debtorName": "丙公司", "endBalance": 500.0, "pledgeAmount": 300.0,
              "pledgee": "某银行", "pledgePurpose": "借款担保", "pledgeDate": "2025-03-01",
              "expiryDate": "2026-03-01", "pledgeCondition": "到期还款", "pledgeAgreement": "质押合同-01",
              "remark": "", "indexRef": "L1-2"},
    "D2-13": {"_exportType": "group", "rowId": "bm-1", "groupName": "信用等级高", "bizModel": "收取并出售",
              "basis": "频繁出售", "indexRef": "D2-13-1", "sppiResult": "通过", "measurementBasis": "FVOCI",
              "remark": ""},
}


@pytest.mark.parametrize("sheet", sorted(_SAMPLES))
def test_export_values_line_up_with_columns(sheet: str) -> None:
    values = d2._export_row_values(sheet, _SAMPLES[sheet])
    assert len(values) == len(d2.SHEET_COLUMNS[sheet]), sheet


def _exported(sheet: str) -> dict:
    return dict(zip(d2.SHEET_COLUMNS[sheet], d2._export_row_values(sheet, _SAMPLES[sheet])))


def test_d2_6_new_columns_round_trip() -> None:
    row = d2._parse_d2_6_rows([_exported("D2-6")])[0]
    assert (row["agingPeriod"], row["postPayment"], row["indexRef"]) == ("1年以内", 50.0, "D2-2")
    assert row["transactionType"] == "销售商品" and row["remark"] == "备"
    legacy = {k: v for k, v in _exported("D2-6").items() if k not in ("发生时间及账龄", "期后回款", "索引号")}
    old = d2._parse_d2_6_rows([legacy])[0]
    assert (old["agingPeriod"], old["postPayment"], old["indexRef"]) == ("", 0.0, "")


def test_d2_11_reversal_columns_round_trip() -> None:
    rows = d2._parse_d2_11_by_section([_exported("D2-11")])[d2.D2_11_ITEM_IDS["reversal"]]
    assert rows[0]["cumulativeProvision"] == 9.0  # 原导出恒空、导入不读
    assert (rows[0]["recoveryMethod"], rows[0]["originalBasis"]) == ("银行转账", "单项计提")
    assert rows[0]["auditorComment"] == "已核"


def test_d2_11_writeoff_columns_round_trip() -> None:
    sample = {**_SAMPLES["D2-11"], "_exportSection": "核销", "receivableType": "货款", "isRelatedParty": "否"}
    exported = dict(zip(d2.SHEET_COLUMNS["D2-11"], d2._export_row_values("D2-11", sample)))
    rows = d2._parse_d2_11_by_section([exported])[d2.D2_11_ITEM_IDS["writeoff"]]
    assert (rows[0]["receivableType"], rows[0]["isRelatedParty"]) == ("货款", "否")


def test_d2_12_pledge_columns_round_trip_and_factoring_stays_blank() -> None:
    rows = d2._parse_d2_12_by_type([_exported("D2-12")])
    pledge = rows[d2.D2_12_ITEM_IDS["pledge"]][0]
    assert (pledge["endBalance"], pledge["pledgeAmount"]) == (500.0, 300.0)
    assert (pledge["pledgeCondition"], pledge["pledgeAgreement"]) == ("到期还款", "质押合同-01")
    factoring = dict(zip(d2.SHEET_COLUMNS["D2-12"], d2._export_row_values(
        "D2-12", {"_exportType": "保理", "debtorName": "丁公司", "factoringAmount": 7.0, "factor": "保理商"})))
    assert (factoring["期末余额"], factoring["质押条件"], factoring["质押协议"]) == ("", "", "")
    assert factoring["金额"] == 7.0


def test_d2_13_group_columns_round_trip() -> None:
    groups = d2._parse_d2_13_rows([_exported("D2-13")])[d2.D2_13_ITEM_IDS["groups"]]
    assert (groups[0]["basis"], groups[0]["indexRef"]) == ("频繁出售", "D2-13-1")


@pytest.mark.parametrize("sheet", ["D2-11", "D2-12", "D2-13"])
def test_template_passes_own_import_validation(sheet: str) -> None:
    import io

    import openpyxl

    buf = io.BytesIO()
    d2._create_template_workbook(sheet).save(buf)
    buf.seek(0)
    ws = d2._select_data_ws(openpyxl.load_workbook(buf, data_only=True), sheet)
    assert d2._validate_columns(ws, sheet) == []


# ═══ D1-8T ═══

_ENDORSE = {
    "noteType": "银行承兑汇票", "receivedDate": "2025-10-01", "issuer": "甲", "noteNumber": "N-1",
    "billAmount": 1000.0, "endorser": "乙公司", "issueDate": "2025-09-01", "maturityDate": "2026-03-01",
    "acceptorBank": "某银行", "creditRating": "AAA", "endorsedTo": "丙公司", "endorsedDate": "2025-12-01",
    "description": "支付货款", "isDerecognized": "是", "isCorrect": "是", "indexRef": "D1-7",
}


def test_d1_8t_headers_follow_template_and_differ_from_discount() -> None:
    headers = d1._SHEET_HEADERS["D1-8T"]
    assert [headers[i] for i in (5, 10, 11, 12)] == ["前手", "背书转让单位", "背书转让日期", "说明"]
    assert [d1._SHEET_HEADERS["D1-8"][i] for i in (5, 10, 11, 12)] == ["已计利息", "贴现银行", "贴现金额", "贴现息"]


def test_d1_8t_round_trip() -> None:
    headers = d1._SHEET_HEADERS["D1-8T"]
    exported = d1.export_d1_8t_row(_ENDORSE)
    assert len(exported) == len(headers)
    parsed = d1.parse_d1_8t_row(tuple(exported), headers)
    assert {k: parsed[k] for k in _ENDORSE} == _ENDORSE
    assert d1._validate_columns_against(headers, "D1-8T") == []


def test_d1_8t_legacy_file_still_imports_and_keeps_old_columns() -> None:
    legacy_headers = d1._SHEET_HEADERS["D1-8"]  # 旧 D1-8T 导出文件 = 贴现表列
    assert d1._validate_columns_against(legacy_headers, "D1-8T") == []
    row = ["银行承兑汇票", "", "甲", "N-2", 200.0, 3.0, "", "", "", "", "某行", 150.0, 1.5, "否", "是", "D1-7"]
    parsed = d1.parse_d1_8t_row(tuple(row), legacy_headers)
    assert (parsed["billAmount"], parsed["accruedInterest"], parsed["discountBank"]) == (200.0, 3.0, "某行")
    assert (parsed["discountAmount"], parsed["discountInterest"]) == (150.0, 1.5)
    assert (parsed["endorser"], parsed["endorsedTo"], parsed["endorsedDate"], parsed["description"]) == ("", "", "", "")


def test_d1_8_discount_unchanged() -> None:
    """贴现表（已开删物理行的那张）列与转换函数不动。"""
    assert d1._SHEET_HEADERS["D1-8"] is d1._D1_8_HEADERS
    assert d1._validate_columns_against(d1._SHEET_HEADERS["D1-8T"], "D1-8") != []
