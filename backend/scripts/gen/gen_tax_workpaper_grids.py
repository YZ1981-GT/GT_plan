"""税审底稿 / 纳税申报表样表 → 前端 Univer 工作表数据。

产物：
- 底稿：`src/constants/taxWorkpaperGrids/<编号>.json`，每张底稿一个文件；
- 纳税申报表：`src/constants/taxReturnGrid.json`，2025 工作簿「申报表封面」~「行业数据报送明细表」
  全部进同一个工作簿，申报表之间的公式（A100000 引 A101010 等）保留、由 Univer 计算。

范围：`src/constants/taxWorkpaperIndex.ts` 里的全部编号（索引是唯一清单，本脚本不另列）。
来源（两本工作簿，按编号分工）：
- 「一、综合类」1-xx：`CITRv1.0工作底稿-六部提供案例（解密）.xlsx`
- 其余各类：`2025底稿-5.23-5.25补充高新-5.29（解密版）.xlsx`
编号 → 工作表：默认按工作表名等于编号匹配（全角括号、尾随空格视同一致）；
工作簿里表名与编号对不上的，登记在 `OVERRIDES`（已逐张按表内标题核对过）。
任何编号找不到工作表即报错退出，不静默跳过。

转写口径：
- 保留值、合并、行高 / 列宽、隐藏行列、字体（字号 / 粗斜体 / 下划线 / 颜色）、
  对齐与自动换行、边框、纯色填充。
- 本表内公式（`=SUM(B9:E9)/2`）原样保留，交给 Univer 计算。
- **跨表公式**（引用「填写参数」「索引」、申报表等其他工作表）Univer 里没有那些表，
  算出来只会是 #REF!；缓存值又是案例企业（ABC 餐饮）的数据，带进每个项目会误导。
  ⇒ 置空，只保留公式里打头的字面文字（`="业务委托书编号:"&…` → `业务委托书编号:`），
  将来接项目数据时再按单元格补取数。
- BA 列等远端辅助列（`=索引!E6` 之类）随跨表公式一并丢弃；表的范围按有内容的单元格算。

用法：
    python backend/scripts/gen/gen_tax_workpaper_grids.py          # 生成
    python backend/scripts/gen/gen_tax_workpaper_grids.py --check  # 只比对，产物过期则 exit 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "audit-platform" / "frontend"
SOURCES = {
    "case": FRONTEND / "CITRv1.0工作底稿-六部提供案例（解密）.xlsx",
    "y2025": FRONTEND / "2025底稿-5.23-5.25补充高新-5.29（解密版）.xlsx",
}
INDEX_FILE = FRONTEND / "src" / "constants" / "taxWorkpaperIndex.ts"
TARGET_DIR = FRONTEND / "src" / "constants" / "taxWorkpaperGrids"
RETURN_TARGET = FRONTEND / "src" / "constants" / "taxReturnGrid.json"
# 纳税申报表 = 2025 工作簿里「申报表封面」到「行业数据报送明细表」这一段（含首尾），按工作簿顺序成页签。
RETURN_FIRST, RETURN_LAST = "申报表封面", "行业数据报送明细表"

# 工作表名与索引编号对不上的，显式登记（编号 → 工作表，一个编号可多张表 = 底稿的多个页签）。
# 2-15 ~ 2-18：工作簿里的编号比索引错后一位（表「2-15」是「审核表（其他损益类科目）」，
# 索引的 2-15 制造费用明细在表「2-16制造费用」）—— 按表内标题对齐，以索引为准。
OVERRIDES: dict[str, list[str]] = {
    "1-01": ["1-01报告封面", "1-01报告正文"],
    "2-03-1": ["2-3-1 其他收益"],
    "2-03-2": ["2-3-2 资产处置收益"],
    "2-15": ["2-16制造费用"],
    "2-16": ["2-17生产成本"],
    "2-17": ["2-18在建工程"],
    "2-18": ["2-19其他成本1"],
    "3-02-10-2": ["3-02-10-2 保险企业佣金和手续费鉴证表"],
}


def source_of(code: str) -> str:
    return "case" if code.startswith("1-") else "y2025"


def index_codes() -> list[str]:
    text = INDEX_FILE.read_bytes().decode("utf-8")
    codes = re.findall(r"\{ code: '([^']+)', name: '[^']+' \}", text)
    if not codes:
        raise SystemExit(f"[ERROR] 从 {INDEX_FILE.name} 读不到任何编号")
    return codes


def _norm_sheet_name(name: str) -> str:
    return name.strip().replace("（", "(").replace("）", ")")


def resolve_sheets(code: str, sheet_names: list[str]) -> list[str]:
    if code in OVERRIDES:
        missing = [n for n in OVERRIDES[code] if n not in sheet_names]
        if missing:
            raise SystemExit(f"[ERROR] {code}: OVERRIDES 登记的工作表不存在 {missing}")
        return OVERRIDES[code]
    hits = [n for n in sheet_names if _norm_sheet_name(n) == code]
    if len(hits) != 1:
        raise SystemExit(f"[ERROR] {code}: 按编号匹配到 {len(hits)} 张工作表 {hits}，请在 OVERRIDES 登记")
    return hits

# AZ / BA 两列是「索引」页用的辅助列（AZ1 填报状态「已完成 / 未填报」、BA1 `=索引!E…`），
# 不属于表样 ⇒ 从 AZ 列（0 起第 51 列）往右整列不转写。
HELPER_COL_START = 51

MIN_ROWS = 100
MIN_COLS = 26
DEFAULT_COL_WIDTH_CHARS = 8.43

_BORDER = {
    "thin": 1, "hair": 2, "dotted": 3, "dashed": 4, "dashDot": 5, "dashDotDot": 6,
    "double": 7, "medium": 8, "mediumDashed": 9, "mediumDashDot": 10,
    "mediumDashDotDot": 11, "slantDashDot": 12, "thick": 13,
}
_H_ALIGN = {"left": 1, "center": 2, "centerContinuous": 2, "right": 3, "justify": 4, "distributed": 6}
_V_ALIGN = {"top": 1, "center": 2, "bottom": 3}


def _rgb(color) -> str | None:
    """openpyxl 颜色 → #RRGGBB；主题色 / 索引色无法离线还原，返回 None（用默认色）。"""
    if color is None or getattr(color, "type", None) != "rgb":
        return None
    v = color.rgb
    if not isinstance(v, str) or len(v) != 8:
        return None
    return f"#{v[2:]}"


