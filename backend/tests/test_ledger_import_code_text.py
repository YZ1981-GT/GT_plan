"""编码类单元格转文本：Excel 数字编码读成 float 时不能带「.0」。

真库两个项目的科目编码全是 ``510101.0`` / ``5101.0``：叶子判定（``LIKE code || '.%'``）
与父级补齐都认不出上下级 ⇒ 父子重复汇总（其他业务成本 1,987.47 显示 3,974.94），凭证号 ``1.0``。
"""

from decimal import Decimal

import pytest

from app.services.ledger_import.converter import convert_balance_rows, convert_ledger_rows
from app.core.code_text import code_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1001.0, "1001"),
        (510101.0, "510101"),
        (Decimal("2202"), "2202"),
        (1, "1"),
        ("1002.01", "1002.01"),   # 点号分级的文本编码原样保留
        ("001", "001"),           # 前导零的文本编码原样保留
        (" 1231-01 ", "1231-01"),
        (1002.5, "1002.5"),       # 非整数不硬截（真有小数就别吞掉）
        (None, ""),
        ("", ""),
    ],
)
def test_code_text(raw, expected):
    assert code_text(raw) == expected


def test_balance_rows_keep_integer_codes():
    rows, _aux = convert_balance_rows([
        {"account_code": 5101.0, "account_name": "主营业务收入", "debit_amount": 0, "credit_amount": 100,
         "closing_balance": -100, "company_code": 1.0},
        {"account_code": 510101.0, "account_name": "主营业务收入_药品", "debit_amount": 0, "credit_amount": 100,
         "closing_balance": -100, "company_code": 1.0},
    ])
    assert [r["account_code"] for r in rows] == ["5101", "510101"]
    assert {r["company_code"] for r in rows} == {"1"}


def test_ledger_rows_keep_integer_voucher_no():
    rows, _aux, _stats = convert_ledger_rows([
        {"account_code": 1002.0, "account_name": "银行存款", "voucher_date": "2025-01-01", "voucher_no": 1.0,
         "debit_amount": 10, "credit_amount": 0},
    ])
    assert rows[0]["account_code"] == "1002"
    assert rows[0]["voucher_no"] == "1"
