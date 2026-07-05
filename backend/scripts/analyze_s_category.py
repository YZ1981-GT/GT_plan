"""Inventory S-category (特定项目程序) working paper templates.

Reads every .xlsx/.xls under the S folder and prints a compact summary:
per-file sheet names + (rows x cols) + merged-cell count + formula count.
Read-only analysis; writes nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

ROOT = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\6.特定项目程序（S）"
)


def summarize_sheet(ws) -> str:
    rows = ws.max_row or 0
    cols = ws.max_column or 0
    merged = len(ws.merged_cells.ranges)
    formulas = 0
    longtext = 0
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str):
                if v.startswith("="):
                    formulas += 1
                elif len(v) > 80:
                    longtext += 1
    return f"{rows}x{cols} merged={merged} formula={formulas} longtext={longtext}"


def main() -> None:
    files = sorted(
        [p for p in ROOT.rglob("*") if p.suffix.lower() in (".xlsx", ".xls")],
        key=lambda p: str(p),
    )
    print(f"# S-category templates: {len(files)} spreadsheet files\n")
    for p in files:
        rel = p.relative_to(ROOT)
        try:
            wb = openpyxl.load_workbook(p, read_only=False, data_only=False)
        except Exception as e:  # noqa: BLE001
            print(f"## {rel}\n  <ERROR: {e}>\n")
            continue
        print(f"## {rel}  (sheets={len(wb.sheetnames)})")
        for name in wb.sheetnames:
            ws = wb[name]
            print(f"  - [{name}] {summarize_sheet(ws)}")
        wb.close()
        print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
