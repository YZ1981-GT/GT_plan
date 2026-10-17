"""附注模板模式表格外观（spec ``deliverable-trio-generation-accuracy`` §2.4；由 ``note_template_block_fill`` 拆出）。

``NoteWordExporter._render_table`` 产出的表套模板样例表外观：表属性、列宽（金额列按最长数值放宽）、字号（样例表
字号 / 宽表 9 磅 / 放不下 8 磅）、最小行高、表头行重复、合计行加粗。只在模板模式用，程序化导出（R5.2 口径）不动。
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.services.note_template_docx_base import (
    _raw_text,
    _text,
    _W_P,
)

__all__ = [
    "apply_template_table_look",
]

_TOTAL_RE = re.compile(r"^(?:合\s*计|小\s*计|总\s*计)")
#: 模板正文宽度（twip）：A4 21cm − 左 3cm − 右 3.18cm ≈ 14.8cm；无样例表时按此分配列宽
_TEXT_WIDTH_TWIPS = 8400
_TCPR_AFTER_BORDERS = ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign",
                       "w:hideMark", "w:headers", "w:cellIns", "w:cellDel", "w:cellMerge", "w:tcPrChange")


def _border(tag: str, val: str, sz: int) -> Any:
    el = OxmlElement(tag)
    el.set(qn("w:val"), val)
    el.set(qn("w:color"), "auto")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), "0")
    return el


def _default_tblpr() -> Any:
    """无样例表时的模板外观：通栏、居中、上下 1 磅、无竖线（同模板样例表）。"""
    tblpr = OxmlElement("w:tblPr")
    w = OxmlElement("w:tblW")
    w.set(qn("w:w"), "5000")
    w.set(qn("w:type"), "pct")
    tblpr.append(w)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    tblpr.append(jc)
    borders = OxmlElement("w:tblBorders")
    for tag, val, sz in (("w:top", "single", 8), ("w:left", "none", 0), ("w:bottom", "single", 8),
                         ("w:right", "none", 0), ("w:insideH", "none", 0), ("w:insideV", "none", 0)):
        borders.append(_border(tag, val, sz))
    tblpr.append(borders)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "autofit")
    tblpr.append(layout)
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", 0), ("left", 108), ("bottom", 0), ("right", 108)):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), str(val))
        m.set(qn("w:type"), "dxa")
        mar.append(m)
    tblpr.append(mar)
    return tblpr


def _grid_widths(tbl, sample) -> list[int]:
    cols = tbl.find(qn("w:tblGrid"))
    n = len(cols.findall(qn("w:gridCol"))) if cols is not None else 0
    if n <= 0:
        return []
    if sample is not None:
        sg = sample.find(qn("w:tblGrid"))
        widths = [int(g.get(qn("w:w")) or 0) for g in (sg.findall(qn("w:gridCol")) if sg is not None else [])]
        if len(widths) == n and all(w > 0 for w in widths):
            return widths
    weights = [2] + [1] * (n - 1) if n >= 3 else ([3, 2] if n == 2 else [1])
    total = sum(weights)
    return [round(_TEXT_WIDTH_TWIPS * w / total) for w in weights]


def _text_units(text: str) -> float:
    """显示宽度（em）：全角字 1、半角字约 0.46（Arial Narrow 数字宽）。"""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.46 for ch in text)


def _fit_widths(tbl, widths: list[int], header_rows: int, half_pts: int) -> tuple[list[int], int]:
    """数据列宽不小于该列最长内容（从首列匀出，首列不少于 1300 twip ≈ 2.3cm）；放不下时字号降到 8 磅。

    返回 ``(列宽, 字号半磅)``。只处理 3 列及以上的表（两列表首列本就够宽）。
    """
    if len(widths) < 3:
        return widths, half_pts
    need_units = [0.0] * len(widths)
    for tr in tbl.findall(qn("w:tr"))[header_rows:]:
        for col, span, tc in _row_cells(tr):
            if span != 1 or col == 0 or col >= len(widths):
                continue
            for p in tc.iter(_W_P):
                need_units[col] = max(need_units[col], _text_units(_raw_text(p).strip()))
    total = sum(widths)
    out: list[int] = list(widths)
    for size in (half_pts, 16) if half_pts > 16 else (half_pts,):
        em = size / 2 * 20  # 1 em 的 twip 数
        out = list(widths)
        for c in range(1, len(out)):
            need = round(need_units[c] * em) + 230 if need_units[c] else 0  # 230 ≈ 左右单元格边距 + 余量
            if need > out[c]:
                out[0] -= need - out[c]
                out[c] = need
        if out[0] >= 1300:
            return out, size
    # 8 磅仍放不下：首列保底，其余按比例压缩到原总宽
    out[0] = max(out[0], 1300)
    rest = sum(out[1:])
    if rest > total - out[0] > 0:
        factor = (total - out[0]) / rest
        out[1:] = [max(1, int(w * factor)) for w in out[1:]]
    return out, 16 if half_pts > 16 else half_pts


def _tc_set_borders(tc, bottom_sz: int | None) -> None:
    tcpr = tc.get_or_add_tcPr()
    for old in tcpr.findall(qn("w:tcBorders")):
        tcpr.remove(old)
    if bottom_sz is None:
        return
    borders = OxmlElement("w:tcBorders")
    borders.append(_border("w:bottom", "single", bottom_sz))
    tcpr.insert_element_before(borders, *_TCPR_AFTER_BORDERS)


def _row_cells(tr) -> list[tuple[int, int, Any]]:
    """行内单元格 → ``[(起始网格列, 跨列数, tc)]``。"""
    out = []
    col = 0
    for tc in tr.findall(qn("w:tc")):
        tcpr = tc.find(qn("w:tcPr"))
        span_el = tcpr.find(qn("w:gridSpan")) if tcpr is not None else None
        span = int(span_el.get(qn("w:val")) or 1) if span_el is not None else 1
        out.append((col, span, tc))
        col += span
    return out


def apply_template_table_look(tbl, sample=None, *, header_rows: int = 1) -> None:
    """``_render_table`` 产出的表套模板样例表外观（只在模板模式用，程序化导出的 R5.2 口径不动）。

    - 表属性整体换成样例表的 ``tblPr``（表样式、通栏宽度、居中、上下 1 磅、单元格边距）；无样例表用同款默认；
    - 列宽：列数与样例表一致时沿用样例表网格，否则首列加宽、其余等分；单元格宽度按百分比写；
    - 行：最小行高 340（与模板一致，不再固定 0.7cm 截断换行）、不跨页断行、表头行跨页重复；
    - 表头：末行（及跨列分组格）下边框 1/2 磅；单元格垂直居中；
    - 字体：Arial Narrow / 仿宋_GB2312，去掉固定字号（继承模板正文字号，与样例表一致）；合计 / 小计 / 总计行加粗。
    """
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.shared import Pt
    from docx.table import _Cell
    from docx.text.run import Run

    old = tbl.find(qn("w:tblPr"))
    sample_pr = sample.find(qn("w:tblPr")) if sample is not None else None
    new = copy.deepcopy(sample_pr) if sample_pr is not None else _default_tblpr()
    if old is not None:
        tbl.replace(old, new)
    else:
        tbl.insert(0, new)

    rows = tbl.findall(qn("w:tr"))
    header_rows = max(0, min(header_rows, len(rows)))
    widths = _grid_widths(tbl, sample)
    # 字号：样例表单元格写了字号（宽表多为 9 磅）就照用；没写的继承模板正文（五号），6 列及以上的宽表用 9 磅防数字折行
    size_half_pts = _sample_font_size(sample) or (18 if len(widths) >= 6 else None)
    if widths:
        # 金额列按最长数值放宽（模板样例表列宽是按空表设计的，真实金额放不下会折成两行）
        widths, fitted = _fit_widths(tbl, widths, header_rows, size_half_pts or 21)
        if fitted != (size_half_pts or 21):
            size_half_pts = fitted
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None and widths:
        for g, w in zip(grid.findall(qn("w:gridCol")), widths):
            g.set(qn("w:w"), str(w))
    total = sum(widths) or 1
    for i, tr in enumerate(rows):
        trpr = tr.get_or_add_trPr()
        for tag in ("w:trHeight", "w:cantSplit", "w:tblHeader"):
            for el in trpr.findall(qn(tag)):
                trpr.remove(el)
        trpr.append(OxmlElement("w:cantSplit"))
        h = OxmlElement("w:trHeight")
        h.set(qn("w:val"), "340")
        h.set(qn("w:hRule"), "atLeast")
        trpr.append(h)
        if i < header_rows:
            trpr.append(OxmlElement("w:tblHeader"))
        label = ""
        for k, (col, span, tc) in enumerate(_row_cells(tr)):
            if widths:
                tcw = tc.get_or_add_tcPr().get_or_add_tcW()
                tcw.set(qn("w:w"), str(round(5000 * sum(widths[col: col + span]) / total)))
                tcw.set(qn("w:type"), "pct")
            bottom = 4 if i < header_rows and (i == header_rows - 1 or span > 1) else None
            _tc_set_borders(tc, bottom)
            _Cell(tc, None).vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if k == 0:
                label = re.sub(r"\s+", "", _text(tc))
            for r in tc.iter(qn("w:r")):
                rpr = r.get_or_add_rPr()
                for tag in ("w:sz", "w:szCs"):
                    for el in rpr.findall(qn(tag)):
                        rpr.remove(el)
                if size_half_pts:
                    Run(r, None).font.size = Pt(size_half_pts / 2)
                fonts = rpr.get_or_add_rFonts()
                for attr in ("w:ascii", "w:hAnsi", "w:cs"):
                    fonts.set(qn(attr), "Arial Narrow")
                fonts.set(qn("w:eastAsia"), "仿宋_GB2312")
        if i >= header_rows and _TOTAL_RE.match(label):
            for r in tr.iter(qn("w:r")):
                Run(r, None).bold = True


def _sample_font_size(sample) -> int | None:
    """样例表单元格 run 里最常见的字号（半磅）；没写字号返回 None。"""
    if sample is None:
        return None
    counts: dict[int, int] = {}
    for sz in sample.iter(qn("w:sz")):
        parent = sz.getparent()
        if parent is None or parent.tag != qn("w:rPr") or parent.getparent() is None or parent.getparent().tag != qn("w:r"):
            continue
        try:
            v = int(sz.get(qn("w:val")) or 0)
        except ValueError:
            continue
        if v > 0:
            counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _header_rows(table: dict) -> int:
    """``_render_table`` 的表头行数：有分组表头（``_column_groups``）两行，否则一行。"""
    groups = table.get("_column_groups")
    return 2 if isinstance(groups, list) and groups else 1
