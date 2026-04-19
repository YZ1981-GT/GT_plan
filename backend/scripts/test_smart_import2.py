# -*- coding: utf-8 -*-
"""分步测试通用引擎"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.smart_import_engine import smart_parse_files

base = Path(__file__).resolve().parent.parent.parent / "数据"

# 只测试余额表
print("=== 测试余额表 ===")
t0 = time.time()
with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    files = [("科目余额表.xlsx", f.read())]
result = smart_parse_files(files)
print(f"耗时: {time.time()-t0:.1f}s")
print(f"余额表: {len(result['balance_rows'])} 行")
print(f"辅助余额表: {len(result['aux_balance_rows'])} 行")
print(f"年度: {result['year']}")
for d in result["diagnostics"]:
    print(f"  {d['file']}/{d['sheet']}: {d['data_type']} ({d.get('row_count',0)} rows) [{d['status']}]")
    if "balance_count" in d:
        print(f"    余额{d['balance_count']}, 辅助余额{d['aux_balance_count']}")
print(f"维度: {result['aux_dimensions'][:5]}")
