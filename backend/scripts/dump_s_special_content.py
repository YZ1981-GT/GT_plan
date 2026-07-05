"""Dump text of calculation-type and special-transaction S templates (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

BASE = Path(
    r"d:\GT_plan\数据\致同通用审计程序及底稿模板（2025年修订）"
    r"\1.致同审计程序及底稿模板（2025年）\6.特定项目程序（S）"
)

TARGETS = [
    ("S15 每股收益和净资产收益率.xlsx", ["基本每股收益计算表S15-2", "净资产收益率计算S15-4"]),
    ("S21 数据资产.xlsx", ["开发支出资本化分析表S21-2", "成本归集与分摊检查表S21-3"]),
    ("S20 营业收入扣除情况核查底稿202504.xlsx", ["营业收入扣除情况核查"]),
    ("S4 非货币性资产交换202401.xlsx", ["审定表S4-1", "商业实质的判断S4-2"]),
    ("S5 债务重组202401.xlsx", ["审定表S5-1", "债务重组损益确认时点S5-2"]),
    ("S12 利用专家（注册会计师的专家）的工作.xlsx", ["S12 利用专家的工作程序表"]),
    ("S14 会计估计和相关披露.xlsx", ["S14程序表"]),
]


def dump(ws, max_rows: int = 34) -> None:
    for r_i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if r_i > max_rows:
            print("    ... (truncated)")
            break
        cells = [str(c).strip().replace("\n", " ") for c in row if c is not None and str(c).strip()]
        if cells:
            print(f"    {r_i:>3}: {' | '.join(cells)[:200]}")


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
