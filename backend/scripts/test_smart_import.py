# -*- coding: utf-8 -*-
"""测试通用智能导入引擎"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.smart_import_engine import smart_parse_files

base = Path(__file__).resolve().parent.parent.parent / "数据"

files = []
with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    files.append(("科目余额表.xlsx", f.read()))
with open(base / "25年序时账" / "序时账-重庆和平药房连锁有限责任公司 20250101-1011.xlsx", "rb") as f:
    files.append(("序时账1-10月.xlsx", f.read()))
with open(base / "25年序时账" / "序时账-重庆和平药房连锁有限责任公司 20251012-1031.xlsx", "rb") as f:
    files.append(("序时账10月下.xlsx", f.read()))

print("开始解析...")
result = smart_parse_files(files)

print(f"年度: {result['year']}")
print(f"余额表: {len(result['balance_rows'])} 行")
print(f"辅助余额表: {len(result['aux_balance_rows'])} 行")
print(f"序时账: {len(result['ledger_rows'])} 行")
print(f"辅助明细账: {len(result['aux_ledger_rows'])} 行")

print(f"\n辅助核算维度:")
for d in result["aux_dimensions"][:10]:
    print(f"  {d['type']}: {d['count']}")

print(f"\n校验结果: {len(result['validation'])} 条")
for v in result["validation"][:5]:
    print(f"  [{v['level']}] {v['message']}")

print(f"\n诊断:")
for d in result["diagnostics"]:
    status = d["status"]
    extra = ""
    if "balance_count" in d:
        extra = f" (余额{d['balance_count']}, 辅助余额{d['aux_balance_count']})"
    elif "ledger_count" in d:
        extra = f" (序时账{d['ledger_count']}, 辅助明细{d['aux_ledger_count']})"
    print(f"  {d['file']} / {d['sheet']}: {d['data_type']} ({d.get('row_count', 0)} rows) [{status}]{extra}")
