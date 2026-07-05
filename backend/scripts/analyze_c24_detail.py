"""Detailed analysis of C24 formulas and structure for Phase0."""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\3.风险应对-一般性程序与控制测试（C1-C26）"
)

wb = openpyxl.load_workbook(ROOT / "C24 会计分录 - 细节测试.xlsx", data_only=False)

# 1. N-column formula (holiday/weekend check) from virtual entries
ws = wb["参考-本福特定律测试-虚拟会计分录"]
print("=== N-column formula (holiday/weekend check) ===")
n2 = ws["N2"].value
print(f"N2: {n2}")
print()
print("=== O-column formula (gap/skip detection) ===")
o3 = ws["O3"].value
print(f"O3: {o3}")
print()

# Column headers of virtual entries
print("=== Virtual entries column headers (row 1) ===")
for cell in ws[1]:
    if cell.value:
        print(f"  {cell.coordinate}: {cell.value}")
print()

# Check columns M, N, O headers
print("=== Columns M/N/O in virtual entries ===")
print(f"  M1: {ws['M1'].value}")
print(f"  N1: {ws['N1'].value}")
print(f"  O1: {ws['O1'].value}")
print()

# 2. Benford sheet full structure
ws2 = wb["参考-本福特定律测试"]
print("=== Benford sheet rows 14-50 (full formula area) ===")
for r_i, row in enumerate(ws2.iter_rows(min_row=14, max_row=50, values_only=False), start=14):
    cells = []
    for cell in row:
        v = cell.value
        if v is not None:
            cells.append(f"{cell.coordinate}={str(v)[:100]}")
    if cells:
        joined = "  |  ".join(cells[:8])
        print(f"  R{r_i}: {joined}")
print()

# 3. Benford defined names
print("=== Defined names ===")
for dn in wb.defined_names.definedName:
    print(f"  {dn.name}: {dn.attr_text}")
print()

# 4. C24-0 full content rows 24-50
print("=== C24-0 rows 24-50 (test items summary) ===")
ws0 = wb["C24-0汇总表"]
for r_i, row in enumerate(ws0.iter_rows(min_row=24, max_row=80, values_only=True), start=24):
    cells = [str(c).strip().replace("\n", " ")[:100] for c in row if c is not None and str(c).strip()]
    if cells:
        joined = " | ".join(cells)
        print(f"  R{r_i}: {joined}")
print()

# 5. C24-3 skip-test formula detail
print("=== C24-3 skip test formula (B37) ===")
ws3 = wb["C24-3完整性-跳号测试"]
print(f"  B37: {ws3['B37'].value}")
print()

# 6. C24-2 column headers row 26
print("=== C24-2 column headers (row 26) ===")
ws_c242 = wb["C24-2完整性-分录&余额表对比"]
for cell in ws_c242[26]:
    if cell.value:
        print(f"  {cell.coordinate}: {str(cell.value)[:80]}")
print()

# 7. C24-5 anomaly rules rows 24-38
print("=== C24-5 anomaly rules (rows 24-38) ===")
ws5 = wb["C24-5细节测试-异常分录测试"]
for r_i, row in enumerate(ws5.iter_rows(min_row=24, max_row=46, values_only=True), start=24):
    cells = [str(c).strip().replace("\n", " ")[:80] for c in row if c is not None and str(c).strip()]
    if cells:
        joined = " | ".join(cells)
        print(f"  R{r_i}: {joined}")

wb.close()
