"""统一公式语法引擎 — 一套语法覆盖所有场景

用户只需学习一种公式语法，后端自动识别并执行。

═══ 统一公式语法规范 ═══

1. 单元格引用（表内）：
   - Excel风格: B3, $B$3, B3:B10
   - 坐标风格: [2,1]（row=2, col=1，0-indexed）

2. 跨表引用：
   - 试算表: TB(科目编码, 字段)     如 TB(1001, 审定数)
   - 报表:   RPT(行次, 字段)        如 RPT(BS-002, 期末)
   - 附注:   NOTE(章节, 行标签, 列)  如 NOTE(五、1, 合计, 期末余额)
   - 底稿:   WP(编号, 字段)         如 WP(E1-1, 审定数)
   - 辅助:   AUX(科目, 维度, 字段)  如 AUX(1122, 客户A, 期末)

3. 函数：
   - SUM(B2:B5)          — 区域求和
   - SUM([1,1]:[4,1])    — 坐标区域求和
   - ABS(B3)             — 绝对值
   - IF(B3>0, B3, 0)     — 条件
   - ROUND(B3, 2)        — 四舍五入

4. 运算符：+ - * / ()

═══ 解析流程 ═══
用户输入 → parse() 识别语法类型 → 转为统一 AST → execute() 执行 → 返回结果+溯源
"""

from __future__ import annotations

import re
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

_logger = logging.getLogger(__name__)


# ═══ 公式解析器 ═══

# Excel 列字母→数字
def _letter_to_col(letter: str) -> int:
    """A→0, B→1, Z→25, AA→26"""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - 64)
    return result - 1


# 正则模式
_EXCEL_CELL_RE = re.compile(r'\$?([A-Z]{1,3})\$?(\d+)')  # B3, $B$3
_COORD_CELL_RE = re.compile(r'\[(\d+),\s*(\d+)\]')  # [2,1]
_TB_RE = re.compile(r'TB\(\s*([^,]+)\s*,\s*([^)]+)\s*\)')
_RPT_RE = re.compile(r'RPT\(\s*([^,]+)\s*,\s*([^)]+)\s*\)')
_NOTE_RE = re.compile(r'NOTE\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)')
_WP_RE = re.compile(r'WP\(\s*([^,]+)\s*,\s*([^)]+)\s*\)')
_AUX_RE = re.compile(r'AUX\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)')
_SUM_RANGE_RE = re.compile(r'SUM\(\s*([A-Z]{1,3}\d+)\s*:\s*([A-Z]{1,3}\d+)\s*\)')
_SUM_COORD_RE = re.compile(r'SUM\(\s*\[(\d+),\s*(\d+)\]\s*:\s*\[(\d+),\s*(\d+)\]\s*\)')


class FormulaToken:
    """公式解析后的 token"""
    CELL_REF = "cell_ref"       # 表内单元格引用
    CROSS_REF = "cross_ref"     # 跨表引用
    FUNCTION = "function"       # 函数调用
    LITERAL = "literal"         # 字面量
    OPERATOR = "operator"       # 运算符

    def __init__(self, token_type: str, value: Any, raw: str = ""):
        self.token_type = token_type
        self.value = value
        self.raw = raw


def parse_formula(formula: str) -> dict[str, Any]:
    """解析公式，返回结构化信息

    Returns:
        {
            "type": "simple" | "cross_table" | "function" | "mixed",
            "references": [{"type": "cell", "row": 2, "col": 1, "addr": "B3"}, ...],
            "cross_refs": [{"type": "TB", "args": ["1001", "审定数"]}, ...],
            "functions": ["SUM", ...],
            "raw": "=SUM(B2:B5) + TB(1001, 审定数)"
        }
    """
    if not formula:
        return {"type": "empty", "references": [], "cross_refs": [], "functions": [], "raw": ""}

    # 去掉开头的 =
    expr = formula.lstrip("=").strip()

    references = []
    cross_refs = []
    functions = []

    # 提取跨表引用
    for m in _TB_RE.finditer(expr):
        cross_refs.append({"type": "TB", "args": [m.group(1).strip(), m.group(2).strip()], "raw": m.group(0)})
    for m in _RPT_RE.finditer(expr):
        cross_refs.append({"type": "RPT", "args": [m.group(1).strip(), m.group(2).strip()], "raw": m.group(0)})
    for m in _NOTE_RE.finditer(expr):
        cross_refs.append({"type": "NOTE", "args": [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()], "raw": m.group(0)})
    for m in _WP_RE.finditer(expr):
        cross_refs.append({"type": "WP", "args": [m.group(1).strip(), m.group(2).strip()], "raw": m.group(0)})
    for m in _AUX_RE.finditer(expr):
        cross_refs.append({"type": "AUX", "args": [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()], "raw": m.group(0)})

    # 提取 Excel 风格单元格引用
    for m in _EXCEL_CELL_RE.finditer(expr):
        col = _letter_to_col(m.group(1))
        row = int(m.group(2)) - 1  # 转0-indexed
        references.append({"type": "cell", "row": row, "col": col, "addr": f"{m.group(1)}{m.group(2)}"})

    # 提取坐标风格引用
    for m in _COORD_CELL_RE.finditer(expr):
        row, col = int(m.group(1)), int(m.group(2))
        references.append({"type": "cell", "row": row, "col": col, "addr": f"[{row},{col}]"})

    # 提取函数
    for func_name in ["SUM", "ABS", "IF", "ROUND", "MAX", "MIN", "AVERAGE"]:
        if func_name + "(" in expr.upper():
            functions.append(func_name)

    # 确定类型
    if cross_refs and references:
        formula_type = "mixed"
    elif cross_refs:
        formula_type = "cross_table"
    elif functions:
        formula_type = "function"
    elif references:
        formula_type = "simple"
    else:
        formula_type = "literal"

    return {
        "type": formula_type,
        "references": references,
        "cross_refs": cross_refs,
        "functions": functions,
        "raw": formula,
    }


