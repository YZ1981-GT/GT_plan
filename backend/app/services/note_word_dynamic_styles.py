"""Sprint C.4 — Word 导出动态行/列样式增强 (D1/D2/D5).

主要 API:
- apply_dynamic_row_style(cell): 动态行黄色高亮（GTNoteDynamicRow）
- apply_dynamic_col_style(cell): 动态列紫色高亮（GTNoteDynamicCol）
- apply_consol_elimination_style(cell, eliminated): 合并抵销双列样式
- replace_empty_table_with_paragraph(doc, paragraph_text): 空表替换段落
- pre_render_jinja_refs(text, rendered_numbers): 预渲染 ref() 内部引用
- skip_empty_section(note): 判断空章节是否跳过

覆盖任务：
- C.4.1: GTNoteDynamicRow / GTNoteDynamicCol 样式
- C.4.3: 空表替换 + 空章节跳过 + 不适用提示
- C.4.5: 合并附注抵销双列 Word 表
- C.4.9: Word 内部引用 ref() 渲染最终序号
"""
from __future__ import annotations

import re
from typing import Any

from docx.oxml.ns import qn
from docx.oxml import OxmlElement


__all__ = [
    "apply_dynamic_row_style",
    "apply_dynamic_col_style",
    "apply_consol_elimination_style",
    "replace_empty_table_with_paragraph",
    "pre_render_jinja_refs",
    "should_skip_empty_section",
    "build_consol_dual_column_table_data",
]


# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------

# C.4.1: 动态行/列颜色（与前端 cell-dynamic-row / cell-dynamic-col 一致）
DYNAMIC_ROW_FILL = "FFFBE6"  # 浅黄
DYNAMIC_COL_FILL = "F3EAFF"  # 浅紫
ELIMINATION_FILL = "FFE4E1"  # 浅红（抵销列）


# ---------------------------------------------------------------------------
# C.4.1: Dynamic Row / Col Styles
# ---------------------------------------------------------------------------