_SHEET_REF = re.compile(r"(?:'((?:[^']|'')+)'|([^\s'!=+\-*/^&,;:()<>{}\"]+))!")


def _cross_sheet(formula: str, allowed: frozenset[str] = frozenset()) -> bool:
    """公式是否引用了 `allowed` 之外的工作表（剔掉双引号字符串后找「表名!」）。

    `allowed` 是同一份产物里一起交给 Univer 的工作表（申报表各表互相引用），
    这些引用 Univer 算得出来，保留；其余工作表不在产物里，引用只会是 #REF!。
    """
    body = re.sub(r'"[^"]*"', "", formula)
    if "!" not in body:
        return False
    refs = [(q or b).replace("''", "'") for q, b in _SHEET_REF.findall(body)]
    # 认不出表名（「!」出现了却没解析到引用）一律当外部引用，宁可置空不留 #REF!
    return not refs or any(r not in allowed for r in refs)


def _leading_literal(formula: str) -> str:
    """`="业务委托书编号:"&'参数'!B19` → `业务委托书编号:`；不以字符串开头返回空串。"""
    m = re.match(r'^=\s*"((?:[^"]|"")*)"\s*&', formula)
    return m.group(1).replace('""', '"') if m else ""


def _clean_text(v: str) -> str:
    return v.replace("_x000D_", "").replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _style(cell: Cell) -> dict:
    s: dict = {}
    f = cell.font
    if f is not None:
        if f.name:
            s["ff"] = f.name
        if f.sz:
            s["fs"] = float(f.sz)
        if f.b:
            s["bl"] = 1
        if f.i:
            s["it"] = 1
        if f.u and f.u != "none":
            s["ul"] = {"s": 1}
        c = _rgb(f.color)
        if c and c.upper() != "#000000":
            s["cl"] = {"rgb": c}
    fill = cell.fill
    if fill is not None and fill.fill_type == "solid":
        c = _rgb(fill.fgColor)
        if c and c.upper() != "#FFFFFF":
            s["bg"] = {"rgb": c}
    a = cell.alignment
    if a is not None:
        if a.horizontal in _H_ALIGN:
            s["ht"] = _H_ALIGN[a.horizontal]
        if a.vertical in _V_ALIGN:
            s["vt"] = _V_ALIGN[a.vertical]
        if a.wrap_text:
            s["tb"] = 3  # WrapStrategy.WRAP
    bd: dict = {}
    for side, key in (("top", "t"), ("bottom", "b"), ("left", "l"), ("right", "r")):
        edge = getattr(cell.border, side, None)
        if edge is not None and edge.style in _BORDER:
            bd[key] = {"s": _BORDER[edge.style], "cl": {"rgb": _rgb(edge.color) or "#000000"}}
    if bd:
        s["bd"] = bd
    return s


