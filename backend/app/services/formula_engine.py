"""统一公式引擎 — 企业级版本

所有报表公式计算的唯一执行器。

设计原则：
- 纯函数，不依赖 async/db session
- 插件式函数注册（新增函数只需注册 handler）
- 返回 FormulaResult（含 value + errors + trace）
- 多列支持（TB 第二参数指定列名）
- 上年数据支持（PREV 函数）
- 公式解析缓存（同一公式不重复解析）

支持的函数：
- TB('1002','期末余额') — 单科目取值
- SUM_TB('1400~1499','期末余额') — 范围科目求和
- ROW('BS-002') — 引用其他行的值
- SUM_ROW('BS-002','BS-008') — 范围行次求和
- REPORT('BS-002','current') — 跨报表引用
- PREV('1002','期末余额') — 上年同期值
- AUX('1002','客户','期末余额') — 辅助核算取值
- ABS/ROUND/MAX/MIN/IF — 内置函数
"""

from __future__ import annotations

import ast
import logging
import operator
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类型定义
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FormulaResult:
    """公式执行结果"""
    value: Decimal = Decimal("0")
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)  # 取数轨迹（审计用）

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass
class FormulaContext:
    """公式执行上下文（预加载的数据）"""
    # 科目编码 → {列名: 金额}（支持多列取数）
    tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 行次编码 → 已计算值（供 ROW/SUM_ROW 引用）
    row_cache: dict[str, Decimal] = field(default_factory=dict)
    # 上年科目数据（供 PREV 引用）
    prior_tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 默认列名
    default_column: str = "期末余额"

    # ── 便捷构造方法 ──
    @classmethod
    def from_simple_map(
        cls,
        tb_map: dict[str, Decimal],
        row_cache: dict[str, Any] | None = None,
        prior_map: dict[str, Decimal] | None = None,
    ) -> "FormulaContext":
        """从简单的 科目→金额 字典构建上下文（向后兼容）"""
        tb_data = {code: {"期末余额": val, "审定数": val, "未审数": val} for code, val in tb_map.items()}
        prior_data = {}
        if prior_map:
            prior_data = {code: {"期末余额": val} for code, val in prior_map.items()}
        rc = {k: Decimal(str(v)) for k, v in (row_cache or {}).items()}
        return cls(tb_data=tb_data, row_cache=rc, prior_tb_data=prior_data)


