"""表格类底稿（univer 类：F-审定表/F-明细表/G-测算 等）网格提取服务

从底稿 xlsx 模板读取单元格 + 合并区域 + 列宽 + **真实样式**（填充色/加粗/对齐/
字号/数字格式），构建只读 HTML 网格数据，供 GtGridSheet.vue 还原 Excel 外观。

动机（2026-06-02 修复）：混合底稿（含 HTML sheet + univer sheet，如 D1 同时有
A 程序表/B 目录/F 审定表）整本路由到 GtWpRenderer，但其 univer 分支只是一个
**死占位**「数据尚未导入」，模板里的审定表/明细表结构完全不显示。本服务让 univer
sheet 在 HTML 渲染器内也能显示模板网格内容（只读，且按 Excel 模板样式还原）。

样式还原（2026-06-02 用户要求按 Excel 模板样式）：提取真实 fill（rgb 直取 /
theme+tint 经 _resolve_theme_color 解析）+ bold + align + font_size + number_format，
不再用文字正则启发式（合计/小计等）。

纯函数无 DB 副作用，便于单测。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认 Office 主题配色（clrScheme XML 顺序：dk1 lt1 dk2 lt2 accent1..6 hlink folHlink）
_DEFAULT_SCHEME = [
    "000000", "FFFFFF", "1F497D", "EEECE1",
    "4F81BD", "C0504D", "9BBB59", "8064A2",
    "4BACC6", "F79646", "0000FF", "800080",
]

# openpyxl cell.fill.fgColor.theme 索引 → clrScheme XML 索引映射
# Excel 渲染层 theme：0=lt1 1=dk1 2=lt2 3=dk2 4=accent1…（lt1/dk1 相对 clrScheme 互换）
_THEME_TO_SCHEME = {0: 1, 1: 0, 2: 3, 3: 2, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9}


def _parse_scheme_from_workbook(wb: Any) -> list[str]:
    """从工作簿 theme XML 解析 clrScheme 12 色（失败回退默认 Office 配色）。"""
    import re

    try:
        raw = wb.loaded_theme
        if not raw:
            return _DEFAULT_SCHEME
        xml = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        m = re.search(r"<a:clrScheme.*?</a:clrScheme>", xml, re.S)
        if not m:
            return _DEFAULT_SCHEME
        colors = re.findall(
            r"<a:(?:srgbClr|sysClr)[^>]*?(?:val|lastClr)=\"([0-9A-Fa-f]{6})\"",
            m.group(0),
        )
        return colors if len(colors) >= 12 else _DEFAULT_SCHEME
    except Exception:
        return _DEFAULT_SCHEME


def _apply_tint(hex_rgb: str, tint: float) -> str:
    """对 6 位 hex 应用 Excel tint（>0 变亮，<0 变暗），返回 6 位 hex（不含 #）。"""
    try:
        r = int(hex_rgb[0:2], 16)
        g = int(hex_rgb[2:4], 16)
        b = int(hex_rgb[4:6], 16)
    except (ValueError, IndexError):
        return hex_rgb

    def _adj(c: int) -> int:
        if tint < 0:
            v = c * (1.0 + tint)
        else:
            v = c * (1.0 - tint) + 255.0 * tint
        return max(0, min(255, int(round(v))))

    return f"{_adj(r):02X}{_adj(g):02X}{_adj(b):02X}"


def _resolve_fill(cell: Any, scheme: list[str]) -> str | None:
    """解析单元格填充色 → '#RRGGBB'（无填充 / 解析失败 → None）。"""
    fill = cell.fill
    if not fill or not getattr(fill, "patternType", None):
        return None
    fg = fill.fgColor
    if fg is None:
        return None
    try:
        if fg.type == "rgb" and fg.rgb and isinstance(fg.rgb, str):
            # openpyxl rgb 形如 'FFE4DFEC'（前两位 alpha）
            rgb = fg.rgb[-6:]
            if rgb == "000000" and fill.patternType == "solid" and fg.rgb == "00000000":
                return None
            return f"#{rgb}"
        if fg.type == "theme":
            scheme_idx = _THEME_TO_SCHEME.get(int(fg.theme), int(fg.theme))
            if 0 <= scheme_idx < len(scheme):
                base = scheme[scheme_idx]
                return f"#{_apply_tint(base, float(fg.tint or 0.0))}"
    except Exception as e:
        logger.debug("解析填充色失败: %s", e)
        return None
    return None