def convert_sheet(
    ws, styles: dict[str, dict], style_ids: dict[str, str], allowed: frozenset[str] = frozenset(),
) -> tuple[dict, int]:
    """返回（Univer 工作表片段, 被置空的跨表公式数）。"""
    cells: dict[int, dict[int, dict]] = {}
    blanked = 0
    max_r = max_c = 0

    def style_id(cell: Cell) -> str | None:
        s = _style(cell)
        if not s:
            return None
        key = json.dumps(s, sort_keys=True, ensure_ascii=False)
        if key not in style_ids:
            sid = f"s{len(style_ids)}"
            style_ids[key] = sid
            styles[sid] = s
        return style_ids[key]

    for row in ws.iter_rows(max_col=HELPER_COL_START):
        for cell in row:
            v = cell.value
            entry: dict = {}
            if isinstance(v, str) and v.startswith("="):
                if _cross_sheet(v, allowed):
                    blanked += 1
                    lit = _leading_literal(v)
                    if lit:
                        entry["v"] = _clean_text(lit)
                else:
                    entry["f"] = v
            elif isinstance(v, (dt.datetime, dt.date)):
                entry["v"] = v.strftime("%Y-%m-%d")
            elif isinstance(v, bool):
                entry["v"] = "TRUE" if v else "FALSE"
            elif isinstance(v, (int, float)):
                entry["v"] = v
            elif isinstance(v, str) and _clean_text(v):
                entry["v"] = _clean_text(v)
            has_value = bool(entry)
            sid = style_id(cell)
            if sid:
                entry["s"] = sid
            if not entry:
                continue
            r, c = cell.row - 1, cell.column - 1
            cells.setdefault(r, {})[c] = entry
            if has_value:
                max_r, max_c = max(max_r, r + 1), max(max_c, c + 1)

    merges = []
    for m in ws.merged_cells.ranges:
        r1, c1, r2, c2 = m.min_row - 1, m.min_col - 1, m.max_row - 1, m.max_col - 1
        if r1 < max_r and c1 < max_c:
            merges.append({"startRow": r1, "endRow": r2, "startColumn": c1, "endColumn": c2})
            max_r, max_c = max(max_r, r2 + 1), max(max_c, c2 + 1)
    merges.sort(key=lambda x: (x["startRow"], x["startColumn"]))

    # 只保留表范围内的单元格（远端辅助列只有边框样式时也丢掉）
    cells = {r: {c: e for c, e in cols.items() if c < max_c} for r, cols in cells.items() if r < max_r}
    cells = {r: cols for r, cols in cells.items() if cols}

    default_h = ws.sheet_format.defaultRowHeight or 15
    row_data: dict[int, dict] = {}
    for i in range(1, max_r + 1):
        d = ws.row_dimensions.get(i)
        if d is None:
            continue
        item: dict = {}
        if d.height:
            item["h"] = round(d.height * 4 / 3)
        if d.hidden:
            item["hd"] = 1
        if item:
            row_data[i - 1] = item
    col_data: dict[int, dict] = {}
    for i in range(1, max_c + 1):
        d = ws.column_dimensions.get(get_column_letter(i))
        width = d.width if d is not None and d.width else DEFAULT_COL_WIDTH_CHARS
        item = {"w": round(width * 7 + 5)}
        if d is not None and d.hidden:
            item["hd"] = 1
        col_data[i - 1] = item

    sheet = {
        "rowCount": max(MIN_ROWS, max_r + 20),
        "columnCount": max(MIN_COLS, max_c),
        "defaultRowHeight": round(default_h * 4 / 3),
        "cellData": cells,
        "mergeData": merges,
        "rowData": row_data,
        "columnData": col_data,
    }
    return sheet, blanked