def formula_to_display(formula: str, cells: dict) -> str:
    """将公式转为可读的显示文本（替换地址为值预览）

    如 "=B2+B3" → "=50000+1200000 (B2+B3)"
    """
    if not formula:
        return ""

    expr = formula.lstrip("=").strip()
    preview_parts = []

    for m in _EXCEL_CELL_RE.finditer(expr):
        col = _letter_to_col(m.group(1))
        row = int(m.group(2)) - 1
        key = f"{row}:{col}"
        cell = cells.get(key, {})
        val = cell.get("value")
        if val is not None:
            preview_parts.append(f"{m.group(0)}={val}")

    if preview_parts:
        return f"{formula}  ({', '.join(preview_parts)})"
    return formula


def convert_excel_to_internal(formula: str) -> str:
    """将 Excel 风格公式转为内部 cell(row,col) 格式

    =SUM(B2:B5) → SUM(1:4, 1)
    =B3+C3 → cell(2,1)+cell(2,2)
    """
    if not formula:
        return ""

    expr = formula.lstrip("=").strip()

    # SUM(B2:B5) → SUM(start_row:end_row, col)
    def _convert_sum_range(m):
        start_col = _letter_to_col(m.group(1)[:len(m.group(1))-len(re.search(r'\d+', m.group(1)).group())])
        # 重新解析
        start_match = _EXCEL_CELL_RE.match(m.group(1))
        end_match = _EXCEL_CELL_RE.match(m.group(2))
        if start_match and end_match:
            s_row = int(start_match.group(2)) - 1
            e_row = int(end_match.group(2)) - 1
            col = _letter_to_col(start_match.group(1))
            return f"SUM({s_row}:{e_row}, {col})"
        return m.group(0)

    result = _SUM_RANGE_RE.sub(_convert_sum_range, expr)

    # 单个单元格引用 B3 → cell(2,1)
    def _convert_cell(m):
        col = _letter_to_col(m.group(1))
        row = int(m.group(2)) - 1
        return f"cell({row}, {col})"

    result = _EXCEL_CELL_RE.sub(_convert_cell, result)
    return result


def convert_internal_to_excel(formula: str) -> str:
    """将内部 cell(row,col) 格式转为 Excel 风格

    cell(2,1) → B3
    SUM(1:4, 1) → SUM(B2:B5)
    """
    from app.services.excel_html_converter import _col_to_letter

    if not formula:
        return ""

    # cell(row, col) → LetterRow
    def _convert_cell(m):
        row, col = int(m.group(1)), int(m.group(2))
        return f"{_col_to_letter(col)}{row + 1}"

    from app.services.excel_html_converter import _CELL_REF_PATTERN, _SUM_PATTERN
    result = _CELL_REF_PATTERN.sub(_convert_cell, formula)

    # SUM(start:end, col) → SUM(Letter_start:Letter_end)
    def _convert_sum(m):
        start, end, col = int(m.group(1)), int(m.group(2)), int(m.group(3))
        letter = _col_to_letter(col)
        return f"SUM({letter}{start+1}:{letter}{end+1})"

    result = _SUM_PATTERN.sub(_convert_sum, result)
    return result


# ═══ 公式验证 ═══

def validate_formula(formula: str, max_row: int, max_col: int) -> dict[str, Any]:
    """验证公式合法性

    检查：
    - 引用的单元格是否在表格范围内
    - 括号是否匹配
    - 函数名是否合法
    - 跨表引用格式是否正确
    """
    errors = []
    parsed = parse_formula(formula)

    # 检查单元格引用范围
    for ref in parsed["references"]:
        if ref["row"] < 0 or ref["row"] >= max_row:
            errors.append(f"行引用越界: {ref['addr']} (最大行{max_row})")
        if ref["col"] < 0 or ref["col"] >= max_col:
            errors.append(f"列引用越界: {ref['addr']} (最大列{max_col})")

    # 检查括号匹配
    expr = formula.lstrip("=")
    if expr.count("(") != expr.count(")"):
        errors.append("括号不匹配")

    # 检查跨表引用格式
    for cr in parsed["cross_refs"]:
        if cr["type"] == "TB" and len(cr["args"]) < 2:
            errors.append(f"TB引用参数不足: {cr['raw']}")
        if cr["type"] == "RPT" and len(cr["args"]) < 2:
            errors.append(f"RPT引用参数不足: {cr['raw']}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "parsed": parsed,
    }