def _resolve_font_color(cell: Any) -> str | None:
    """解析字体颜色 → '#RRGGBB'（仅 rgb 类型，其余返 None 用默认）。"""
    try:
        fc = cell.font.color
        if fc and fc.type == "rgb" and fc.rgb and isinstance(fc.rgb, str):
            rgb = fc.rgb[-6:]
            if rgb in ("000000", "FFFFFF"):
                # 黑白用默认（避免暗色主题下不可见）
                return None
            return f"#{rgb}"
    except Exception as e:
        logger.debug("解析字体色失败: %s", e)
    return None


def _cell_value(value: Any) -> Any:
    """规整单元格值：公式串(=开头)按公式处理由上层决定，这里只规整非公式标量。"""
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _is_accounting_format(numfmt: str | None) -> bool:
    """判断是否会计/数字格式（空值应显示「-」占位）。"""
    if not numfmt:
        return False
    return "#,##0" in numfmt or "0.00" in numfmt


def _col_letter(c: int) -> str:
    """列号(1-based) → 字母（1→A, 27→AA）。"""
    s = ""
    while c > 0:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def extract_grid_from_sheet(ws: Any, scheme: list[str] | None = None, *, max_scan_rows: int = 200) -> dict:
    """从 openpyxl worksheet 提取网格数据 + 样式。

    规则（2026-06-02 用户要求）：
    - 跳过标题行（表头区：致同会计师事务所/表名/索引号/页次，由统一 preparation header 处理）
    - 裁剪空列（仅输出有实际内容的列范围）
    - 裁剪尾部空行
    - 不输出填充色（fill）——用户明确不需要背景色

    Returns:
        {
          "cells": { "A1": {v, r, c, style:{bold,align,font_size,font_color,numeric}}, ... },
          "merged_cells": [ {s:{r,c}, e:{r,c}}, ... ],
          "col_widths": { "A": 19.7, ... },
          "max_row": int, "max_col": int,
        }
        r/c 1-based，但已偏移（跳过标题行后重编号）。仅输出有值或有格式的单元格。
    """
    if scheme is None:
        scheme = _DEFAULT_SCHEME

    raw_max_row = min(ws.max_row or 0, max_scan_rows)
    raw_max_col = ws.max_column or 0
    if raw_max_row == 0 or raw_max_col == 0:
        return {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}

    # ─── 1. 找到数据表起始行（跳过标题区）────────────────────────────────
    # 标题区 = 表头前几行（致同/表名/索引号/页次），数据表从第一个含"项目"/"期初"/"序号" 的行开始
    data_start_row = 1
    for r in range(1, min(raw_max_row, 15) + 1):
        for c in range(1, min(raw_max_col, 5) + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip() in ("项目", "序号"):
                data_start_row = r
                break
        if data_start_row > 1:
            break

    # ─── 2. 扫描有内容的列范围 ────────────────────────────────────────────
    cols_with_content: set[int] = set()
    for r in range(data_start_row, raw_max_row + 1):
        for c in range(1, raw_max_col + 1):
            v = ws.cell(row=r, column=c).value
            if v is not None and v != "" and not (isinstance(v, str) and v.startswith("=")):
                cols_with_content.add(c)
            elif isinstance(v, str) and v.startswith("="):
                # 公式列也算有内容（即使值为 0/None）
                cols_with_content.add(c)

    if not cols_with_content:
        return {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}

    effective_max_col = max(cols_with_content)

    # ─── 3. 扫描有内容的最后行（裁剪尾部空行）────────────────────────────
    effective_max_row = data_start_row
    for r in range(raw_max_row, data_start_row - 1, -1):
        has_content = False
        for c in range(1, effective_max_col + 1):
            v = ws.cell(row=r, column=c).value
            if v is not None and v != "":
                has_content = True
                break
        if has_content:
            effective_max_row = r
            break

    # ─── 4. 检测列语义（公式标注用）────────────────────────────────────────
    # 扫描表头行（data_start_row）和子表头行（data_start_row+1）确定各列的业务含义
    # 审定表布局：项目 | 未审数 | 账项调整 | 重分类调整 | 审定数 | 未审数 | ... | 变动额 | 变动率 | 原因分析
    _COL_SEMANTICS: dict[str, str] = {
        "未审数": "tb_fetch",       # TB() 从试算表取数
        "账项调整": "adj_sum",      # 从调整分录汇总
        "重分类调整": "reclass_sum", # 从重分类调整汇总
        "审定数": "computed_sum",   # =未审+调整+重分类
        "变动额": "computed_diff",  # =期末审定-期初审定
        "变动率": "computed_rate",  # =变动额/期初审定
        "原因分析": "user_input",   # 用户手填
    }
    col_formula_map: dict[int, str] = {}  # col_number → formula_hint
    # 扫描 sub-header row (data_start_row + 1)
    sub_hdr_row = data_start_row + 1 if data_start_row + 1 <= effective_max_row else data_start_row
    for c in range(1, effective_max_col + 1):
        # 先查 sub-header，再查 header
        for scan_row in (sub_hdr_row, data_start_row):
            txt = ws.cell(row=scan_row, column=c).value
            if isinstance(txt, str):
                txt_clean = txt.strip().replace("\n", "")
                for keyword, hint in _COL_SEMANTICS.items():
                    if keyword in txt_clean:
                        col_formula_map[c] = hint
                        break
            if c in col_formula_map:
                break
    # 项目列（col 1）是 label，不标注
    col_formula_map.pop(1, None)

    # ─── 5. 提取单元格（重编号：数据表首行 → row 1）──────────────────────
    row_offset = data_start_row - 1
    # 确定数据行起始（跳过表头行和子表头行）
    # 表头行 = data_start_row, 子表头行 = data_start_row+1
    # 数据行 = 从第一个非表头行开始（通常 data_start_row+2 或更早）
    header_rows_count = 1
    if sub_hdr_row > data_start_row:
        # 检查子表头行是否真有内容（确认是第二级表头还是直接数据）
        sub_has_content = False
        for c in range(2, effective_max_col + 1):
            sv = ws.cell(row=sub_hdr_row, column=c).value
            if isinstance(sv, str) and sv.strip() and not sv.startswith("="):
                sub_has_content = True
                break
        if sub_has_content:
            header_rows_count = 2

    cells: dict[str, dict] = {}
    for r in range(data_start_row, effective_max_row + 1):
        for c in range(1, effective_max_col + 1):
            cell = ws.cell(row=r, column=c)
            raw = cell.value
            v = _cell_value(raw)
            is_formula = isinstance(v, str) and v.startswith("=")
            display_v = None if is_formula else v
            has_content = display_v is not None and display_v != ""

            if not has_content:
                # Include numeric-format cells even if empty (display "-" in frontend)
                if not _is_accounting_format(cell.number_format):
                    continue

            # 构建样式（不输出 fill —— 用户明确不需要背景色）
            style: dict[str, Any] = {}
            try:
                if cell.font and cell.font.bold:
                    style["bold"] = True
                if cell.font and cell.font.sz:
                    style["font_size"] = float(cell.font.sz)
            except Exception as e:
                logger.debug("提取 cell 字体样式失败: %s", e)
            fcolor = _resolve_font_color(cell)
            if fcolor:
                style["font_color"] = fcolor
            try:
                if cell.alignment and cell.alignment.horizontal:
                    style["align"] = cell.alignment.horizontal
            except Exception as e:
                logger.debug("提取 cell 对齐样式失败: %s", e)
            if _is_accounting_format(cell.number_format):
                style["numeric"] = True

            # 公式标注：数据行（非表头行）的公式列加 formula_hint
            is_data_row = (r - data_start_row) >= header_rows_count
            if is_data_row and c in col_formula_map:
                style["formula_hint"] = col_formula_map[c]

            new_r = r - row_offset
            new_coord = f"{_col_letter(c)}{new_r}"
            cells[new_coord] = {
                "v": display_v if has_content else "",
                "r": new_r,
                "c": c,
                "style": style,
            }

    # ─── 5. 合并区域（仅保留在有效范围内的，并偏移行号）─────────────────
    merged: list[dict] = []
    for mr in ws.merged_cells.ranges:
        if mr.min_row < data_start_row:
            continue  # 标题区合并跳过
        if mr.min_row > effective_max_row:
            continue
        if mr.min_col > effective_max_col:
            continue
        merged.append({
            "s": {"r": mr.min_row - row_offset, "c": mr.min_col},
            "e": {"r": min(mr.max_row, effective_max_row) - row_offset, "c": min(mr.max_col, effective_max_col)},
        })

    # ─── 6. 列宽（仅有效列）─────────────────────────────────────────────
    col_widths: dict[str, float] = {}
    for c in range(1, effective_max_col + 1):
        letter = _col_letter(c)
        dim = ws.column_dimensions.get(letter)
        if dim and dim.width:
            col_widths[letter] = round(float(dim.width), 2)

    output_max_row = effective_max_row - row_offset
    return {
        "cells": cells,
        "merged_cells": merged,
        "col_widths": col_widths,
        "max_row": output_max_row,
        "max_col": effective_max_col,
        "column_meta": {_col_letter(c): hint for c, hint in col_formula_map.items()},
        "header_rows": header_rows_count,
    }


def extract_grid(file_path: str | Path, sheet_name: str) -> dict:
    """读取 xlsx 文件指定 sheet，提取只读网格数据 + 样式（纯函数，无 DB）。

    文件不存在 / 空 / sheet 缺失 / 解析失败 → 返回空网格（降级，不抛异常）。
    """
    import openpyxl

    empty = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}

    fp = Path(file_path)
    if not fp.exists() or fp.stat().st_size == 0:
        return empty

    try:
        wb = openpyxl.load_workbook(str(fp), read_only=False, data_only=True)
    except Exception as e:
        logger.warning("extract_grid: 加载 xlsx 失败 %s: %s", fp, e)
        return empty

    try:
        if sheet_name not in wb.sheetnames:
            return empty
        scheme = _parse_scheme_from_workbook(wb)
        ws = wb[sheet_name]
        return extract_grid_from_sheet(ws, scheme)
    except Exception as e:
        logger.warning("extract_grid: 解析 sheet 失败 %s/%s: %s", fp, sheet_name, e)
        return empty
    finally:
        wb.close()


