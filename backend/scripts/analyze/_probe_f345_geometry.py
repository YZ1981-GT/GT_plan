#!/usr/bin/env python
"""一次性探针（用完即删）：F3/F4/F5 三册模板逐格实测几何。

spec: f3/f4/f5-sync-coverage-and-first-canary · Task 2

输出每张受管候选 sheet 的：
  * 尺寸 / sha256 / sheet_state
  * A 列逐行文本（定位表头 / footer / 锚行，**逐字含空格**）
  * 数据区逐列公式（判 formula_columns）
  * 空列检测（判 uuid_col —— 数据区与表头全空的最靠近列）
  * 数字格式含 % 的列（FC-10 逐列取证）
  * 数据验证区间

用法::
    python backend/scripts/analyze/_probe_f345_geometry.py F3
    python backend/scripts/analyze/_probe_f345_geometry.py F4 --sheets "未入账检查表F4-7"
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

_BACKEND = pathlib.Path(__file__).resolve().parent.parent.parent
TEMPLATES = {
    "F3": _BACKEND / "wp_templates" / "F" / "F3 应付票据.xlsx",
    "F4": _BACKEND / "wp_templates" / "F" / "F4 应付账款.xlsx",
    "F5": _BACKEND / "wp_templates" / "F" / "F5 营业成本.xlsx",
}


def cell_text(ws, row: int, col: int) -> str:
    v = ws.cell(row=row, column=col).value
    return "" if v is None else str(v)


def dump_header_rows(ws, rows: list[int]) -> None:
    """指定行的逐列文本 + 该列数据区首格的数字格式（定性 FC-10 命中列）。"""
    print(f"\n-- 表头逐列文本 rows={rows} --")
    for r in rows:
        print(f"  R{r}:")
        for ci in range(1, min(ws.max_column, 40) + 1):
            L = get_column_letter(ci)
            v = ws.cell(row=r, column=ci).value
            if v is None:
                continue
            fmt = ws.cell(row=r, column=ci).number_format or ""
            print(f"     {L:<3} {str(v)[:44]!r:<48} fmt={fmt[:18]!r}")


def dump_data_formats(ws, *, first: int, last: int) -> None:
    """数据区逐列的数字格式 + 是否有公式（FC-10 判定的权威口径）。"""
    print(f"\n-- 数据区 R{first}-{last} 逐列格式/公式 --")
    for ci in range(1, min(ws.max_column, 40) + 1):
        L = get_column_letter(ci)
        fmts, n_formula, n_value = set(), 0, 0
        for r in range(first, last + 1):
            c = ws.cell(row=r, column=ci)
            fmts.add(c.number_format or "")
            if isinstance(c.value, str) and c.value.startswith("="):
                n_formula += 1
            elif c.value is not None:
                n_value += 1
        pct = any("%" in f for f in fmts)
        tag = ""
        if pct and n_formula == 0:
            tag = "  ← 🔴 百分比格式 + 零公式 ⇒ FC-10 命中候选"
        elif pct:
            tag = "  ← 百分比格式但有公式 ⇒ mode=formula，FC-10 不命中"
        print(f"  {L:<3} fmt={sorted(fmts)!s:<34} formula={n_formula:<3} value={n_value:<3}{tag}")


def probe_sheet(ws, *, max_rows: int) -> None:
    print(f"\n{'=' * 78}")
    print(f"SHEET {ws.title!r}  state={ws.sheet_state}  dims={ws.max_row}r x {ws.max_column}c "
          f"({get_column_letter(ws.max_column)})")
    print("=" * 78)

    # ── A 列逐行文本（逐字，含空格；用 repr 暴露空格与全角）────────────────
    print("\n-- A 列逐行（repr，暴露空格/全角）--")
    for r in range(1, min(ws.max_row, max_rows) + 1):
        a = cell_text(ws, r, 1)
        b = cell_text(ws, r, 2)
        if a or b:
            print(f"  R{r:<3} A={a[:46]!r:<50} B={b[:26]!r}")

    # ── 逐行公式分布 ───────────────────────────────────────────────────────
    print("\n-- 公式分布（行 -> 列:公式）--")
    formula_rows: dict[int, list[tuple[str, str]]] = {}
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_rows)):
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                formula_rows.setdefault(c.row, []).append((c.column_letter, c.value))
    for r in sorted(formula_rows):
        items = formula_rows[r]
        cols = ",".join(col for col, _ in items)
        print(f"  R{r:<3} [{len(items):>2}] cols={cols}")
        for col, f in items[:14]:
            print(f"        {col}{r} = {f[:96]}")

    # ── 空列检测（表头区 + 数据区全空的列）──────────────────────────────────
    print("\n-- 列占用（非空格计数，用于 uuid_col 判定）--")
    limit = min(ws.max_column + 4, 60)
    counts = []
    for ci in range(1, limit + 1):
        n = sum(
            1
            for r in range(1, min(ws.max_row, max_rows) + 1)
            if ws.cell(row=r, column=ci).value is not None
        )
        counts.append((get_column_letter(ci), n))
    print("  " + "  ".join(f"{L}:{n}" for L, n in counts))
    empties = [L for L, n in counts if n == 0]
    print(f"  全空列: {empties}")

    # ── 数字格式含 % 的格（FC-10 取证）──────────────────────────────────────
    print("\n-- 百分比格式格（FC-10 逐列取证）--")
    pct: dict[str, list[tuple[int, bool]]] = {}
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_rows)):
        for c in row:
            fmt = c.number_format or ""
            if "%" in fmt:
                is_formula = isinstance(c.value, str) and c.value.startswith("=")
                pct.setdefault(c.column_letter, []).append((c.row, is_formula))
    if not pct:
        print("  （无）")
    for col in sorted(pct, key=lambda x: (len(x), x)):
        rows = pct[col]
        n_formula = sum(1 for _, f in rows if f)
        sample_rows = [r for r, _ in rows][:8]
        print(f"  列 {col}: {len(rows)} 格，其中公式 {n_formula} 格"
              f"{'  ← 🔴 有非公式格（FC-10 命中风险）' if n_formula < len(rows) else '  ✅ 全是公式列'}"
              f"  rows={sample_rows}")

    # ── 数据验证 ───────────────────────────────────────────────────────────
    print("\n-- 数据验证 --")
    dvs = list(getattr(ws, "data_validations", []).dataValidation or [])
    if not dvs:
        print("  （无）")
    for dv in dvs:
        print(f"  {dv.sqref}  type={dv.type}  formula1={str(dv.formula1)[:80]}")

    # ── 合并单元格（表头层级判定辅助）──────────────────────────────────────
    merged = [str(m) for m in ws.merged_cells.ranges]
    print(f"\n-- 合并区 {len(merged)} 个 --")
    print("  " + ", ".join(merged[:40]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", choices=sorted(TEMPLATES))
    ap.add_argument("--sheets", default="", help="逗号分隔；留空=列出全部 sheet 名后退出")
    ap.add_argument("--max-rows", type=int, default=120)
    ap.add_argument("--header-rows", default="", help="逗号分隔行号：输出这些行的逐列文本")
    # 🔴 用逗号而非冒号：`--data-range 7:11` 会被 shell 包装层误判为 host:port 并拒绝执行。
    ap.add_argument("--data-range", default="", help="first,last —— 输出数据区逐列格式/公式")
    args = ap.parse_args()

    path = TEMPLATES[args.code]
    data = path.read_bytes()
    print(f"TEMPLATE {path.name}")
    print(f"  bytes={len(data):,}  sha256={hashlib.sha256(data).hexdigest()}")

    wb = load_workbook(path, data_only=False)
    try:
        print(f"  sheets={len(wb.sheetnames)}")
        for sn in wb.sheetnames:
            ws = wb[sn]
            print(f"    {sn!r:<52} state={ws.sheet_state:<7} {ws.max_row}r x {ws.max_column}c")
        if not args.sheets:
            return 0
        for sn in [s.strip() for s in args.sheets.split(",") if s.strip()]:
            if sn not in wb.sheetnames:
                print(f"\n[WARN] sheet {sn!r} 不存在")
                continue
            ws = wb[sn]
            probe_sheet(ws, max_rows=args.max_rows)
            if args.header_rows:
                dump_header_rows(ws, [int(x) for x in args.header_rows.split(",") if x.strip()])
            if args.data_range:
                first, last = (int(x) for x in args.data_range.split(","))
                dump_data_formats(ws, first=first, last=last)
    finally:
        wb.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
