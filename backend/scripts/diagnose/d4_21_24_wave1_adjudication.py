# -*- coding: utf-8 -*-
"""D4-21~24 Wave 1 只读裁决核定（本 spec DEC1/DEC2/Requirement 1）。

对运行时权威模板（finder 定位）逐 sheet 记录：真实 tab、几何（表头/数据区/footer）、
逐列表头、公式格（内部 OO 算术 vs 外链）、候选行身份、O 列枚举保留值、合并区、
以及 mapping_digest。产物落 spec evidence 目录，供 Task 1.2 书面裁决与后续 descriptor 引用。

用法（仓库根）：
  & .venv/Scripts/python.exe backend/scripts/diagnose/d4_21_24_wave1_adjudication.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Final

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from openpyxl import load_workbook  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from app.services.wp_template_finder import find_template_file  # noqa: E402

OUT = REPO / ".kiro" / "specs" / "d4-21-24-oo-bidirectional-and-cross-sheet-formula" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)

BRACKET_RE = re.compile(r"\[\d+\]")  # 外链引用 [n]

# 🔴 DEC1 workbook 裁决：D4-21~24 前端宿主同步 manifest 里全部
# `parent_duplicate` / `independentEntry:false`，parentEntryId=`xlsx/gt-d4-operating-revenue`。
# 该父 entry 的运行时权威 workbook = `D/D4 收入底稿.xlsx`，且**已实测包含** D4-21~24 五张
# sheet（与独立文件 D4-21…/D4-22至D4-32… 同名同结构）。故双向 descriptor 必须挂在这份
# 合册上（与 phase5_d4_revenue_detail 的 D4-2/3/5 同 workbook / 同 template blob），
# 而非 finder 对裸 wp_code 命中的 IPO 单册。census 因此直接锁定合册。
PARENT_WORKBOOK: Final = REPO / "backend" / "wp_templates" / "D" / "D4 收入底稿.xlsx"

# (wp_code, sheet 名, 实测表头行) —— 表头行经 openpyxl 逐格核定后写死，
# 不用密度启发式（这些表 row3/4 是 =底稿目录 外链，会骗过启发式）。
TARGETS = [
    ("D4-21", "关联方销售情况及价格分析D4-21", 15),
    ("D4-22A", "程序表D4-22A", 15),
    ("D4-22", "重要指标分析表D4-22", 11),
    ("D4-23", "收入与开具发票金额比较分析D4-23", 11),  # 两级表头 10+11，取下沿 11
    ("D4-24", "第三方回款检查D4-24", 14),
]


def _classify_formula(text: str) -> str:
    if BRACKET_RE.search(text):
        return "external_bracket"
    return "internal"


def _footer_marker(ws, first_data: int) -> tuple[int | None, str | None]:
    """找 footer 行（A 列含「合计」/「合 计」/纯枚举结论行的收口标记）。"""
    for r in range(first_data, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, str):
            compact = v.replace(" ", "").replace("\u3000", "")
            if "合计" in compact or compact.startswith("小计"):
                return r, v
    return None, None


def probe_sheet(path: Path, sheet_name: str, wp_code: str, header_row: int) -> dict:
    wb = load_workbook(path, data_only=False)
    if sheet_name not in wb.sheetnames:
        # 关键词兜底匹配
        cand = [n for n in wb.sheetnames if wp_code.replace("D4-", "") in n]
        sheet_name = cand[0] if cand else sheet_name
    ws = wb[sheet_name]
    max_row, max_col = ws.max_row, ws.max_column

    # 逐格快照（值 + 公式 + 是否合并主格）
    merged = [str(m) for m in ws.merged_cells.ranges]
    grid: list[dict] = []
    formulas: list[dict] = []
    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            v = cell.value
            if v is None:
                continue
            coord = cell.coordinate
            if isinstance(v, str) and v.startswith("="):
                formulas.append(
                    {
                        "cell": coord,
                        "col": get_column_letter(cell.column),
                        "row": cell.row,
                        "formula": v,
                        "kind": _classify_formula(v),
                    }
                )
                grid.append({"cell": coord, "value": v, "is_formula": True})
            else:
                grid.append({"cell": coord, "value": v, "is_formula": False})

    # 表头行由调用方核定传入（见 TARGETS 注释）。
    headers = {
        get_column_letter(c): ws.cell(header_row, c).value for c in range(1, max_col + 1)
    }
    first_data = header_row + 1
    footer_row, footer_text = _footer_marker(ws, first_data)
    last_data = (footer_row - 1) if footer_row else max_row

    # 数据区每列公式覆盖率（判内部算术列 → 候选 formula_mask）
    formula_cols: dict[str, list[str]] = {}
    for f in formulas:
        if first_data <= f["row"] <= (last_data if footer_row else max_row):
            formula_cols.setdefault(f["col"], []).append(f["formula"])

    # O 列保留枚举原值（D4-21 DEC2 / Req 1.3）：数据区外仍要逐字保留的静态列
    o_preserved: dict[str, str] = {}
    for r in range(header_row, max_row + 1):
        v = ws.cell(r, 15).value  # O = 15
        if v not in (None, ""):
            o_preserved[f"O{r}"] = v

    # 导航引用文本（<Dx-y> 等）—— D4-24 的 D2 引用裁决用（Req 5.1）
    nav_refs: list[dict] = []
    ref_re = re.compile(r"[<【]([A-Z]\d+[-\d]*)[>】]")
    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            if isinstance(cell.value, str):
                for m in ref_re.finditer(cell.value):
                    nav_refs.append({"cell": cell.coordinate, "ref": m.group(1)})

    wb.close()
    payload = {
        "wp_code": wp_code,
        "template_relative_path": str(path.relative_to(REPO / "backend" / "wp_templates")),
        "sheet_name": sheet_name,
        "dimensions": ws.dimensions,
        "max_row": max_row,
        "max_col": max_col,
        "header_row": header_row,
        "headers": headers,
        "first_data_row": first_data,
        "footer_row": footer_row,
        "footer_marker_exact": footer_text,
        "last_data_row": last_data,
        "merged_ranges": merged,
        "formula_count": len(formulas),
        "formula_cells": formulas,
        "data_region_formula_columns": {
            col: {"count": len(fs), "sample": fs[0]} for col, fs in sorted(formula_cols.items())
        },
        "o_column_preserved": o_preserved,
        "nav_refs": nav_refs,
    }
    return payload


def main() -> None:
    # DEC1：裁决 workbook = 父 entry 合册。同时记录 finder 对裸码命中的独立册
    # （证明「不走独立册」是有意裁决而非漏看）。
    finder_hits = {code: str(find_template_file(code)) for code, _sk, _h in TARGETS}
    if not PARENT_WORKBOOK.exists():
        raise SystemExit(f"父 workbook 不存在: {PARENT_WORKBOOK}")
    path = PARENT_WORKBOOK
    template_sha = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}
    results: list[dict] = []
    for wp_code, sheet_kw, hrow in TARGETS:
        results.append(probe_sheet(path, sheet_kw, wp_code, hrow))

    canon = json.dumps(
        [
            {
                "wp_code": r["wp_code"],
                "sheet_name": r["sheet_name"],
                "header_row": r["header_row"],
                "headers": r["headers"],
                "first_data_row": r["first_data_row"],
                "footer_row": r["footer_row"],
                "footer_marker_exact": r["footer_marker_exact"],
                "data_region_formula_columns": {
                    c: v["sample"] for c, v in r["data_region_formula_columns"].items()
                },
                "o_column_preserved": r["o_column_preserved"],
                "nav_refs": r["nav_refs"],
            }
            for r in results
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    mapping_digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()

    out = {
        "measured_at": "2026-09-13",
        "tool": "openpyxl data_only=False + finder",
        "workbook_adjudication": {
            "chosen_workbook": str(path.relative_to(REPO)),
            "reason": (
                "D4-21~24 前端同步 manifest 全部 parent_duplicate/independentEntry=false，"
                "parentEntryId=xlsx/gt-d4-operating-revenue，其权威 workbook=D/D4 收入底稿.xlsx "
                "已实测含 5 张 sheet；descriptor 挂合册（与 D4-2/3/5 同 blob）。"
            ),
            "finder_standalone_hits": finder_hits,
        },
        "template_sha256_by_path": template_sha,
        "mapping_digest": mapping_digest,
        "sheets": results,
    }
    (OUT / "T01-adjudication-census.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    # 精简摘要打印
    summary = {
        "mapping_digest": mapping_digest,
        "sheets": [
            {
                "wp_code": r["wp_code"],
                "sheet_name": r["sheet_name"],
                "dims": r["dimensions"],
                "header_row": r["header_row"],
                "first_data_row": r["first_data_row"],
                "footer": [r["footer_row"], r["footer_marker_exact"]],
                "last_data_row": r["last_data_row"],
                "formula_count": r["formula_count"],
                "data_region_formula_columns": list(r["data_region_formula_columns"].keys()),
            }
            for r in results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
