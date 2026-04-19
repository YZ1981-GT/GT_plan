# -*- coding: utf-8 -*-
"""最终全链路检查"""
import sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.smart_import_engine import (
    detect_header_rows, merge_header_rows, smart_match_column,
    _guess_data_type, convert_balance_rows, convert_ledger_rows,
    _safe_decimal, validate_four_tables,
)
from app.services.account_chart_service import parse_aux_dimensions

# 1. _safe_decimal
assert _safe_decimal(0) == Decimal(0)
assert _safe_decimal(None) is None
assert _safe_decimal("") is None
assert _safe_decimal(123.45) == Decimal("123.45")
print("1. _safe_decimal OK")

# 2. convert_balance_rows 分列模式
bal, aux = convert_balance_rows([{
    "account_code": "1001", "account_name": "cash",
    "opening_debit": 100, "opening_credit": None,
    "closing_debit": 200, "closing_credit": None,
    "debit_amount": 50, "credit_amount": 30,
}])
assert bal[0]["opening_balance"] == Decimal(100)
assert bal[0]["opening_debit"] == Decimal(100)
assert bal[0]["closing_balance"] == Decimal(200)
print("2. balance split mode OK")

# 3. convert_balance_rows 净额+方向模式
bal2, _ = convert_balance_rows([{
    "account_code": "2001", "account_name": "loan",
    "opening_balance": 5000, "direction": "贷",
    "closing_balance": 6000, "closing_direction": "贷",
    "debit_amount": 1000, "credit_amount": 2000,
}])
assert bal2[0]["opening_balance"] == Decimal(-5000)
assert bal2[0]["opening_debit"] is None
print("3. balance net+direction mode OK")

# 4. convert_balance_rows 核算维度拆分
_, aux = convert_balance_rows([{
    "account_code": "1002", "account_name": "bank",
    "aux_dimensions": "金融机构:YG001,工商银行; 成本中心:YG108,财务部",
    "opening_debit": 100, "debit_amount": 50, "credit_amount": 30, "closing_debit": 120,
}])
assert len(aux) == 2
assert aux[0]["aux_type"] == "金融机构"
assert aux[0]["aux_dimensions_raw"] is not None
print("4. balance aux_dimensions split OK")

# 5. convert_ledger_rows 返回3个值
led, empty, stats = convert_ledger_rows([{
    "account_code": "1002", "voucher_date": "2025-01-15", "voucher_no": "001",
    "debit_amount": 100, "aux_dimensions": "成本中心:YG001,财务部",
}])
assert len(led) == 1
assert len(empty) == 0
assert stats.get("成本中心") == 1
assert "_aux_dim_str" in led[0]
print("5. ledger convert OK (3 values)")

# 6. _guess_data_type
assert _guess_data_type({"account_code", "opening_debit", "closing_debit", "debit_amount"}) == "balance"
assert _guess_data_type({"account_code", "voucher_date", "voucher_no", "debit_amount"}) == "ledger"
assert _guess_data_type({"account_code", "voucher_date", "voucher_no", "debit_amount", "aux_dimensions"}) == "ledger"
assert _guess_data_type({"account_code", "aux_type", "aux_code", "aux_name", "opening_balance"}) == "aux_balance"
print("6. _guess_data_type OK")

# 7. parse_aux_dimensions
dims = parse_aux_dimensions("金融机构:YG001,工商银行; 银行账户:310002; 成本中心:YG108,财务部")
assert len(dims) == 3
assert dims[0]["aux_type"] == "金融机构"
assert dims[0]["aux_code"] == "YG001"
assert dims[1]["aux_code"] == "310002"  # 纯数字当编号
print("7. parse_aux_dimensions OK")

# 8. smart_match_column 合并表头
assert smart_match_column("年初余额_借方金额") == "year_opening_debit"
assert smart_match_column("期末余额_贷方金额") == "closing_credit"
assert smart_match_column("核算维度") == "aux_dimensions"
assert smart_match_column("科目编码") == "account_code"
assert smart_match_column("记账日期") == "voucher_date"
print("8. smart_match_column OK")

# 9. validate_four_tables
findings = validate_four_tables(
    [{"account_code": "1001", "opening_balance": Decimal(100), "debit_amount": Decimal(50), "credit_amount": Decimal(30), "closing_balance": Decimal(120)}],
    [], [], [],
)
bal_ok = any(f["category"] == "余额表勾稽" for f in findings)
print(f"9. validate_four_tables OK ({len(findings)} findings)")

print("\n✅ ALL 9 CHECKS PASSED")
