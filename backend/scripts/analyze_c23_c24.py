"""Phase0 analysis for C23/C24 journal entry testing spec.

Extracts:
- Sheet names, dimensions, formula/merged counts
- Column headers for each sheet
- Benford formula patterns
- Anomaly rules from C24-5
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import openpyxl

ROOT = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\3.风险应对-一般性程序与控制测试（C1-C26）"
)

C23_FILE = ROOT / "C23 会计分录 - 控制测试.xlsx"
C24_FILE = ROOT / "C24 会计分录 - 细节测试.xlsx"


def analyze_sheet(ws, max_header_rows=5, max_content_rows=50):
    """Analyze a single sheet: headers, formulas, content sample."""
    info = {
        "dimensions": f"{ws.max_row}x{ws.max_column}",
        "merged_ranges": len(ws.merged_cells.ranges),
        "formulas": [],
        "headers": [],
        "content_sample": [],
    }
    
    formula_count = 0
    formula_examples = []
    
    for r_i, row in enumerate(ws.iter_rows(values_only=False), start=1):
        row_values = []
        for cell in row:
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                formula_count += 1
                if len(formula_examples) < 10:
                    formula_examples.append(f"{cell.coordinate}: {v[:120]}")
            if v is not None:
                row_values.append(str(v).strip().replace("\n", " ")[:80])
        
        if r_i <= max_header_rows and row_values:
            info["headers"].append(row_values)
        elif r_i <= max_content_rows and row_values:
            info["content_sample"].append(f"R{r_i}: {' | '.join(row_values[:15])}"[:200])
    
    info["formula_count"] = formula_count
    info["formula_examples"] = formula_examples
    return info


def main():
    results = {}
    
    for label, filepath in [("C23", C23_FILE), ("C24", C24_FILE)]:
        print(f"\n{'='*60}")
        print(f"  {label}: {filepath.name}")
        print(f"{'='*60}")
        
        if not filepath.exists():
            print(f"  FILE NOT FOUND: {filepath}")
            continue
        
        wb = openpyxl.load_workbook(filepath, data_only=False)
        print(f"  Sheets ({len(wb.sheetnames)}): {wb.sheetnames}")
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            print(f"\n  --- [{sheet_name}] ---")
            info = analyze_sheet(ws)
            print(f"  Dims: {info['dimensions']}, Merged: {info['merged_ranges']}, Formulas: {info['formula_count']}")
            
            print(f"  Headers (first {len(info['headers'])} rows):")
            for i, h in enumerate(info["headers"]):
                print(f"    R{i+1}: {' | '.join(h[:12])}"[:200])
            
            if info["formula_examples"]:
                print(f"  Formula examples ({len(info['formula_examples'])} of {info['formula_count']}):")
                for fe in info["formula_examples"]:
                    print(f"    {fe}")
            
            if info["content_sample"]:
                print(f"  Content sample ({len(info['content_sample'])} rows):")
                for cs in info["content_sample"][:20]:
                    print(f"    {cs}")
        
        wb.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
