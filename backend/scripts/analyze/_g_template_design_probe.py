"""一次性（C-6）：余八条「模板编制说明 + 受管表几何 + 前端字段」三合一取数。

spec g-cycle-single-region-detail-lanes · C-6

用法：
  python backend/scripts/analyze/_g_template_design_probe.py            # 列各册 sheet 名
  python backend/scripts/analyze/_g_template_design_probe.py G10 notes # 倒编制说明全文
  python backend/scripts/analyze/_g_template_design_probe.py G10 geom  # 受管表几何（表头/行区/公式）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
TPL = ROOT / "wp_templates" / "G"

BOOKS = {
    "G1": ("G1 交易性金融资产.xlsx", "明细表G1-2"),
    "G3": ("G3 应收股利.xlsx", "明细表G3-2"),
    "G8": ("G8 其他权益工具投资.xlsx", "明细表G8-2"),
    "G9": ("G9 其他非流动金融资产.xlsx", "明细表G9-2"),
    "G10": ("G10 交易性金融负债.xlsx", "明细表G10-2"),
    "G11": ("G11 投资收益.xlsx", "明细分析表G11-2"),
    "G12": ("G12 净敞口套期收益.xlsx", "明细表G12-2"),
    "G13": ("G13 公允价值变动收益.xlsx", "明细表G13-2"),
    "G14": ("G14 信用减值损失.xlsx", "明细表G14-2"),
}

_NOTE_HINT = re.compile(r"说明|指引|填表|编制|索引|目录")


def list_sheets() -> None:
    for code, (book, managed) in BOOKS.items():
        wb = load_workbook(TPL / book, data_only=False)
        marks = []
        for name in wb.sheetnames:
            tag = ""
            if name == managed:
                tag = " ⭐受管"
            elif _NOTE_HINT.search(name):
                tag = " 📝"
            marks.append(f"{name}{tag}")
        print(f"\n== {code} ({book}) {len(wb.sheetnames)} sheets ==")
        for m in marks:
            print("   ", m)
        wb.close()


def dump_notes(code: str) -> None:
    """倒出「编制说明」类 sheet 的全部非空文本 + 受管表内正文段（标题行之下的说明块）。"""
    book, managed = BOOKS[code]
    wb = load_workbook(TPL / book, data_only=False)
    for name in wb.sheetnames:
        if not _NOTE_HINT.search(name):
            continue
        ws = wb[name]
        print(f"\n===== {code} · sheet「{name}」({ws.max_row}×{ws.max_column}) =====")
        for row in ws.iter_rows():
            texts = [
                f"{c.coordinate}={str(c.value).strip()}"
                for c in row
                if isinstance(c.value, str) and c.value.strip()
            ]
            if texts:
                print("  " + " | ".join(texts))
    # 受管表自身的说明块（G9 的编制思路就在受管表尾部 A38-A43）
    ws = wb[managed]
    print(f"\n===== {code} · 受管表「{managed}」内的文本块 =====")
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            if isinstance(v, str) and len(v.strip()) >= 12 and not v.startswith("="):
                print(f"  {c.coordinate} {v.strip()}")
    wb.close()


def dump_geom(code: str) -> None:
    book, managed = BOOKS[code]
    wb = load_workbook(TPL / book, data_only=False)
    ws = wb[managed]
    print(f"\n===== {code} · {managed} max_row={ws.max_row} max_col={ws.max_column} =====")
    print("definedNames:", [dn for dn in wb.defined_names])
    print("\n-- 合并区（前 40）--")
    for rng in sorted(str(r) for r in ws.merged_cells.ranges)[:40]:
        print("   ", rng, repr(ws[rng.split(":")[0]].value))
    print("\n-- 逐行摘要（前 40 行）--")
    for r in range(1, min(ws.max_row, 40) + 1):
        cells = []
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            mark = "ƒ" if isinstance(v, str) and v.startswith("=") else ""
            cells.append(f"{get_column_letter(c)}{mark}={str(v)[:26]}")
        if cells:
            print(f"  R{r:<3} " + " | ".join(cells[:14]) + (" …" if len(cells) > 14 else ""))
    print("\n-- 公式列（按列聚合，取首个出现的模板）--")
    by_col: dict[str, tuple[int, str]] = {}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                letter = get_column_letter(c.column)
                if letter not in by_col:
                    by_col[letter] = (c.row, c.value)
    for letter, (r, f) in sorted(by_col.items(), key=lambda kv: len(kv[0]) * 100 + ord(kv[0][0])):
        print(f"   {letter:3} R{r:<3} {f}")
    wb.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        list_sheets()
    else:
        code = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "geom"
        (dump_notes if mode == "notes" else dump_geom)(code)
