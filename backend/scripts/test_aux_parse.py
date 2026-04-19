# -*- coding: utf-8 -*-
"""验证 parse_aux_dimensions 对所有实际格式的覆盖情况"""
import sys, io, openpyxl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.account_chart_service import parse_aux_dimensions

base = Path(__file__).resolve().parent.parent.parent / "数据"
with open(base / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    content = f.read()
wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
ws = wb["sheet1"]

errors = []
type_stats = {}
total = 0
for row in ws.iter_rows(min_row=5, max_col=3, values_only=True):
    v = row[2]
    if not v or not str(v).strip():
        continue
    total += 1
    try:
        dims = parse_aux_dimensions(str(v))
        for d in dims:
            t = d["aux_type"]
            if t not in type_stats:
                type_stats[t] = {"has_code": 0, "auto_code": 0, "samples": []}
            if d["aux_code"].startswith("AUTO_"):
                type_stats[t]["auto_code"] += 1
                if len(type_stats[t]["samples"]) < 3:
                    type_stats[t]["samples"].append(f"{d['aux_code']} / {d['aux_name']}")
            else:
                type_stats[t]["has_code"] += 1
    except Exception as e:
        errors.append((str(v)[:80], str(e)))

print(f"总行数: {total}, 解析错误: {len(errors)}")
if errors:
    for v, e in errors[:5]:
        print(f"  ERROR: {v} -> {e}")

print(f"\n辅助核算类型统计:")
for t in sorted(type_stats.keys()):
    s = type_stats[t]
    total_t = s["has_code"] + s["auto_code"]
    print(f"  {t}: 有编号 {s['has_code']}, 自动编号 {s['auto_code']} (共{total_t})")
    if s["samples"]:
        for sample in s["samples"]:
            print(f"    样本: {sample}")
wb.close()
