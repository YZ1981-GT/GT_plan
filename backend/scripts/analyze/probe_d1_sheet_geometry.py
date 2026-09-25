# -*- coding: utf-8 -*-
"""D1 模板逐 sheet 几何实测 —— 声明层的唯一几何真源（禁推演）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 1 / 25 / 26 / 27 / 28 / 29
Requirements 5.1（接入清单从模板 21 张实测 sheet 推出）

═══ 为什么必须实测而不是推演 ═══

上游 spec 的「禁推演」铁律（E1 spec 裁决 H8 把它从键名扩展到形态）：几何数字一旦推演，
声明与模板就会漂移，而漂移的后果是 materialize 写到错的行/列，且**判据未必发现**
（判据也照着同一份推演写）。本脚本 openpyxl 逐格直读权威模板，输出：

  * 每张 sheet 的表头行候选（首个有 ≥3 个非空文本格的行）
  * 数据区首末行（表头之后到 footer 之前）
  * footer 行与 marker 文本（A 列出现「合计」「小计」等）
  * 逐列公式分布（哪些列在数据行里有公式 ⇒ formula_columns）
  * 公式模板（按行号归一为 `{r}`，供 formula_templates 与逐行比对守卫）
  * 最后一个有内容的列（managed_last_col ⇒ uuid_col 取其右侧）

用法：
  python backend/scripts/analyze/probe_d1_sheet_geometry.py                  # 全部 21 张
  python backend/scripts/analyze/probe_d1_sheet_geometry.py --sheet D1-2     # 按编号过滤
  python backend/scripts/analyze/probe_d1_sheet_geometry.py --json out.json  # 落证据

🔴 输出是**实测**，不是裁决：形态判定（binding_kind / row_identity_key）还需前端三元组
   （store 键是否存在 / addRow-removeRow 信号 / composable 归属），见 E1 spec 裁决 H8。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
TEMPLATE = _BACKEND / "wp_templates" / "D" / "D1 应收票据.xlsx"

_FOOTER_MARKERS = ("合计", "小计", "总计", "合  计", "合   计")
_ROW_NUM = re.compile(r"(?<=[A-Z$])(\d+)")


def _normalise_formula(formula: str, row: int) -> str:
    """把公式里的当前行号换成 `{r}`（`=D11+E11+F11` → `=D{r}+E{r}+F{r}`）。"""
    return re.sub(rf"(?<=[A-Z]){row}\b", "{r}", formula)


def probe_sheet(ws) -> dict[str, Any]:
    max_r, max_c = ws.max_row, ws.max_column
    from openpyxl.utils import get_column_letter

    # 表头候选：首个 ≥3 个非空字符串格的行（前 15 行内）
    header_row = None
    for r in range(1, min(max_r, 16) + 1):
        texts = sum(
            1
            for c in range(1, max_c + 1)
            if isinstance(ws.cell(row=r, column=c).value, str)
            and str(ws.cell(row=r, column=c).value).strip()
        )
        if texts >= 3:
            header_row = r
            break

    # footer：A 列（或 B 列）出现 marker 的最大行
    footer_row = None
    footer_marker = None
    for r in range(max_r, 0, -1):
        for c in (1, 2):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip().replace(" ", "").replace("\u3000", "") in {
                m.replace(" ", "").replace("\u3000", "") for m in _FOOTER_MARKERS
            }:
                footer_row, footer_marker = r, v
                break
        if footer_row:
            break

    # 数据区：表头之后到 footer 之前
    first_data_row = (header_row + 1) if header_row else None
    last_data_row = (footer_row - 1) if footer_row else None

    # 逐列公式分布（限数据区）
    formula_cols: dict[str, list[str]] = {}
    if first_data_row and last_data_row and last_data_row >= first_data_row:
        for c in range(1, max_c + 1):
            col = get_column_letter(c)
            templates: set[str] = set()
            hits = 0
            for r in range(first_data_row, last_data_row + 1):
                v = ws.cell(row=r, column=c).value
                if isinstance(v, str) and v.startswith("="):
                    hits += 1
                    templates.add(_normalise_formula(v, r))
            if hits:
                formula_cols[col] = sorted(templates)

    # 最后一个有内容的列
    managed_last_col = None
    for c in range(max_c, 0, -1):
        if any(ws.cell(row=r, column=c).value is not None for r in range(1, max_r + 1)):
            managed_last_col = get_column_letter(c)
            break

    # footer 行的公式（合计行是否 SUM）
    footer_formulas: dict[str, str] = {}
    if footer_row:
        for c in range(1, max_c + 1):
            v = ws.cell(row=footer_row, column=c).value
            if isinstance(v, str) and v.startswith("="):
                footer_formulas[get_column_letter(c)] = v

    # 表头文本（供 header_text 逐字比对）
    header_texts: dict[str, str] = {}
    if header_row:
        for c in range(1, max_c + 1):
            v = ws.cell(row=header_row, column=c).value
            if isinstance(v, str) and v.strip():
                header_texts[get_column_letter(c)] = v.strip()

    return {
        "sheet": ws.title,
        "dims": ws.dimensions,
        "max_row": max_r,
        "max_column": max_c,
        "header_row": header_row,
        "header_texts": header_texts,
        "first_data_row": first_data_row,
        "last_data_row": last_data_row,
        "footer_row": footer_row,
        "footer_marker": footer_marker,
        "footer_formulas": footer_formulas,
        "formula_columns": sorted(formula_cols),
        "formula_templates": formula_cols,
        "managed_last_col": managed_last_col,
    }


def run(sheet_filter: str | None = None) -> dict[str, Any]:
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE, data_only=False)
    out: list[dict[str, Any]] = []
    for name in wb.sheetnames:
        if sheet_filter and sheet_filter not in name:
            continue
        out.append(probe_sheet(wb[name]))
    return {
        "template": str(TEMPLATE.relative_to(_REPO)),
        "sheet_count": len(wb.sheetnames),
        "probed": len(out),
        "sheets": out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", type=str, default=None, help="按 sheet 名子串过滤（如 D1-2）")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()

    report = run(args.sheet)
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写 {args.json}（{report['probed']} 张）")
        return 0

    for s in report["sheets"]:
        print(f"\n=== {s['sheet']} ===")
        print(f"  dims={s['dims']} header_row={s['header_row']} "
              f"data={s['first_data_row']}..{s['last_data_row']} "
              f"footer={s['footer_row']}({s['footer_marker']!r}) last_col={s['managed_last_col']}")
        if s["formula_columns"]:
            print(f"  formula_columns={s['formula_columns']}")
            for col, tpls in s["formula_templates"].items():
                print(f"    {col}: {tpls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
