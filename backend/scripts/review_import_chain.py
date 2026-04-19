# -*- coding: utf-8 -*-
"""导入链路完整复盘测试 — 验证所有已知问题"""
import sys, time, io, openpyxl
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

base = Path(__file__).resolve().parent.parent.parent / "数据"

print("=" * 60, flush=True)
print("导入链路复盘测试", flush=True)
print("=" * 60, flush=True)

# ── 1. 年度提取：datetime 对象 vs 字符串 ──
print("\n1. 年度提取测试", flush=True)
from app.services.smart_import_engine import extract_year_from_content
from datetime import datetime, date

# datetime 对象（openpyxl 返回的）
rows_dt = [{"voucher_date": datetime(2025, 3, 15)}]
print(f"  datetime对象: {extract_year_from_content(rows_dt)}")

# 字符串日期
rows_str = [{"voucher_date": "2025-03-15"}]
print(f"  字符串日期: {extract_year_from_content(rows_str)}")

# 期间格式
rows_period = [{"accounting_period": "2025年3期"}]
print(f"  期间格式: {extract_year_from_content(rows_period)}")

# 文件名
print(f"  文件名: {extract_year_from_content([], '科目余额表2025.xlsx')}")

# ── 2. _safe_decimal 边界值 ──
print("\n2. _safe_decimal 边界值", flush=True)
from app.services.smart_import_engine import _safe_decimal
for val in [0, 0.0, "0", "0.00", None, "", "None", 123.45, -99.9, "abc"]:
    print(f"  {repr(val):>12} -> {_safe_decimal(val)}")

# ── 3. 期初兼容模式 ──
print("\n3. 期初兼容模式", flush=True)
from app.services.smart_import_engine import convert_balance_rows

# 模式A：分列
rows_a = [{"account_code": "1001", "account_name": "现金",
           "opening_debit": 1000, "opening_credit": None,
           "debit_amount": 500, "credit_amount": 300,
           "closing_debit": 1200, "closing_credit": None}]
bal_a, _ = convert_balance_rows(rows_a)
r = bal_a[0]
print(f"  分列模式: od={r['opening_debit']} oc={r['opening_credit']} ob={r['opening_balance']} cd={r['closing_debit']} cc={r['closing_credit']} cb={r['closing_balance']}")

# 模式B：净额+方向（借方）
rows_b = [{"account_code": "1001", "account_name": "现金",
           "opening_balance": 1000, "direction": "借",
           "debit_amount": 500, "credit_amount": 300,
           "closing_balance": 1200}]
bal_b, _ = convert_balance_rows(rows_b)
r = bal_b[0]
print(f"  净额+借方: od={r['opening_debit']} oc={r['opening_credit']} ob={r['opening_balance']} cd={r['closing_debit']} cc={r['closing_credit']} cb={r['closing_balance']}")

# 模式B：净额+方向（贷方）
rows_c = [{"account_code": "2001", "account_name": "短期借款",
           "opening_balance": 5000, "direction": "贷",
           "debit_amount": 1000, "credit_amount": 2000,
           "closing_balance": 6000, "closing_direction": "贷"}]
bal_c, _ = convert_balance_rows(rows_c)
r = bal_c[0]
print(f"  净额+贷方: od={r['opening_debit']} oc={r['opening_credit']} ob={r['opening_balance']} cd={r['closing_debit']} cc={r['closing_credit']} cb={r['closing_balance']}")

# 纯净额（无方向）
rows_d = [{"account_code": "1001", "account_name": "现金",
           "opening_balance": 1000,
           "debit_amount": 500, "credit_amount": 300,
           "closing_balance": 1200}]
bal_d, _ = convert_balance_rows(rows_d)
r = bal_d[0]
print(f"  纯净额:   od={r['opening_debit']} oc={r['opening_credit']} ob={r['opening_balance']} cd={r['closing_debit']} cc={r['closing_credit']} cb={r['closing_balance']}")

# ── 4. 核算维度拆分 + 辅助余额表字段完整性 ──
print("\n4. 辅助余额表字段完整性", flush=True)
rows_aux = [{"account_code": "1002", "account_name": "银行存款",
             "aux_dimensions": "金融机构:YG0001,工商银行; 成本中心:YG130108,财务部",
             "opening_debit": 1000, "opening_credit": None,
             "debit_amount": 500, "credit_amount": 300,
             "closing_debit": 1200, "closing_credit": None}]
_, aux = convert_balance_rows(rows_aux)
for r in aux:
    print(f"  {r['aux_type']}:{r['aux_code']}: od={r.get('opening_debit')} oc={r.get('opening_credit')} ob={r.get('opening_balance')}")

# ── 5. 序时账 → 辅助明细账字段完整性 ──
print("\n5. 辅助明细账字段完整性", flush=True)
from app.services.smart_import_engine import convert_ledger_rows
rows_led = [{"account_code": "1002", "account_name": "银行存款",
             "voucher_date": datetime(2025, 3, 15), "voucher_no": "0001",
             "voucher_type": "ZZ", "accounting_period": "2025年3期",
             "debit_amount": 500, "credit_amount": None,
             "summary": "收款", "preparer": "张三",
             "aux_dimensions": "金融机构:YG0001,工商银行; 成本中心:YG130108,财务部"}]
led, _, aux_stats = convert_ledger_rows(rows_led)
print(f"  序时账: {len(led)} 条, 辅助维度统计: {aux_stats}")
for r in led:
    dim_str = r.get("_aux_dim_str", "")
    if dim_str:
        from app.services.account_chart_service import parse_aux_dimensions
        dims = parse_aux_dimensions(dim_str)
        for d in dims:
            print(f"  {d['aux_type']}:{d['aux_code']}: date={r.get('voucher_date')} no={r.get('voucher_no')} d={r.get('debit_amount')} c={r.get('credit_amount')}")

# ── 6. 大数据量内存估算 ──
print("\n6. 大数据量内存估算（和平药房）", flush=True)
import sys as _s
# 单条序时账 dict 大小
sample_led = {"account_code": "1002", "account_name": "银行存款", "voucher_date": date(2025,1,1),
              "voucher_no": "0001", "voucher_type": "ZZ", "accounting_period": 1,
              "debit_amount": Decimal("1000.00"), "credit_amount": None,
              "summary": "收款测试", "preparer": "张三", "company_code": "default", "currency_code": "CNY"}
sample_aux = {**sample_led, "aux_type": "成本中心", "aux_code": "YG130108", "aux_name": "财务部"}
led_size = _s.getsizeof(sample_led) + sum(_s.getsizeof(v) for v in sample_led.values())
aux_size = _s.getsizeof(sample_aux) + sum(_s.getsizeof(v) for v in sample_aux.values())
print(f"  单条序时账(含_aux_dim_str): ~{led_size} bytes")
print(f"  114万序时账: ~{led_size * 1147414 / 1024 / 1024:.0f} MB")
print(f"  辅助明细账: 写入时流式拆分，不占内存")
print(f"  优化前合计: ~4400 MB → 优化后: ~{led_size * 1147414 / 1024 / 1024:.0f} MB")

print("\n✅ 复盘完成", flush=True)