def return_sheet_names(sheet_names: list[str]) -> list[str]:
    try:
        a, b = sheet_names.index(RETURN_FIRST), sheet_names.index(RETURN_LAST)
    except ValueError as e:
        raise SystemExit(f"[ERROR] 申报表首尾工作表不存在：{e}")
    return sheet_names[a:b + 1]


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def build() -> tuple[dict[Path, str], list[str]]:
    """返回（产物路径 → 内容, 报告行）。

    - 底稿：每张一个 JSON，样式表随文件自带。
    - 纳税申报表：一个 JSON，全部申报表进同一个 Univer 工作簿（表间公式保留可算）。
    """
    books = {k: load_workbook(v, data_only=False) for k, v in SOURCES.items()}
    files: dict[Path, str] = {}
    report: list[str] = []
    for code in index_codes():
        wb = books[source_of(code)]
        styles: dict[str, dict] = {}
        style_ids: dict[str, str] = {}
        sheets = []
        for name in resolve_sheets(code, wb.sheetnames):
            data, blanked = convert_sheet(wb[name], styles, style_ids)
            tab = code if _norm_sheet_name(name) == code else name.strip()
            sheets.append({"name": tab, **data})
            n_cells = sum(len(v) for v in data["cellData"].values())
            report.append(
                f"{code} <- {source_of(code)}[{name.strip()}] cells={n_cells} "
                f"merges={len(data['mergeData'])} cross_sheet_blanked={blanked}"
            )
        files[TARGET_DIR / f"{code}.json"] = _dump({"styles": styles, "sheets": sheets})

    wb = books["y2025"]
    names = return_sheet_names(wb.sheetnames)
    allowed = frozenset(names)
    styles, style_ids, sheets = {}, {}, []
    for name in names:
        data, blanked = convert_sheet(wb[name], styles, style_ids, allowed)
        sheets.append({"name": name, **data})
        n_cells = sum(len(v) for v in data["cellData"].values())
        report.append(f"RETURN [{name}] cells={n_cells} merges={len(data['mergeData'])} external_blanked={blanked}")
    files[RETURN_TARGET] = _dump({"styles": styles, "sheets": sheets})
    return files, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只比对，产物与源工作簿不一致时 exit 2")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    files, report = build()
    stale = [p for p, text in files.items()
             if not p.exists() or p.read_bytes().decode("utf-8") != text]
    existing = set(TARGET_DIR.glob("*.json")) if TARGET_DIR.exists() else set()
    extra = sorted(existing - set(files))
    if args.check:
        if stale or extra:
            print(f"[STALE] 过期 {len(stale)} 个、多余 {len(extra)} 个，请重新生成")
            for p in (stale + extra)[:20]:
                print("   ", p.relative_to(ROOT))
            return 2
        print(f"[OK] {len(files)} 个产物与源工作簿一致")
        return 0
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for p in stale:
        p.write_bytes(files[p].encode("utf-8"))
    for p in extra:
        p.unlink()
    for line in report:
        print(line)
    total = sum(len(v.encode("utf-8")) for v in files.values())
    print(f"{len(files)} files, {total} bytes; updated {len(stale)}, removed {len(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
