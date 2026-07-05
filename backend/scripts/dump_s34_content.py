"""Dump text content of a few representative S34 IPO templates (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

BASE = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\6.特定项目程序（S）\S34 首发审核特项底稿"
)

TARGETS = [
    ("S34 -0证监会及沪深北证券交易所需会计师核查事项清单.xlsx", ["核查事项清单"]),
    ("S34-16 第三方回款.xlsx", ["S34-16程序表", "S34-16-1第三方回款情况检查表"]),
    ("S34-3 股份支付.xlsx", ["S34-3程序表"]),
]


def dump(ws, max_rows: int = 40) -> None:
    for r_i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if r_i > max_rows:
            print("    ... (truncated)")
            break
        cells = [str(c).strip().replace("\n", " ") for c in row if c is not None and str(c).strip()]
        if cells:
            line = " | ".join(cells)
            print(f"    {r_i:>3}: {line[:220]}")


def main() -> None:
    for fname, sheets in TARGETS:
        p = BASE / fname
        wb = openpyxl.load_workbook(p, data_only=False)
        for name in sheets:
            print(f"\n### {fname} :: [{name}]")
            dump(wb[name])
        wb.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