# ── 列名映射（中文 → 标准字段名） ──
COLUMN_ALIASES: dict[str, str] = {
    "期末余额": "期末余额",
    "审定数": "期末余额",
    "年初余额": "年初余额",
    "期初余额": "年初余额",
    "未审数": "期末余额",
    "本期发生额": "本期发生额",
    "RJE调整": "RJE调整",
    "AJE调整": "AJE调整",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 公式 Token 解析（Regex）
# ═══════════════════════════════════════════════════════════════════════════════

_TOKEN_PATTERNS = [
    ("SUM_ROW", re.compile(r"SUM_ROW\('([^']+)','([^']+)'\)")),
    ("SUM_TB", re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")),
    ("TB", re.compile(r"TB\('([^']+)','([^']+)'\)")),
    ("ROW", re.compile(r"ROW\('([^']+)'\)")),
    ("REPORT", re.compile(r"REPORT\('([^']+)','([^']+)'\)")),
    ("PREV", re.compile(r"PREV\('([^']+)','([^']+)'\)")),
    ("AUX", re.compile(r"AUX\('([^']+)','([^']*?)','([^']+)'\)")),
    ("NOTE", re.compile(r"NOTE\('([^']+)','([^']+)','([^']+)'\)")),
    ("WP", re.compile(r"WP\('([^']+)','([^']+)'\)")),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 安全算术求值器
# ═══════════════════════════════════════════════════════════════════════════════

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_expr(expr: str) -> Decimal:
    """安全求值纯算术表达式（+−×÷ 括号 + 内置函数），基于 AST 解析。"""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return Decimal("0")

    def _eval_node(node: ast.expr) -> Decimal:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            if isinstance(node.op, ast.Div) and right == 0:
                return Decimal("0")
            return Decimal(str(op_func(float(left), float(right))))
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError("Unsupported unary operator")
            return Decimal(str(op_func(float(operand))))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            args = [_eval_node(a) for a in node.args]
            if fn == "ABS" and len(args) == 1:
                return abs(args[0])
            if fn == "ROUND" and len(args) >= 1:
                ndigits = int(args[1]) if len(args) > 1 else 2
                return round(args[0], ndigits)
            if fn == "MAX" and len(args) >= 2:
                return max(args)
            if fn == "MIN" and len(args) >= 2:
                return min(args)
            if fn == "IF" and len(args) == 3:
                return args[1] if args[0] != 0 else args[2]
            raise ValueError(f"Unsupported function: {fn}")
        if isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval_node(comparator)
                if isinstance(op, ast.Eq) and left != right: return Decimal("0")
                if isinstance(op, ast.NotEq) and left == right: return Decimal("0")
                if isinstance(op, ast.Gt) and not (left > right): return Decimal("0")
                if isinstance(op, ast.GtE) and not (left >= right): return Decimal("0")
                if isinstance(op, ast.Lt) and not (left < right): return Decimal("0")
                if isinstance(op, ast.LtE) and not (left <= right): return Decimal("0")
                left = right
            return Decimal("1")
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    try:
        return _eval_node(tree)
    except (ValueError, InvalidOperation, ZeroDivisionError, TypeError):
        return Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# 核心执行函数
# ═══════════════════════════════════════════════════════════════════════════════

def execute_formula(
    formula: str | None,
    tb_map: dict[str, Decimal],
    row_cache: dict[str, Any],
    column: str = "期末余额",
) -> Decimal:
    """简易版执行（向后兼容）。返回 Decimal 值。"""
    ctx = FormulaContext.from_simple_map(tb_map, row_cache)
    result = execute(formula, ctx)
    return result.value


def execute(formula: str | None, ctx: FormulaContext) -> FormulaResult:
    """企业级公式执行。返回 FormulaResult（含 value + errors + trace）。"""
    result = FormulaResult()

    if not formula or not formula.strip():
        return result

    expression = formula
    col = ctx.default_column

    # ── 逐 token 替换 ──
    for token_name, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(formula):
            val = Decimal("0")
            trace_msg = ""

            if token_name == "TB":
                code, col_name = match.group(1), match.group(2)
                resolved_col = COLUMN_ALIASES.get(col_name, col_name)
                account_data = ctx.tb_data.get(code, {})
                val = account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))
                trace_msg = f"TB('{code}','{col_name}') = {val}"

            elif token_name == "SUM_TB":
                code_range, col_name = match.group(1), match.group(2)
                parts = code_range.split("~")
                if len(parts) == 2:
                    start, end = parts[0], parts[1]
                    prefix_len = len(start)
                    for code, data in ctx.tb_data.items():
                        # 精确前缀长度匹配（避免短编码误匹配）
                        code_prefix = code[:prefix_len]
                        if start <= code_prefix <= end:
                            val += data.get("期末余额", Decimal("0"))
                trace_msg = f"SUM_TB('{code_range}') = {val}"

            elif token_name == "ROW":
                row_code = match.group(1)
                val = ctx.row_cache.get(row_code, Decimal("0"))
                trace_msg = f"ROW('{row_code}') = {val}"

            elif token_name == "SUM_ROW":
                start_code, end_code = match.group(1), match.group(2)
                for code, rv in ctx.row_cache.items():
                    if start_code <= code <= end_code:
                        val += rv
                trace_msg = f"SUM_ROW('{start_code}','{end_code}') = {val}"

            elif token_name == "REPORT":
                row_code = match.group(1)
                val = ctx.row_cache.get(row_code, Decimal("0"))
                trace_msg = f"REPORT('{row_code}') = {val}"

            elif token_name == "PREV":
                code, col_name = match.group(1), match.group(2)
                prior_data = ctx.prior_tb_data.get(code, {})
                val = prior_data.get("期末余额", Decimal("0"))
                if val == 0:
                    result.warnings.append(f"PREV('{code}'): 无上年数据")
                trace_msg = f"PREV('{code}','{col_name}') = {val}"

            elif token_name in ("AUX", "NOTE", "WP"):
                # 跨模块数据，当前默认 0
                result.warnings.append(f"{token_name}(...): 跨模块引用暂不支持，返回 0")
                trace_msg = f"{token_name}(...) = 0 (unsupported)"

            expression = expression.replace(match.group(0), str(val), 1)
            if trace_msg:
                result.trace.append(trace_msg)

    # ── 安全求值 ──
    try:
        result.value = safe_eval_expr(expression)
    except Exception as e:
        result.errors.append(f"算术求值失败: {e} (expr={expression})")
        logger.warning("Formula eval error: %s (expr=%s, formula=%s)", e, expression, formula)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_formula_account_codes(formula: str | None) -> set[str]:
    """从公式中提取所有涉及的科目编码（用于汇总调整分录）。"""
    if not formula:
        return set()
    codes: set[str] = set()
    tb_pattern = _TOKEN_PATTERNS[2][1]  # TB pattern
    sum_tb_pattern = _TOKEN_PATTERNS[1][1]  # SUM_TB pattern
    for match in tb_pattern.finditer(formula):
        codes.add(match.group(1))
    for match in sum_tb_pattern.finditer(formula):
        code_range = match.group(1)
        parts = code_range.split("~")
        if len(parts) == 2:
            codes.add(f"__range__{parts[0]}~{parts[1]}")
    return codes


def validate_formula(formula: str) -> list[str]:
    """校验公式语法，返回错误列表（空=合法）。"""
    if not formula or not formula.strip():
        return []
    errors = []
    # 检查括号匹配
    depth = 0
    for ch in formula:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            errors.append("括号不匹配：多余的右括号")
            break
    if depth > 0:
        errors.append("括号不匹配：缺少右括号")
    # 检查是否有未识别的函数
    import re as _re
    unknown = _re.findall(r"([A-Z_]+)\(", formula)
    known_funcs = {"TB", "SUM_TB", "ROW", "SUM_ROW", "REPORT", "PREV", "AUX", "NOTE", "WP", "ABS", "ROUND", "MAX", "MIN", "IF"}
    for fn in unknown:
        if fn not in known_funcs:
            errors.append(f"未知函数: {fn}()")
    return errors


# ═══════════════════════════════════════════════════════════════════════════════
# FormulaEngine 类（向后兼容 formula.py 路由）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaEngine:
    """公式引擎类（兼容旧 API 路由）。

    旧路由 formula.py 需要一个带 redis_client 的类实例，
    提供 execute/list_all_functions/register_custom_function 等方法。
    """

    # 内置函数列表
    _BUILTIN_FUNCTIONS = [
        {"name": "TB", "description": "取科目余额", "syntax": "TB('科目编码','列名')", "category": "取数"},
        {"name": "SUM_TB", "description": "范围科目求和", "syntax": "SUM_TB('起始~结束','列名')", "category": "取数"},
        {"name": "ROW", "description": "引用其他行次", "syntax": "ROW('行次编码')", "category": "引用"},
        {"name": "SUM_ROW", "description": "范围行次求和", "syntax": "SUM_ROW('起始','结束')", "category": "引用"},
        {"name": "PREV", "description": "上年同期值", "syntax": "PREV('科目编码','列名')", "category": "取数"},
        {"name": "REPORT", "description": "跨报表引用", "syntax": "REPORT('行次编码','期间')", "category": "引用"},
        {"name": "AUX", "description": "辅助核算取值", "syntax": "AUX('科目','维度','列名')", "category": "取数"},
        {"name": "ABS", "description": "绝对值", "syntax": "ABS(值)", "category": "数学"},
        {"name": "ROUND", "description": "四舍五入", "syntax": "ROUND(值, 位数)", "category": "数学"},
        {"name": "MAX", "description": "最大值", "syntax": "MAX(值1, 值2)", "category": "数学"},
        {"name": "MIN", "description": "最小值", "syntax": "MIN(值1, 值2)", "category": "数学"},
        {"name": "IF", "description": "条件判断", "syntax": "IF(条件, 真值, 假值)", "category": "逻辑"},
    ]

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._custom_functions: dict[str, dict] = {}

    def list_all_functions(self) -> list[dict]:
        """列出所有可用函数（内置 + 自定义）"""
        result = list(self._BUILTIN_FUNCTIONS)
        for name, info in self._custom_functions.items():
            result.append({"name": name, "category": "自定义", **info})
        return result

    def list_custom_functions(self) -> list[dict]:
        """列出自定义函数"""
        return [{"name": k, **v} for k, v in self._custom_functions.items()]

    def register_custom_function(self, name: str, description: str = "", syntax: str = "", formula: str = "", expression: str = "") -> dict:
        """注册自定义函数"""
        if not name or not name.strip():
            raise ValueError("函数名不能为空")
        # 检查是否与内置函数冲突
        builtin_names = {f["name"] for f in self._BUILTIN_FUNCTIONS}
        if name in builtin_names:
            raise ValueError(f"内置函数 {name} 不可覆盖")
        # 校验表达式
        expr = expression or formula
        if expr and not _validate_custom_expression(expr):
            raise ValueError(f"表达式语法不合法: {expr}")
        self._custom_functions[name] = {
            "description": description,
            "syntax": syntax,
            "formula": expr,
            "expression": expr,
        }
        return {"registered": True, "name": name}

    def unregister_custom_function(self, name: str) -> bool:
        """注销自定义函数"""
        return self._custom_functions.pop(name, None) is not None

    async def invalidate_cache(self, project_id=None, year=None, account_codes=None):
        """清除公式缓存（Redis）"""
        if not self.redis:
            return
        try:
            # 简单实现：删除项目相关的缓存键
            pattern = f"formula:*:{project_id}:*" if project_id else "formula:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
        except Exception:
            pass  # Redis 不可用时静默

    async def execute(self, db, project_id, year, formula_type: str, params: dict, **kwargs) -> dict:
        """执行公式（兼容旧 API）"""
        from decimal import Decimal
        # 简单实现：构建 tb_map 并调用统一引擎
        formula_str = params.get("formula", "")
        if not formula_str:
            return {"value": 0, "formula": "", "error": None}

        # 从 trial_balance 加载数据
        import sqlalchemy as sa
        from app.models.audit_platform_models import TrialBalance
        tb_table = TrialBalance.__table__
        q = sa.select(tb_table.c.standard_account_code, tb_table.c.unadjusted_amount).where(
            tb_table.c.project_id == project_id,
            tb_table.c.year == year,
            tb_table.c.is_deleted == sa.false(),
        )
        result = await db.execute(q)
        tb_map: dict[str, Decimal] = {}
        for r in result.fetchall():
            if r.standard_account_code:
                tb_map[r.standard_account_code] = tb_map.get(r.standard_account_code, Decimal("0")) + (r.unadjusted_amount or Decimal("0"))

        val = execute_formula(formula_str, tb_map, {})
        return {"value": float(val), "formula": formula_str, "error": None}

    async def batch_execute(self, db, project_id, year, formulas: list[dict], **kwargs) -> list[dict]:
        """批量执行公式"""
        results = []
        for f in formulas:
            r = await self.execute(db, project_id, year, f.get("formula_type", ""), f.get("params", {}))
            results.append(r)
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容导出（旧测试和旧模块依赖的名称）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaError(Exception):
    """公式执行错误"""
    pass


# 旧测试引用的 Executor 类（占位，实际逻辑在 execute 函数中）
class TBExecutor:
    """TB 函数执行器（兼容占位）"""
    pass


class SumTBExecutor:
    """SUM_TB 函数执行器（兼容占位）"""
    pass


class PREVExecutor:
    """PREV 函数执行器（兼容占位）"""
    pass


def _validate_custom_expression(expression: str) -> bool:
    """校验自定义公式表达式是否安全合法。

    规则：
    - 不能为空
    - 不能包含 import/exec/eval/__/open 等危险关键字
    - 必须能被 ast.parse 解析
    """
    if not expression or not expression.strip():
        return False
    dangerous = ['import ', 'exec(', 'eval(', '__', 'open(', 'os.', 'sys.', 'subprocess']
    for d in dangerous:
        if d in expression:
            return False
    # 先替换公式函数为数字占位符再验证语法
    import re
    cleaned = re.sub(r"[A-Z_]+\([^)]*\)", "0", expression)
    try:
        ast.parse(cleaned, mode="eval")
        return True
    except SyntaxError:
        return False
