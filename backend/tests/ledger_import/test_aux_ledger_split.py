"""验证 convert_ledger_rows 辅助明细账拆分（对齐旧引擎 write_four_tables 逻辑）。

关键场景：
- 序时账行含辅助维度 → 主表 + 辅助表都写
- 一行多维度（分号分隔）→ 一条主表 + 多条辅助表
- 空辅助维度 → 只写主表
- 单维度"类型:编码,名称"（YG36 真实格式）
"""
from __future__ import annotations

from datetime import date

from backend.app.services.ledger_import.converter import convert_ledger_rows


def _make_row(**extra) -> dict:
    base = {
        "account_code": "1001",
        "account_name": "库存现金",
        "voucher_date": date(2025, 1, 15),
        "voucher_no": "记-1",
        "debit_amount": "100.00",
        "credit_amount": "0",
    }
    base.update(extra)
    return base


def test_ledger_without_aux():
    rows = [_make_row()]
    ledger, aux_ledger, stats = convert_ledger_rows(rows)
    assert len(ledger) == 1
    assert len(aux_ledger) == 0
    assert stats == {}


def test_ledger_with_single_aux_code_name():
    """YG36 真实格式: 金融机构:YG0001,工商银行"""
    rows = [_make_row(aux_dimensions="金融机构:YG0001,工商银行")]
    ledger, aux_ledger, stats = convert_ledger_rows(rows)
    assert len(ledger) == 1
    assert len(aux_ledger) == 1
    assert aux_ledger[0]["aux_type"] == "金融机构"
    assert aux_ledger[0]["aux_code"] == "YG0001"
    assert aux_ledger[0]["aux_name"] == "工商银行"
    assert aux_ledger[0]["aux_dimensions_raw"] == "金融机构:YG0001,工商银行"
    # 辅助表保留主表字段
    assert aux_ledger[0]["account_code"] == "1001"
    assert aux_ledger[0]["voucher_date"] == date(2025, 1, 15)
    assert stats == {"金融机构": 1}


def test_ledger_with_multi_aux():
    """多维度分号分隔: 客户:001 北京A；项目:P01 新产品"""
    rows = [_make_row(aux_dimensions="客户:001 北京A；项目:P01 新产品")]
    ledger, aux_ledger, stats = convert_ledger_rows(rows)
    assert len(ledger) == 1
    assert len(aux_ledger) == 2
    assert {r["aux_type"] for r in aux_ledger} == {"客户", "项目"}
    assert stats == {"客户": 1, "项目": 1}


def test_ledger_with_multi_aux_comma():
    """多维度逗号分隔（逗号后接类型:）:
    客户:001 北京A,项目:P01 新产品 → 2 维度
    """
    rows = [_make_row(aux_dimensions="客户:001 北京A,项目:P01 新产品")]
    ledger, aux_ledger, stats = convert_ledger_rows(rows)
    assert len(ledger) == 1
    assert len(aux_ledger) == 2


def test_ledger_accounting_period_from_date():
    """accounting_period 缺失时从 voucher_date 推断月份"""
    rows = [_make_row(voucher_date=date(2025, 6, 20))]
    ledger, _, _ = convert_ledger_rows(rows)
    assert ledger[0]["accounting_period"] == 6


def test_multi_rows_mixed():
    """多行：有辅助 / 无辅助 混合"""
    rows = [
        _make_row(aux_dimensions="客户:C001 A客户"),
        _make_row(),
        _make_row(aux_dimensions="供应商:V001 B供应商"),
    ]
    ledger, aux_ledger, stats = convert_ledger_rows(rows)
    assert len(ledger) == 3
    assert len(aux_ledger) == 2
    assert stats == {"客户": 1, "供应商": 1}
