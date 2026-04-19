# -*- coding: utf-8 -*-
"""测试四表间一致性校验（新版）"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.smart_import_engine import smart_parse_files

base = Path(__file__).resolve().parent.parent.parent / "数据"

print("解析文件...", flush=True)
t0 = time.time()
files = []
with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    files.append(("余额表.xlsx", f.read()))
with open(base / "25年序时账" / "序时账-重庆和平药房连锁有限责任公司 20251012-1031.xlsx", "rb") as f:
    files.append(("序时账.xlsx", f.read()))

result = smart_parse_files(files)
print(f"解析耗时: {time.time()-t0:.1f}s", flush=True)
print(f"balance={len(result['balance_rows'])}, aux_bal={len(result['aux_balance_rows'])}, "
      f"ledger={len(result['ledger_rows'])}, aux_led={len(result['aux_ledger_rows'])}", flush=True)

print(f"\n校验结果: {len(result['validation'])} 条", flush=True)
for v in result["validation"]:
    icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(v["level"], "?")
    print(f"  {icon} [{v['category']}] {v['message']}", flush=True)
