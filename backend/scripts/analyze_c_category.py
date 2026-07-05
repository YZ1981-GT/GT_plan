"""Inventory C-category (风险应对-一般性程序与控制测试 C1-C26) templates.

Captures per sheet: dims, merged, formula/longtext counts, hyperlinks (跳转),
defined names, and whether the workbook carries a VBA project (macros).
Read-only.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import openpyxl

ROOT = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\3.风险应对-一般性程序与控制测试（C1-C26）"
)


def has_vba(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return any("vbaProject" in n for n in z.namelist())
    except Exception:  # noqa: BLE001
        return False


def sheet_summary(ws) -> str:
    rows = ws.max_row or 0
    cols = ws.max_column or 0
    merged = len(ws.merged_cells.ranges)
    formulas = longtext = 0
    hyper = []
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str):
                if v.startswith("="):
                    formulas += 1
                elif len(v) > 80:
                    longtext += 1
            if cell.hyperlink is not None:
                tgt = cell.hyperlink.location or cell.hyperlink.target or ""
                hyper.append(f"{cell.coordinate}->{tgt}")
    hyper_str = f" hyper={len(hyper)}" if hyper else ""
    return f"{rows}x{cols} merged={merged} formula={formulas} longtext={longtext}{hyper_str}", hyper


def main() -> None:
    files = sorted(
        [p for p in ROOT.rglob("*") if p.suffix.lower() in (".xlsx", ".xlsm")],
        key=lambda p: str(p),
    )
    print(f"# C-category templates: {len(files)} spreadsheet files\n")
    for p in files:
        rel = p.relative_to(ROOT)
        vba = " [VBA/macros]" if has_vba(p) else ""
        try:
            wb = openpyxl.load_workbook(p, data_only=False)
        except Exception as e:  # noqa: BLE001
            print(f"## {rel}{vba}\n  <ERROR: {e}>\n")
            continue
        dn = list(wb.defined_names) if hasattr(wb, "defined_names") else []
        print(f"## {rel}{vba}  (sheets={len(wb.sheetnames)}, definedNames={len(dn)})")
        for name in wb.sheetnames:
            ws = wb[name]
            summ, hyper = sheet_summary(ws)
            print(f"  - [{name}] {summ}")
            for h in hyper[:8]:
                print(f"      jump: {h}")
        wb.close()
        print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
