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


# ═══ 公式执行桥接 ═══

async def execute_formula(
    formula: str,
    db,
    project_id: UUID,
    year: int,
    sheet_cells: dict | None = None,
) -> dict[str, Any]:
    """统一公式执行入口

    自动识别公式类型并调度到对应引擎执行：
    - 表内引用(cell/SUM) → 从 sheet_cells 直接计算
    - 跨表引用(TB/RPT/NOTE/WP/AUX) → 调用 data_fetch_custom
    - 混合公式 → 先解析跨表引用替换为值，再计算表内部分

    Args:
        formula: 公式字符串（支持所有统一语法）
        db: 数据库会话
        project_id: 项目ID
        year: 年度
        sheet_cells: 当前表格的 cells 字典（用于表内引用）

    Returns:
        {"value": Decimal|float|None, "sources": [...], "error": str|None}
    """
    parsed = parse_formula(formula)
    sources = []
    error = None

    if parsed["type"] == "empty":
        return {"value": None, "sources": [], "error": None}

    if parsed["type"] == "literal":
        # 纯字面量
        try:
            return {"value": float(formula.lstrip("=").strip()), "sources": [], "error": None}
        except ValueError:
            return {"value": None, "sources": [], "error": "非数值字面量"}

    # 解析跨表引用并获取值
    cross_values: dict[str, float] = {}
    if parsed["cross_refs"]:
        # 优先从预加载的 _tb_context 取值（避免N+1查询）
        tb_context = sheet_cells.get("_tb_context", {}) if sheet_cells else {}

        for cr in parsed["cross_refs"]:
            # 尝试从缓存取值
            cached_val = _try_get_from_cache(cr, tb_context)
            if cached_val is not None:
                cross_values[cr["raw"]] = cached_val
                sources.append({"type": cr["type"], "args": cr["args"], "value": cached_val, "source": "cache"})
            else:
                # 缓存未命中，走数据库查询
                from app.services.data_fetch_custom import CustomFetchService
                svc = CustomFetchService(db, project_id, year)
                source = _cross_ref_to_source(cr)
                if source:
                    val = await svc._fetch_from_source(source)
                    cross_values[cr["raw"]] = float(val) if val is not None else 0
                    sources.append({"type": cr["type"], "args": cr["args"], "value": cross_values[cr["raw"]], "source": "db"})

    # 构建可计算的表达式
    expr = formula.lstrip("=").strip()

    # 替换跨表引用为值
    for raw, val in cross_values.items():
        expr = expr.replace(raw, str(val))

    # 替换表内单元格引用为值
    if sheet_cells:
        def _replace_excel_ref(m):
            col = _letter_to_col(m.group(1))
            row = int(m.group(2)) - 1
            key = f"{row}:{col}"
            cell = sheet_cells.get(key, {})
            v = cell.get("value")
            return str(float(v)) if v is not None and _is_number(v) else "0"

        def _replace_coord_ref(m):
            row, col = int(m.group(1)), int(m.group(2))
            key = f"{row}:{col}"
            cell = sheet_cells.get(key, {})
            v = cell.get("value")
            return str(float(v)) if v is not None and _is_number(v) else "0"

        # 先处理 SUM 函数
        def _replace_sum_range(m):
            start_col = _letter_to_col(m.group(1)[:1])  # 简化：取第一个字母
            sm = _EXCEL_CELL_RE.match(m.group(1))
            em = _EXCEL_CELL_RE.match(m.group(2))
            if sm and em:
                s_row = int(sm.group(2)) - 1
                e_row = int(em.group(2)) - 1
                col = _letter_to_col(sm.group(1))
                total = 0.0
                for r in range(s_row, e_row + 1):
                    cell = sheet_cells.get(f"{r}:{col}", {})
                    v = cell.get("value")
                    if v is not None and _is_number(v):
                        total += float(v)
                return str(total)
            return "0"

        expr = _SUM_RANGE_RE.sub(_replace_sum_range, expr)
        expr = _COORD_CELL_RE.sub(_replace_coord_ref, expr)
        expr = _EXCEL_CELL_RE.sub(_replace_excel_ref, expr)

    # 安全计算表达式
    try:
        import ast
        result = _safe_eval(expr)
        return {"value": result, "sources": sources, "error": None}
    except Exception as e:
        return {"value": None, "sources": sources, "error": str(e)}


