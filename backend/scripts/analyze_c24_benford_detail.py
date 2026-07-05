"""Extract Benford formula detail structure and C24-0 full content."""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

BASE = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\3.风险应对-一般性程序与控制测试（C1-C26）"
)
C24_FILE = BASE / "C24 会计分录 - 细节测试.xlsx"
OUT = Path(r"d:\GT_plan\backend\scripts\c24_benford_detail.md")


def main() -> None:
    wb = openpyxl.load_workbook(C24_FILE, data_only=False)
    lines: list[str] = []

    # === Benford sheet structure ===
    ws_bf = wb["参考-本福特定律测试"]
    lines.append("# Benford Sheet Detail (参考-本福特定律测试)\n")
    lines.append(f"Size: {ws_bf.max_row}x{ws_bf.max_column}\n")

    # Row 1-40 content
    lines.append("## Content (rows 1-50):")
    for r in range(1, min(51, (ws_bf.max_row or 0) + 1)):
        cells = []
        for c in range(1, (ws_bf.max_column or 0) + 1):
            v = ws_bf.cell(r, c).value
            if v is not None:
                s = str(v).strip().replace("\n", " ")[:100]
                cells.append(f"C{c}:{s}")
        if cells:
            lines.append(f"  R{r}: {' | '.join(cells)}")

    # Key formula patterns (sample from different areas)
    lines.append("\n## Formula patterns:")
    formula_areas = {}
    for row in ws_bf.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                row_num = cell.row
                area = "header" if row_num < 15 else "benford_calc" if row_num < 50 else "data"
                if area not in formula_areas:
                    formula_areas[area] = []
                if len(formula_areas[area]) < 8:
                    formula_areas[area].append(f"  {cell.coordinate}: {v[:150]}")

    for area, formulas in formula_areas.items():
        lines.append(f"\n### {area}:")
        for f in formulas:
            lines.append(f)

    # === C24-0 full content (all rows) ===
    lines.append("\n\n# C24-0 汇总表 Full Content\n")
    ws_c0 = wb["C24-0汇总表"]
    for r in range(1, min(130, (ws_c0.max_row or 0) + 1)):
        cells = []
        for c in range(1, (ws_c0.max_column or 0) + 1):
            v = ws_c0.cell(r, c).value
            if v is not None:
                s = str(v).strip().replace("\n", " ")[:120]
                cells.append(s)
        if cells:
            lines.append(f"  R{r}: {' | '.join(cells)}")

    # === C23-2 detail (rows 35-72) ===
    lines.append("\n\n# C23-2 Control Test Detail (rows 35-72)\n")
    ws_c2 = wb if "会计分录控制测试C23-2" in wb.sheetnames else None
    if ws_c2 is None:
        wb23 = openpyxl.load_workbook(BASE / "C23 会计分录 - 控制测试.xlsx", data_only=False)
        ws_c23_2 = wb23["会计分录控制测试C23-2"]
    else:
        ws_c23_2 = None

    if ws_c23_2 is None:
        wb23 = openpyxl.load_workbook(BASE / "C23 会计分录 - 控制测试.xlsx", data_only=False)
        ws_c23_2 = wb23["会计分录控制测试C23-2"]

    for r in range(35, min(73, (ws_c23_2.max_row or 0) + 1)):
        cells = []
        for c in range(1, (ws_c23_2.max_column or 0) + 1):
            v = ws_c23_2.cell(r, c).value
            if v is not None:
                s = str(v).strip().replace("\n", " ")[:100]
                cells.append(f"C{c}:{s}")
        if cells:
            lines.append(f"  R{r}: {' | '.join(cells)}")

    wb.close()
    if 'wb23' in dir():
        wb23.close()

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written {len(lines)} lines to {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