#: 编制信息行的标签关键词。判据不是「整行文本包含关键词」，而是「某格以关键词开头
#: 且后面还有分隔符/取值」——见 :func:`_looks_like_prep_label` 的说明。
#:
#: 🔴 这份清单**必须与改造前的子串关键词逐字相同、不得扩充**。新判据因此是旧判据的
#: 真子集（格以关键词开头 ⇒ 整行必含该关键词），从而结构性地保证「只可能少删行，
#: 绝不多删」。实测扩充过 ``页次/索引号/会计期间/复核日`` 后，2722 张 sheet 里有
#: 83 张反而多删 1~3 行（``底稿目录`` / ``A3 合并报表试算`` 等），已回退。
_PREP_LABEL_KEYWORDS = (
    "致同",
    "被审计单位",
    "编制人",
    "编制日",
    "截止日",
    "复核人",
)


def _looks_like_prep_label(text: str) -> bool:
    """单个格子是否是「编制信息标签」（如 ``截止日：202X年12月31日`` / ``被审计单位：``）。

    两个条件同时满足才算：

    1. 以 :data:`_PREP_LABEL_KEYWORDS` 之一**开头**（不是「包含」）——
       故列头 ``报表截止日`` 不算（关键词不在开头），数据行里描述性长文本
       ``…被审计单位的风险评估流程…`` 也不算。
    2. 关键词之后仍有内容（``：``/``:``/空格+取值）——故裸列头 ``索引号``
       不算（关键词后为空）。

    这两条是修掉「列头行被当成编制信息行删掉」的关键（2026-08-02）：
    旧实现按整行子串命中，``报表截止日``（含「截止日」）会让 E0-3~E0-6
    四张发函记录表的列头行连同上方全部被裁掉，前端只剩无表头空网格。
    """
    t = (text or "").strip()
    if not t:
        return False
    for kw in _PREP_LABEL_KEYWORDS:
        if t.startswith(kw):
            rest = t[len(kw):].strip()
            if rest:
                return True
            # 「被审计单位：」这类只有标签没有取值的形态：原文以分隔符结尾即算
            if t[len(kw):] and t[len(kw):][0] in ("：", ":"):
                return True
    return False