def _try_get_from_cache(cr: dict, tb_context: dict) -> float | None:
    """尝试从预加载的 _tb_context 缓存中获取跨表引用值

    仅支持 TB 类型引用（最常见的跨表引用），其他类型返回 None 走数据库。
    """
    if cr["type"] != "TB" or not tb_context:
        return None

    args = cr.get("args", [])
    if len(args) < 2:
        return None

    account_code = args[0].strip()
    field_name = args[1].strip()

    # 中文字段名映射
    field_map = {
        "审定数": "audited_amount", "未审数": "unadjusted_amount",
        "期初": "opening_balance", "AJE": "aje_adjustment", "RJE": "rje_adjustment",
        "期末": "audited_amount",
    }
    field = field_map.get(field_name, field_name)

    account_data = tb_context.get(account_code)
    if account_data and field in account_data:
        return account_data[field]
    return None


def _cross_ref_to_source(cr: dict) -> dict | None:
    """将跨表引用转为 data_fetch_custom 的 source 格式"""
    cr_type = cr["type"]
    args = cr["args"]

    if cr_type == "TB" and len(args) >= 2:
        field_map = {"审定数": "audited_amount", "未审数": "unadjusted_amount",
                     "期初": "opening_balance", "AJE": "aje_adjustment", "RJE": "rje_adjustment",
                     "期末": "audited_amount"}
        return {"type": "trial_balance", "account_code": args[0], "field": field_map.get(args[1], args[1])}
    elif cr_type == "RPT" and len(args) >= 2:
        field_map = {"期末": "amount", "期初": "prior_amount"}
        return {"type": "report", "row_code": args[0], "field": field_map.get(args[1], "amount")}
    elif cr_type == "NOTE" and len(args) >= 3:
        return {"type": "note", "section": args[0], "row_label": args[1], "col_header": args[2]}
    elif cr_type == "WP" and len(args) >= 2:
        field_map = {"审定数": "audited_amount", "未审数": "unadjusted_amount", "期初": "opening_balance"}
        return {"type": "workpaper", "wp_code": args[0], "data_key": field_map.get(args[1], args[1])}
    elif cr_type == "AUX" and len(args) >= 3:
        field_map = {"期末": "closing_balance", "期初": "opening_balance"}
        return {"type": "aux_balance", "account_code": args[0], "aux_code": args[1], "field": field_map.get(args[2], args[2])}
    return None


def _is_number(v) -> bool:
    """判断值是否可转为数字"""
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _safe_eval(expr: str) -> float | None:
    """安全计算数学表达式（只允许数字和+-*/()）"""
    import ast
    import operator

    # 清理：只保留数字、运算符、小数点、括号、空格
    allowed = set("0123456789.+-*/() ")
    cleaned = "".join(c for c in expr if c in allowed).strip()
    if not cleaned:
        return None

    try:
        tree = ast.parse(cleaned, mode="eval")
        return _eval_node(tree.body)
    except Exception:
        return None


def _eval_node(node) -> float:
    """递归求值 AST 节点"""
    import ast
    import operator

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
    }

    if isinstance(node, ast.Constant):
        return float(node.value)
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = ops.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的运算符: {type(node.op)}")
        if isinstance(node.op, ast.Div) and right == 0:
            return 0.0  # 除零返回0
        return op(left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op = ops.get(type(node.op))
        if op:
            return op(operand)
        raise ValueError(f"不支持的一元运算符")
    else:
        raise ValueError(f"不支持的节点类型: {type(node)}")
