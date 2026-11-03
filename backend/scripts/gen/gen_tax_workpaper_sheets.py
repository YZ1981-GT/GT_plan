"""税务底稿样表 → 前端单表显示结构（每张表一个 JSON）+ 后端计算模型。

事实来源：税审底稿样表 xlsx（如「税审底稿10.16.xlsx」，不入库，经 --src 或环境变量
GT_TAX_WORKPAPER_XLSX 指定）。目录与编号以前端 taxWorkpaperIndex.ts 为准。

前端 ``sheets/<编号>.json``（显示结构）：
- 范围：sheet 的打印区域（区域外是取数规则、状态辅助格，不属于底稿本身）；跳过隐藏行列。
- 值：常量照原表；公式格、取数格不带文字，带 ``ref``（单元格地址）由后端接口给值；
  ``role``：f 公式（只读）/ e 可填写；``fmt``：pct / money / int。
- 呈现类型只影响样式，规则见 classify_rows。

后端 ``backend/data/tax_workpaper_model.json``（计算模型，见 tax_workpaper_model.py）：
全部公式、常量、结构化取数规则（tax_workpaper_rules.py 解析 202 条中文规则）、参数页。

用法：
  python backend/scripts/gen/gen_tax_workpaper_sheets.py --src <样表.xlsx>          # 生成
  python backend/scripts/gen/gen_tax_workpaper_sheets.py --src <样表.xlsx> --check  # 漂移检查，有差异 exit 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import range_boundaries

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tax_workpaper_model import build_model  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FRONT_DIR = ROOT / "audit-platform" / "frontend" / "src" / "views" / "tax-workpapers"
INDEX_TS = FRONT_DIR / "taxWorkpaperIndex.ts"
OUT_DIR = FRONT_DIR / "sheets"
MODEL_PATH = ROOT / "backend" / "data" / "tax_workpaper_model.json"

# 一个编号对应多张 sheet 的特例：(sheet 名, 分段标题)
MULTI_PART = {
    "1-01": [("1-01报告封面", "报告封面"), ("1-01报告正文", "报告正文")],
}

META_RE = re.compile(r"索引号|金额单位")
TOTAL_RE = re.compile(r"^(合计|小计|总计)")
NUMERIC_FMT_RE = re.compile(r"[0#]")


def read_index_codes() -> list[str]:
    text = INDEX_TS.read_text(encoding="utf-8")
    return re.findall(r"code:\s*'([^']+)'", text)


def code_key(raw: str) -> str:
    """编号归一：全角括号转半角、去尾部中文与空白、数字段去前导零（2-3-1 与 2-03-1 视为同号）。"""
    s = raw.replace("（", "(").replace("）", ")")
    s = re.sub(r"[\u4e00-\u9fff].*$", "", s)
    s = re.sub(r"\s+", "", s)
    return re.sub(r"\d+", lambda m: str(int(m.group())), s)


def clean_text(value: str) -> str:
    s = value.replace("_x000D_", "").replace("\r\n", "\n").replace("\r", "\n")
    # 样表用前导空格做对齐，网页里会变成缩进，首尾空白一律去掉（中间的保留）
    return s.strip(" \t\n\u3000")


def leading_literal(formula: str) -> str:
    """="文字"&... 取前导文字；其余公式无可显示文字。"""
    m = re.match(r'^="((?:[^"]|"")*)"\s*&', formula)
    return m.group(1).replace('""', '"') if m else ""


def is_numeric_format(fmt: str | None) -> bool:
    return bool(fmt) and fmt not in ("@", "General") and bool(NUMERIC_FMT_RE.search(fmt))


def format_number(value: float | int, fmt: str) -> str:
    if "%" in fmt:
        digits = len(fmt.split(".")[1].split("%")[0]) if "." in fmt else 0
        return f"{value * 100:.{digits}f}%"
    decimals = 2 if ".00" in fmt or (isinstance(value, float) and not value.is_integer()) else 0
    grouping = "," if "," in fmt else ""
    return f"{value:{grouping}.{decimals}f}"


def print_bounds(ws) -> tuple[int, int, int, int]:
    area = ws.print_area
    if area:
        first = area.split(",")[0].split("!")[-1].replace("$", "")
        min_col, min_row, max_col, max_row = range_boundaries(first)
        return min_row, min_col, max_row, max_col
    return 1, 1, ws.max_row, ws.max_column


def value_format(fmt: str | None) -> str | None:
    """数值格显示口径：pct 百分比 / money 两位小数千分位 / int 整数；其余前端按默认显示。"""
    if not is_numeric_format(fmt):
        return None
    if "%" in fmt:
        return "pct"
    if ".0" in fmt:
        return "money"
    return "int"


def convert_sheet(ws_val, ws_fx, model_sheet: dict | None = None, rule_refs: dict[str, str] | None = None) -> list[list[dict]]:
    """``model_sheet``：计算模型里本 sheet 的 cells（判公式格）；``rule_refs``：本 sheet 取数目标格 → op。"""
    model_cells = (model_sheet or {}).get("cells", {})
    rule_ops = rule_refs or {}
    rule_refs = set(rule_ops)
    min_row, min_col, max_row, max_col = print_bounds(ws_val)
    rows_idx = [r for r in range(min_row, max_row + 1) if not ws_val.row_dimensions[r].hidden]
    cols_idx = [
        c for c in range(min_col, max_col + 1)
        if not ws_val.column_dimensions[openpyxl.utils.get_column_letter(c)].hidden
    ]
    row_pos = {r: i for i, r in enumerate(rows_idx)}
    col_pos = {c: i for i, c in enumerate(cols_idx)}

    # 合并区域：可见左上角记 (行跨度, 列跨度, 原左上角)，其余格子被吞掉。
    # 原左上角可能落在打印区或隐藏行列之外，值与样式仍取原左上角。
    spans: dict[tuple[int, int], tuple[int, int, tuple[int, int]]] = {}
    covered: set[tuple[int, int]] = set()
    for rng in ws_val.merged_cells.ranges:
        vis_rows = [r for r in range(rng.min_row, rng.max_row + 1) if r in row_pos]
        vis_cols = [c for c in range(rng.min_col, rng.max_col + 1) if c in col_pos]
        if not vis_rows or not vis_cols:
            continue
        anchor = (vis_rows[0], vis_cols[0])
        spans[anchor] = (len(vis_rows), len(vis_cols), (rng.min_row, rng.min_col))
        for r in vis_rows:
            for c in vis_cols:
                if (r, c) != anchor:
                    covered.add((r, c))

    grid: list[list[dict]] = []
    for r in rows_idx:
        row_cells: list[dict] = []
        for c in cols_idx:
            if (r, c) in covered:
                continue
            span = spans.get((r, c))
            src_r, src_c = span[2] if span else (r, c)
            src_cell = ws_val.cell(src_r, src_c)
            info = describe_cell(src_cell, ws_fx.cell(src_r, src_c).value)
            ref = f"{openpyxl.utils.get_column_letter(src_c)}{src_r}"
            raw = model_cells.get(ref)
            if ref in rule_refs:
                info["_ref"], info["_role"] = ref, "e"
                info.pop("text", None)  # 值由后端取数给出
            elif isinstance(raw, dict) and "f" in raw:
                info["_ref"], info["_role"] = ref, "f"
                info.pop("text", None)  # 值由后端计算给出（含 ="文字"&... 的前导文字）
            elif info.get("text") is None and info["_border"] and not info["_formula"]:
                info["_ref"], info["_role"] = ref, "e"
            fmt = value_format(src_cell.number_format)
            # 取数的金额格样表常没设数字格式：除名称列外按金额显示
            if not fmt and ref in rule_refs and rule_ops.get(ref) != "list_name":
                fmt = "money"
            if info.get("_ref") and fmt:
                info["_fmt"] = fmt
            if span and span[0] > 1:
                info["rowSpan"] = span[0]
            if span and span[1] > 1:
                info["colSpan"] = span[1]
            row_cells.append(info)
        grid.append(row_cells)
    classify_rows(grid, len(cols_idx))
    for row in grid:
        for cell in row:
            # 表名、索引号、表头这类格子不可填写
            if cell.get("_role") == "e" and cell.get("kind") in ("title", "meta", "header") and cell["_ref"] not in rule_refs:
                del cell["_ref"], cell["_role"]
                cell.pop("_fmt", None)
    return [[strip_private(c) for c in row] for row in grid]


def describe_cell(cell, fx) -> dict:
    """单元格 → 中间态（带下划线的键只给分类用，输出前剔除）。"""
    value = cell.value
    fmt = cell.number_format
    is_formula = isinstance(fx, str) and fx.startswith("=") and fx != value
    info: dict = {
        "_bold": bool(cell.font and cell.font.bold),
        "_size": float(cell.font.sz or 0) if cell.font else 0.0,
        "_center": bool(cell.alignment and cell.alignment.horizontal in ("center", "centerContinuous")),
        "_numeric": False,
        "_formula": is_formula,
        "_border": bool(cell.border and (cell.border.left.style or cell.border.bottom.style)),
        "_empty_num_fmt": False,
    }
    text = ""
    if is_formula:
        text = leading_literal(fx)
        info["_numeric"] = is_numeric_format(fmt) and not text
    elif isinstance(value, bool):
        text = "是" if value else "否"
    elif isinstance(value, (int, float)):
        text = format_number(value, fmt) if is_numeric_format(fmt) else (
            str(int(value)) if float(value).is_integer() else str(value)
        )
        info["_numeric"] = True
    elif isinstance(value, (dt.datetime, dt.date)):
        text = value.strftime("%Y-%m-%d")
    elif isinstance(value, str):
        text = clean_text(value)
    elif value is None:
        info["_empty_num_fmt"] = is_numeric_format(fmt)
    if text.strip():
        info["text"] = text
    return info


def classify_rows(grid: list[list[dict]], width: int) -> None:
    """呈现类型：title 表名 / meta 索引号、金额单位 / header 表头 / number 数值 / total 合计 / input 待填。"""
    for i, row in enumerate(grid):
        texts = [c for c in row if c.get("text")]
        first_label = next((c["text"] for c in row if c.get("text") and not c["_numeric"]), "")
        is_total = bool(TOTAL_RE.match(re.sub(r"\s+", "", first_label)))
        has_formula_or_num = any(c["_formula"] or c["_numeric"] for c in row)
        centered_texts = [c for c in texts if c["_center"]]
        is_header = (
            not has_formula_or_num
            and not is_total
            and texts
            and len(centered_texts) == len(texts)
            and (len(texts) >= 2 or texts[0].get("colSpan", 1) * 2 >= width)
        )
        for c in row:
            text = c.get("text", "")
            if text and META_RE.search(text):
                c["kind"] = "meta"
            elif text and i < 3 and c["_bold"] and (c.get("colSpan", 1) * 2 >= width or c["_size"] >= 12):
                c["kind"] = "title"
            elif c["_numeric"]:
                c["kind"] = "number"
            elif is_total and text:
                c["kind"] = "total"
            elif is_header and text:
                c["kind"] = "header"
            elif not text and c["_empty_num_fmt"] and c["_border"]:
                c["kind"] = "input"


def strip_private(cell: dict) -> dict:
    out = {k: cell[k] for k in ("text", "kind", "colSpan", "rowSpan") if k in cell}
    for key in ("ref", "role", "fmt"):
        if f"_{key}" in cell:
            out[key] = cell[f"_{key}"]
    return out


def render_json(code: str, parts: list[dict]) -> str:
    """一行一行写，样表更新时 diff 能看出改了哪一行。"""
    lines = ["{", f'  "code": {json.dumps(code, ensure_ascii=False)},', '  "parts": [']
    for pi, part in enumerate(parts):
        lines.append("    {")
        if part.get("title"):
            lines.append(f'      "title": {json.dumps(part["title"], ensure_ascii=False)},')
        lines.append(f'      "source": {json.dumps(part["source"], ensure_ascii=False)},')
        lines.append('      "rows": [')
        rows = part["rows"]
        for ri, row in enumerate(rows):
            sep = "," if ri < len(rows) - 1 else ""
            lines.append("        " + json.dumps(row, ensure_ascii=False, separators=(",", ":")) + sep)
        lines.append("      ]")
        lines.append("    }" + ("," if pi < len(parts) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def file_name(code: str) -> str:
    return f"{code}.json"


def render_model(model: dict) -> str:
    """计算模型：顶层键各占一行、sheets / rules 每项一行，样表更新时 diff 可读。"""
    dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    lines = ["{"]
    keys = list(model)
    for i, key in enumerate(keys):
        sep = "," if i < len(keys) - 1 else ""
        value = model[key]
        if key == "sheets":
            lines.append(f'  "sheets": {{')
            names = list(value)
            for j, name in enumerate(names):
                lines.append(f"    {dump(name)}: {dump(value[name])}" + ("," if j < len(names) - 1 else ""))
            lines.append("  }" + sep)
        elif key in ("rules", "params", "corrections") and value:
            lines.append(f"  {dump(key)}: [")
            for j, item in enumerate(value):
                lines.append(f"    {dump(item)}" + ("," if j < len(value) - 1 else ""))
            lines.append("  ]" + sep)
        elif key == "lists" and value:
            lines.append('  "lists": {')
            ids = list(value)
            for j, list_id in enumerate(ids):
                lines.append(f"    {dump(list_id)}: {dump(value[list_id])}" + ("," if j < len(ids) - 1 else ""))
            lines.append("  }" + sep)
        else:
            lines.append(f"  {dump(key)}: {dump(value)}{sep}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build(src: Path) -> tuple[dict[str, str], str, dict]:
    """返回 (前端 sheets/*.json 文件名 → 内容, 计算模型 JSON 文本, 模型 dict)。"""
    wb_val = openpyxl.load_workbook(src, data_only=True)
    wb_fx = openpyxl.load_workbook(src, data_only=False)

    by_key: dict[str, list[str]] = {}
    for name in wb_val.sheetnames:
        by_key.setdefault(code_key(name), []).append(name)

    # 编号 → sheet
    codes: dict[str, list[tuple[str, str | None]]] = {}
    errors: list[str] = []
    for code in read_index_codes():
        if code in MULTI_PART:
            sources = MULTI_PART[code]
        else:
            matches = by_key.get(code_key(code), [])
            if len(matches) != 1:
                errors.append(f"{code}: 样表中匹配到 {len(matches)} 张 sheet {matches}")
                continue
            sources = [(matches[0], None)]
        missing = [s for s, _ in sources if s not in wb_val.sheetnames]
        if missing:
            errors.append(f"{code}: 样表中没有 sheet {missing}")
            continue
        codes[code] = sources
    if errors:
        raise SystemExit("编号与样表对不上：\n  " + "\n  ".join(errors))

    model, rules = build_model(wb_fx, wb_val, {c: [s for s, _ in v] for c, v in codes.items()}, code_key)
    rule_refs: dict[str, dict[str, str]] = {}
    for item in rules.items:
        rule_refs.setdefault(item["sheet"], {})[item["ref"]] = item["op"]

    outputs: dict[str, str] = {}
    for code, sources in codes.items():
        parts = []
        for sheet_name, title in sources:
            rows = convert_sheet(wb_val[sheet_name], wb_fx[sheet_name], model["sheets"].get(sheet_name), rule_refs.get(sheet_name))
            # source 用模型里的 sheet 名原样（含尾部空格），前端按它对接口返回的值
            part = {"source": sheet_name, "rows": rows}
            if title:
                part["title"] = title
            parts.append(part)
        outputs[file_name(code)] = render_json(code, parts)
    return outputs, render_model(model), model


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", default=os.environ.get("GT_TAX_WORKPAPER_XLSX"), help="税审底稿样表 xlsx")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件；有差异 exit 2")
    args = parser.parse_args()
    if not args.src:
        parser.error("需要 --src 或环境变量 GT_TAX_WORKPAPER_XLSX")
    src = Path(args.src)
    if not src.is_file():
        parser.error(f"样表不存在：{src}")

    outputs, model_text, model = build(src)
    existing = {p.name: p.read_text(encoding="utf-8") for p in OUT_DIR.glob("*.json")} if OUT_DIR.is_dir() else {}
    changed = sorted(n for n, t in outputs.items() if existing.get(n) != t)
    stale = sorted(set(existing) - set(outputs))
    model_changed = (MODEL_PATH.read_text(encoding="utf-8") if MODEL_PATH.is_file() else None) != model_text
    summary = (
        f"{len(outputs)} 张表；计算模型 {len(model['sheets'])} 个 sheet、取数项 {len(model['rules'])} 个、"
        f"列表 {len(model['lists'])} 个、纠正 {len(model['corrections'])} 条"
    )

    if args.check:
        if changed or stale or model_changed:
            print(f"[DRIFT] 表差异 {len(changed)} 个，多余 {len(stale)} 个，模型{'有' if model_changed else '无'}差异：{(changed + stale)[:10]}")
            return 2
        print(f"[OK] {summary}，与样表一致")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in changed:
        (OUT_DIR / name).write_text(outputs[name], encoding="utf-8", newline="\n")
    for name in stale:
        (OUT_DIR / name).unlink()
    if model_changed:
        MODEL_PATH.write_text(model_text, encoding="utf-8", newline="\n")
    print(f"[WRITE] {summary}；写入表 {len(changed)}，删除 {len(stale)}，模型{'已更新' if model_changed else '未变'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