def _looks_like_field_label(text: str) -> bool:
    """单个格子是否是「短标签：取值」形态（不限关键词）。

    编制信息行整行都是这种形态（``客户名称：`` / ``会计期间：202X年度`` /
    ``复核日期：2025.X.X`` / ``索引：A1-13-1`` / ``页次：1``），但关键词表只覆盖
    其中几个，故需要这个通用形态一起投票。

    三重约束把内容格排除在外：无换行 + 全长 ≤30 + 冒号出现在第 1~12 字符。
    反例（必须判 False）：``审计报告：致同审字（2021）第310A0001号；\\n专项报告：…``
    ——A1-11「文号规则」的数据格，带换行且很长，早期实现漏了这两条约束时
    该表的数据行会被重新误删。
    """
    t = (text or "").strip()
    if not t or "\n" in t or len(t) > 30:
        return False
    for sep in ("：", ":"):
        idx = t.find(sep)
        if 1 <= idx <= 12:
            return True
    return False


def _is_prep_info_row(texts: list[str]) -> bool:
    """整行是否是编制信息行（而不是列头行 / 数据行）。

    两条同时成立：

    1. **至少一格**是关键词锚定的编制信息标签（:func:`_looks_like_prep_label`）
       —— 这一条保证本判据是旧子串判据的子集（见 :data:`_PREP_LABEL_KEYWORDS`）。
    2. 「关键词标签 ∪ 短标签形态」的格数**过半**。

    过半票是必要的 —— ``核实被函证单位信息E0-2`` 的列头行里有一格叫
    ``被审计单位提供的被函证单位信息及核对（…）``，单看那一格会误判成标签，
    但它在 6 个列头里只占 1 个；``B50-2 财务报表层次风险`` 的数据行同理
    （首格是 ``被审计单位的风险评估流程未识别出…``）。
    """
    if not texts:
        return False
    if not any(_looks_like_prep_label(t) for t in texts):
        return False
    labelish = sum(
        1 for t in texts if _looks_like_prep_label(t) or _looks_like_field_label(t)
    )
    return labelish * 2 >= len(texts)


