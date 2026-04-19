# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.smart_import_engine import smart_parse_files

base = Path(__file__).resolve().parent.parent.parent / "数据"
with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    files = [("余额表.xlsx", f.read())]
result = smart_parse_files(files)

print("=== 余额表前3条 ===")
for r in result["balance_rows"][:3]:
    print(f"  {r['account_code']} {r['account_name']}:")
    print(f"    opening: debit={r.get('opening_debit')} credit={r.get('opening_credit')} balance={r.get('opening_balance')}")
    print(f"    closing: debit={r.get('closing_debit')} credit={r.get('closing_credit')} balance={r.get('closing_balance')}")

print("\n=== 辅助余额表前2条 ===")
for r in result["aux_balance_rows"][:2]:
    print(f"  {r['account_code']}/{r.get('aux_type')}:{r.get('aux_code')}:")
    print(f"    opening: debit={r.get('opening_debit')} credit={r.get('opening_credit')} balance={r.get('opening_balance')}")
    print(f"    closing: debit={r.get('closing_debit')} credit={r.get('closing_credit')} balance={r.get('closing_balance')}")
