"""税审底稿计算模型（生成脚本内部模块）：样表 → ``backend/data/tax_workpaper_model.json``。

- 纳入的 sheet：索引编号对应的 sheet + 它们的公式传递引用到的 sheet（索引页、填写参数页、A 类申报表）。
- 纳入的格：编号 sheet 打印区内全部非空格 + 被公式（传递）引用到的格。
- 取数规则目标格：样表上的常量 / 公式删掉，值改由后端按项目账套取数；两条规则转成公式写入。
- 参数页「填写参数（无需打印）」B1~B15：标签、下拉选项、默认值来源（project 字段）。
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

from openpyxl.utils import range_boundaries
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.tax_formula_engine import FormulaSyntaxError, iter_functions, iter_refs, parse_formula  # noqa: E402
from tax_workpaper_rules import ParsedRules, RuleParser  # noqa: E402

PARAMS_SHEET = "填写参数（无需打印）"
RULE_HEADER = "取数规则"
# 参数页默认值：取项目信息；未列出的默认空（由用户在页面填写）
PARAM_DEFAULTS = {"B1": "client_name", "B8": "legal_representative", "B10": "period"}
_EXTERNAL_RE = re.compile(r"\[\d+\]")


def print_bounds(ws) -> tuple[int, int, int, int]:
    area = ws.print_area
    if area:
        first = area.split(",")[0].split("!")[-1].replace("$", "")
        min_col, min_row, max_col, max_row = range_boundaries(first)
        return min_row, min_col, max_row, max_col
    return 1, 1, ws.max_row, ws.max_column


def formula_text(cell) -> str | None:
    """openpyxl 公式格的公式文本（普通公式是 str，数组公式取 .text）。"""
    if cell.data_type != "f":
        return None
    value = cell.value
    text = value if isinstance(value, str) else getattr(value, "text", None)
    return _EXTERNAL_RE.sub("", text) if isinstance(text, str) else None


def constant_json(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y-%m-%d")
    text = str(value).replace("_x000D_", "")
    return text if text != "" else None


def collect_raw_rules(wb, sheet_names: list[str]) -> list[dict]:
    raw: list[dict] = []
    for name in sheet_names:
        ws = wb[name]
        header_row = next(
            (c.row for row in ws.iter_rows() for c in row if c.value == RULE_HEADER), None,
        )
        if header_row is None:
            continue
        for r in range(header_row + 2, ws.max_row + 1):
            mark = ws.cell(r, 2).value
            if isinstance(mark, str) and mark.strip().startswith("@"):
                raw.append({
                    "sheet": name,
                    "target": str(ws.cell(r, 1).value).strip().replace("$", ""),
                    "mark": mark.strip(),
                    "text": str(ws.cell(r, 3).value or "").strip(),
                })
    return raw


def _cell_ref(row: int, col: int) -> str:
    return f"{get_column_letter(col)}{row}"


def build_model(
    wb_fx, wb_val, codes: dict[str, list[str]], code_key,
    extra_formulas: dict[tuple[str, str], str] | None = None,
) -> tuple[dict, ParsedRules]:
    """返回 (模型 dict, 解析后的规则)。``codes``：编号 → [sheet 名]；``extra_formulas``：(sheet, 格) → 替换样表原值的公式。"""
    code_sheets = [s for names in codes.values() for s in names]
    bounds = {s: print_bounds(wb_fx[s]) for s in code_sheets}

    def in_print(sheet: str, row: int, col: int) -> bool:
        b = bounds.get(sheet)
        return bool(b) and b[0] <= row <= b[2] and b[1] <= col <= b[3]

    def cell_text(sheet: str, ref: str) -> str | None:
        v = wb_val[sheet][ref].value
        return str(v).strip() if v not in (None, "") else None

    def column_texts(sheet: str, col: str) -> list[str]:
        r1, _, r2, _ = bounds[sheet]
        out = []
        for r in range(r1, r2 + 1):
            v = wb_val[sheet][f"{col}{r}"].value
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        return out

    def resolve_sheet(code: str) -> str | None:
        key = code_key(code)
        for c, names in codes.items():
            if code_key(c) == key:
                return names[0]
        return next((s for s in wb_fx.sheetnames if code_key(s) == key), None)

    rules = RuleParser(cell_text, column_texts, resolve_sheet).parse_all(collect_raw_rules(wb_fx, code_sheets))
    rule_keys = {(i["sheet"], i["ref"]) for i in rules.items}
    injected = {(s, ref): f for s, ref, f in rules.formulas}
    injected.update(extra_formulas or {})

    # 种子：编号 sheet 打印区内全部非空格 + 取数目标格 + 注入公式
    cells: dict[str, dict[str, object]] = {}
    pending: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for sheet in code_sheets:
        r1, c1, r2, c2 = bounds[sheet]
        for row in wb_fx[sheet].iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2):
            for c in row:
                if c.value is not None:
                    pending.append((sheet, c.row, c.column))
    for sheet, ref in list(rule_keys) + list(injected):
        col_letters, row = coordinate_from_string(ref)
        pending.append((sheet, row, column_index_from_string(col_letters)))

    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        sheet, row, col = key
        if sheet not in wb_fx.sheetnames:
            continue
        ref = _cell_ref(row, col)
        if (sheet, ref) in rule_keys:
            cells.setdefault(sheet, {})[ref] = None  # 值由取数给出
            continue
        formula = injected.get((sheet, ref)) or formula_text(wb_fx[sheet].cell(row, col))
        if formula is None:
            value = constant_json(wb_fx[sheet].cell(row, col).value)
            if value is not None:
                cells.setdefault(sheet, {})[ref] = value
            continue
        cells.setdefault(sheet, {})[ref] = {"f": formula}
        try:
            ast = parse_formula(formula, sheet)
        except FormulaSyntaxError as exc:
            raise SystemExit(f"{sheet}!{ref} 公式无法解析：{formula}（{exc}）") from exc
        for _, ref_sheet, r1, c1, r2, c2 in iter_refs(ast):
            if ref_sheet not in wb_fx.sheetnames:
                raise SystemExit(f"{sheet}!{ref} 引用了不存在的 sheet {ref_sheet!r}")
            ws_ref = wb_fx[ref_sheet]
            for rr in range(r1, min(r2, ws_ref.max_row) + 1):
                for cc in range(c1, min(c2, ws_ref.max_column) + 1):
                    if (ref_sheet, rr, cc) not in seen:
                        pending.append((ref_sheet, rr, cc))

    params = []
    ws_params = wb_fx[PARAMS_SHEET]
    options = {}
    for dv in ws_params.data_validations.dataValidation:
        if dv.type == "list" and dv.formula1:
            values = [v.strip() for v in dv.formula1.strip('"').split(",") if v.strip()]
            for ref in str(dv.sqref).split():
                options[ref] = values
    for r in range(1, 16):
        label = ws_params.cell(r, 1).value
        if not label:
            continue
        ref = f"B{r}"
        params.append({
            "ref": ref,
            "label": str(label).strip(),
            "default": PARAM_DEFAULTS.get(ref),
            "options": options.get(ref, []),
            "sample": constant_json(wb_val[PARAMS_SHEET][ref].value),
        })
        # 参数页 B 列的值由参数（项目默认 + 手工）给出，不用样表示例
        cells.setdefault(PARAMS_SHEET, {})[ref] = None

    # 取数目标格、参数格不存值（运行时给出），只保留有值的格
    sheets = {}
    functions = set()
    for name in sorted(cells, key=wb_fx.sheetnames.index):
        b = bounds.get(name)
        kept = {k: v for k, v in sorted(cells[name].items(), key=lambda kv: _sort_ref(kv[0])) if v is not None}
        for v in kept.values():
            if isinstance(v, dict):
                functions.update(iter_functions(parse_formula(v["f"], name)))
        sheets[name] = {"print": list(b) if b else None, "cells": kept}
    model = {
        "version": 1,
        "codes": codes,
        "params_sheet": PARAMS_SHEET,
        "params": params,
        "functions": sorted(functions),
        "corrections": rules.corrections,
        "lists": rules.lists,
        "rules": sorted(rules.items, key=lambda i: (wb_fx.sheetnames.index(i["sheet"]), _sort_ref(i["ref"]))),
        "sheets": sheets,
    }
    return model, rules


def _sort_ref(ref: str) -> tuple[int, str]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (int(m.group(2)), m.group(1).rjust(3)) if m else (0, ref)