def strip_standard_header(grid: dict) -> dict:
    """裁剪致同标准表头行（事务所名/表名/编制信息行）。

    审计底稿模板前几行通常是：
      Row 1: "致同会计师事务所"
      Row 2: 表名（如"合同负债及销售替代程序检查表"）
      Row 3: 被审计单位: xxx | 编制人: | 编制日: | 索引号:
      Row 4: 截止日: | 复核人: | 复核日:
      (可能还有空行)

    这些信息已由平台 GtWpPreparationHeader 组件显示，grid 中无需重复。
    自动检测**编制信息行**的最大行号，删除其及之前的所有行并重编坐标。

    列头行永不被裁剪：判定走 :func:`_is_prep_info_row`（过半格为编制信息标签），
    不再用「整行包含关键词」的子串命中。
    """
    import re

    cells = grid.get("cells", {})
    if not cells:
        return grid

    max_col = grid.get("max_col", 0)
    max_row = grid.get("max_row", 0)

    skip = 0
    for r in range(1, min(8, max_row + 1)):
        texts = []
        for c in range(1, min(15, max_col + 1)):
            v = cells.get(f"{_col_letter(c)}{r}", {}).get("v", "")
            s = str(v).strip() if v is not None else ""
            if s:
                texts.append(s)
        if _is_prep_info_row(texts):
            skip = r

    if skip == 0:
        return grid

    # 重建 cells（行号减 skip）
    new_cells = {}
    for key, val in cells.items():
        m = re.match(r"([A-Z]+)(\d+)", key)
        if m:
            row_num = int(m.group(2))
            if row_num > skip:
                new_key = f"{m.group(1)}{row_num - skip}"
                new_val = dict(val)
                new_val["r"] = row_num - skip
                new_cells[new_key] = new_val

    # 重建 merged_cells
    new_merged = []
    for mc in grid.get("merged_cells", []):
        sr, er = mc["s"]["r"], mc["e"]["r"]
        if sr > skip:
            new_merged.append({
                "s": {"r": sr - skip, "c": mc["s"]["c"]},
                "e": {"r": er - skip, "c": mc["e"]["c"]},
            })
        elif er > skip:
            new_merged.append({
                "s": {"r": 1, "c": mc["s"]["c"]},
                "e": {"r": er - skip, "c": mc["e"]["c"]},
            })

    return {
        **grid,
        "cells": new_cells,
        "merged_cells": new_merged,
        "max_row": max_row - skip,
        "header_rows": 1,
    }