def _set_cell_shading(cell, fill_hex: str) -> None:
    """Apply background color to a Word table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


def apply_dynamic_row_style(cell) -> None:
    """C.4.1: 应用动态行黄色高亮（GTNoteDynamicRow）."""
    _set_cell_shading(cell, DYNAMIC_ROW_FILL)


def apply_dynamic_col_style(cell) -> None:
    """C.4.1: 应用动态列紫色高亮（GTNoteDynamicCol）."""
    _set_cell_shading(cell, DYNAMIC_COL_FILL)


def apply_consol_elimination_style(cell, eliminated: bool = True) -> None:
    """C.4.5: 合并附注抵销列样式（红色淡底）."""
    if eliminated:
        _set_cell_shading(cell, ELIMINATION_FILL)


# ---------------------------------------------------------------------------
# C.4.3: Empty Section / Table Handling
# ---------------------------------------------------------------------------


def should_skip_empty_section(note: dict) -> bool:
    """C.4.3 + design §7.1: 判断章节是否应跳过（auto_trim 标记或全空）.

    跳过条件（design §7.1 裁剪判定优先级 ①~④）：
    1. `is_deleted=True`（auto_trim 或用户删除）
    2. `status='not_applicable'`（auto_trim_v2 章节级不适用）
    3. `is_empty=True`（用户「不导出」标记）
    4. `text_content` 空 且 所有 table 经 `is_empty_table()` 判定全空

    注：条件 ④ 复用 `is_empty_table`（不重复实现空表检测）；
    `table_data` 支持多表 `_tables` 数组与单表两种结构。
    """
    if not isinstance(note, dict):
        return False
    if note.get("is_deleted"):
        return True
    if note.get("status") == "not_applicable":
        return True
    # ③ 用户标记「不导出」
    if note.get("is_empty"):
        return True
    # ④ text_content 空 且 所有表全空
    text_content = note.get("text_content")
    if text_content and str(text_content).strip():
        return False
    table_data = note.get("table_data")
    if not isinstance(table_data, dict):
        # 无文本且无表数据 → 视为全空
        return True
    tables_to_check = table_data.get("_tables") or [table_data]
    for tbl in tables_to_check:
        if not isinstance(tbl, dict):
            continue
        if not is_empty_table(tbl):
            return False
    return True


def is_empty_table(table_data: dict) -> bool:
    """C.4.3: 判断单表是否为空（所有数据 cell 为 0/空/-）."""
    if not isinstance(table_data, dict):
        return True
    rows = table_data.get("rows", [])
    if not rows:
        return True
    for row in rows:
        cells = row.get("cells", row.get("values", []))
        for cell in cells:
            if isinstance(cell, dict):
                val = cell.get("value", cell.get("manual_value"))
            else:
                val = cell
            if val is None or val == "" or val == 0 or val == "0" or val == "-":
                continue
            return False
    return True


def replace_empty_table_with_paragraph(
    doc: Any,
    paragraph_text: str = "本期无此项业务",
) -> Any:
    """C.4.3: 空表替换为提示段落（如「本期无此项业务」）."""
    p = doc.add_paragraph()
    run = p.add_run(paragraph_text)
    run.italic = True
    # Apply gray text color
    run.font.color.rgb = None  # default; can be customized
    return p


def get_table_render_mode(table_data: dict) -> str:
    """C.4.3: 获取表格渲染模式（normal / no_business_paragraph / skip）.

    优先级：
    1. table_data._render_as = 'no_business_paragraph' → 段落替换
    2. is_empty_table → 'skip' 由调用方决定是否替换
    3. 默认 'normal'
    """
    if not isinstance(table_data, dict):
        return "skip"
    render_as = table_data.get("_render_as")
    if render_as == "no_business_paragraph":
        return "no_business_paragraph"
    if is_empty_table(table_data):
        return "no_business_paragraph"
    return "normal"


# ---------------------------------------------------------------------------
# C.4.5: Consol Dual Column (抵销前/抵销后)
# ---------------------------------------------------------------------------


def build_consol_dual_column_table_data(
    base_table_data: dict,
    elimination_data: dict | None = None,
) -> dict:
    """C.4.5: 构造合并附注抵销前后双列表数据.

    输入：
    - base_table_data: 单体附注汇总数据（抵销前）
    - elimination_data: {row_idx: {col_idx: amount}} 抵销额映射

    输出：
    - 新 table_data，每个数据列展开为「抵销前 / 抵销后」两列
    """
    if not isinstance(base_table_data, dict):
        return base_table_data

    headers_raw = list(base_table_data.get("headers", []))
    rows = base_table_data.get("rows", [])

    if not headers_raw:
        return base_table_data

    # Build new headers: keep first column (label), expand others to dual
    new_headers = [headers_raw[0]]
    new_columns_meta = []

    if base_table_data.get("_columns_meta"):
        new_columns_meta.append(base_table_data["_columns_meta"][0])

    for idx, h in enumerate(headers_raw[1:], start=1):
        new_headers.append(f"{h}（抵销前）")
        new_headers.append(f"{h}（抵销后）")
        if base_table_data.get("_columns_meta") and idx < len(base_table_data["_columns_meta"]):
            base_col = base_table_data["_columns_meta"][idx]
            new_columns_meta.append({
                **base_col,
                "id": f"{base_col.get('id', f'col_{idx}')}_pre",
                "label": f"{base_col.get('label', h)}（抵销前）",
            })
            new_columns_meta.append({
                **base_col,
                "id": f"{base_col.get('id', f'col_{idx}')}_post",
                "label": f"{base_col.get('label', h)}（抵销后）",
                "is_elimination": True,
            })

    # Build new rows
    new_rows = []
    elim = elimination_data or {}
    for row_idx, row in enumerate(rows):
        new_row = {**row}
        old_cells = row.get("cells", row.get("values", []))
        new_cells = [old_cells[0] if old_cells else ""]  # label column

        for col_idx, val in enumerate(old_cells[1:], start=1):
            base_val = val
            if isinstance(val, dict):
                base_val = val.get("value", val.get("manual_value"))

            # 抵销前 = 原值
            new_cells.append(base_val)

            # 抵销后 = 原值 - 抵销额
            elim_amount = elim.get(row_idx, {}).get(col_idx, 0)
            try:
                if base_val is not None and base_val != "" and base_val != "-":
                    post_val = float(base_val) - float(elim_amount)
                    new_cells.append(post_val)
                else:
                    new_cells.append(base_val)
            except (ValueError, TypeError):
                new_cells.append(base_val)

        new_row["cells"] = new_cells
        new_rows.append(new_row)

    result = {
        **base_table_data,
        "headers": new_headers,
        "rows": new_rows,
    }
    if new_columns_meta:
        result["_columns_meta"] = new_columns_meta
    result["_has_elimination_columns"] = True
    return result


# ---------------------------------------------------------------------------
# C.4.9: Pre-render Jinja ref() in Word text
# ---------------------------------------------------------------------------

# Match {{ ref('section_id') }} or {{ref("section_id")}}
_REF_PATTERN = re.compile(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")


def pre_render_jinja_refs(text: str, rendered_numbers: dict[str, str]) -> str:
    """C.4.9: 预渲染文本中的 ref() 调用为最终章节序号.

    输入：'本期增加详见 {{ ref("section_revenue") }}'
    输出：'本期增加详见 八、（一）2.'

    Args:
        text: 原始文本（含 Jinja ref() 调用）
        rendered_numbers: {section_id: rendered_number} 映射；空 dict 时未知章节回退占位

    Returns:
        替换后的文本
    """
    if not text:
        return text
    if rendered_numbers is None:
        return text

    def _replace(match: re.Match) -> str:
        section_id = match.group(1)
        return rendered_numbers.get(section_id, f"[未知章节: {section_id}]")

    return _REF_PATTERN.sub(_replace, text)
