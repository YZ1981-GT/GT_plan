"""formula_grammar.py — 公式 token 正则 + 函数名集 + arity 映射 + WP/PREV 解析器（单一来源）

所有使用公式 token 解析的模块统一从此处导入，避免多处重复定义。
两类正则：
  - 严格模式（无空格容忍）：formula_engine / report_engine 使用
  - 宽松模式（允许空格）：address_registry 使用

ACNR M1 扩展（R10.2, R10.5）：
  - parse_wp_formula(): 真实解析器，支持 WP()/PREV() 2 参与 3 参
  - ParsedFormula dataclass: 解析结果结构化表示
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# 严格 token 正则（formula_engine / report_engine 求值路径）
# ═══════════════════════════════════════════════════════════════════════════════

TB_PATTERN = re.compile(r"TB\('([^']+)','([^']+)'\)")
SUM_TB_PATTERN = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
ROW_PATTERN = re.compile(r"ROW\('([^']+)'\)")
SUM_ROW_PATTERN = re.compile(r"SUM_ROW\('([^']+)','([^']+)'\)")
REPORT_PATTERN = re.compile(r"REPORT\('([^']+)','([^']+)'\)")
NOTE_PATTERN = re.compile(r"NOTE\('([^']+)','([^']+)','([^']+)'\)")
WP_PATTERN = re.compile(r"WP\('([^']+)','([^']+)'(?:,'([^']+)')?\)")
PREV_PATTERN = re.compile(r"PREV\('([^']+)','([^']+)'(?:,'([^']+)')?\)")
AUX_PATTERN = re.compile(r"AUX\('([^']+)','([^']*?)','([^']+)'\)")

# 有序 token 列表（SUM_ROW/SUM_TB 必须在 ROW/TB 之前以避免部分匹配）
TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SUM_ROW", SUM_ROW_PATTERN),
    ("SUM_TB", SUM_TB_PATTERN),
    ("TB", TB_PATTERN),
    ("ROW", ROW_PATTERN),
    ("REPORT", REPORT_PATTERN),
    ("PREV", PREV_PATTERN),
    ("AUX", AUX_PATTERN),
    ("NOTE", NOTE_PATTERN),
    ("WP", WP_PATTERN),
]

# ═══════════════════════════════════════════════════════════════════════════════
# 宽松 token 正则（address_registry，允许参数间可选空格）
# ═══════════════════════════════════════════════════════════════════════════════

RELAXED_FORMULA_PATTERNS: dict[str, re.Pattern[str]] = {
    'TB': re.compile(r"TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'SUM_TB': re.compile(r"SUM_TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'ROW': re.compile(r"ROW\(\s*'([^']+)'\s*\)"),
    'SUM_ROW': re.compile(r"SUM_ROW\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'REPORT': re.compile(r"REPORT\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'NOTE': re.compile(r"NOTE\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'WP': re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'AUX': re.compile(r"AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'PREV': re.compile(r"PREV\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# 函数名集合 + arity 映射
# ═══════════════════════════════════════════════════════════════════════════════

FORMULA_FUNCTION_NAMES: frozenset[str] = frozenset({
    "TB", "SUM_TB", "ROW", "SUM_ROW", "REPORT",
    "NOTE", "WP", "PREV", "AUX",
    "ABS", "ROUND", "MAX", "MIN", "IF",
})

FORMULA_ARITY: dict[str, int | list[int] | None] = {
    "TB": 2,
    "SUM_TB": 2,
    "ROW": 1,
    "SUM_ROW": 2,
    "REPORT": 2,
    "NOTE": 3,
    "WP": [2, 3],  # grammar_v1: arities=[2,3], 2参 custom_flat / 3参 standard
    "PREV": [2, 3],  # grammar_v1: arities=[2,3], 同 WP 结构
    "AUX": 3,
    "ABS": 1,
    "ROUND": 2,
    "MAX": 2,
    "MIN": 2,
    "IF": 3,
}


# ═══════════════════════════════════════════════════════════════════════════════
# WP()/PREV() 真实解析器（ACNR M1, R10.2, R10.5）
#
# 按 grammar_v1.json 定义：
#   WP:   { arities: [2, 3], third_arg: "semantic_or_cell", roundtrip: true }
#   PREV: { arities: [2, 3], third_arg: "semantic_or_cell", roundtrip: true }
#
# 2 参 (custom_flat): WP('CUST-01', 'B7') 或 WP('D2', '明细表D2-2')
# 3 参 (standard):    WP('D2', '明细表D2-2', 'E100') 或 WP('D2', '明细表D2-2', '合计行-期末余额')
# ═══════════════════════════════════════════════════════════════════════════════


class FormulaProfile(str, Enum):
    """URI profile 类型，对应 grammar_v1.json uri_profiles。"""

    STANDARD = "standard"
    CUSTOM_FLAT = "custom_flat"


@dataclass(frozen=True, slots=True)
class ParsedFormula:
    """WP()/PREV() 解析结果。

    Attributes:
        func_name: 函数名（"WP" 或 "PREV"）
        args: 解析出的参数列表（去除引号后的纯字符串）
        arity: 参数个数（2 或 3）
        profile: URI profile 类型（"standard" 或 "custom_flat"）
    """

    func_name: str
    args: list[str] = field(default_factory=list)
    arity: int = 0
    profile: str = ""


class FormulaParseError(ValueError):
    """公式解析失败异常。"""

    pass


# ─── 词法分析（Tokenizer）────────────────────────────────────────────────────


class _TokenType(str, Enum):
    FUNC_NAME = "FUNC_NAME"  # WP / PREV
    LPAREN = "LPAREN"  # (
    RPAREN = "RPAREN"  # )
    COMMA = "COMMA"  # ,
    STRING = "STRING"  # 带引号的字符串值
    WS = "WS"  # 空白（跳过）
    EOF = "EOF"


@dataclass(slots=True)
class _Token:
    type: _TokenType
    value: str
    pos: int


def _tokenize(formula_ref: str) -> list[_Token]:
    """词法分析：将 formula_ref 字符串拆分为 token 序列。

    支持：
    - 函数名 WP / PREV（大小写不敏感匹配后规范化为大写）
    - 单引号字符串 '...'（支持 \\' 和 \\\\ 转义）
    - 双引号字符串 "..."（支持 \\" 和 \\\\ 转义）
    - 括号与逗号
    - 空白（跳过）
    """
    tokens: list[_Token] = []
    i = 0
    length = len(formula_ref)

    while i < length:
        ch = formula_ref[i]

        # 空白
        if ch in (" ", "\t", "\r", "\n"):
            i += 1
            continue

        # 函数名（WP / PREV）
        if ch.isalpha():
            start = i
            while i < length and formula_ref[i].isalpha():
                i += 1
            word = formula_ref[start:i].upper()
            if word in ("WP", "PREV"):
                tokens.append(_Token(_TokenType.FUNC_NAME, word, start))
            else:
                raise FormulaParseError(
                    f"位置 {start}: 不支持的函数名 '{formula_ref[start:i]}'，"
                    f"仅支持 WP/PREV"
                )
            continue

        # 左括号
        if ch == "(":
            tokens.append(_Token(_TokenType.LPAREN, "(", i))
            i += 1
            continue

        # 右括号
        if ch == ")":
            tokens.append(_Token(_TokenType.RPAREN, ")", i))
            i += 1
            continue

        # 逗号
        if ch == ",":
            tokens.append(_Token(_TokenType.COMMA, ",", i))
            i += 1
            continue

        # 字符串字面量（单引号或双引号）
        if ch in ("'", '"'):
            quote_char = ch
            start = i
            i += 1  # 跳过开始引号
            value_chars: list[str] = []
            while i < length:
                c = formula_ref[i]
                if c == "\\" and i + 1 < length:
                    # 转义字符
                    next_c = formula_ref[i + 1]
                    if next_c == quote_char:
                        value_chars.append(quote_char)
                        i += 2
                    elif next_c == "\\":
                        value_chars.append("\\")
                        i += 2
                    else:
                        value_chars.append(c)
                        i += 1
                elif c == quote_char:
                    # 结束引号
                    i += 1
                    break
                else:
                    value_chars.append(c)
                    i += 1
            else:
                raise FormulaParseError(
                    f"位置 {start}: 字符串未闭合（缺少匹配的 {quote_char}）"
                )
            tokens.append(_Token(_TokenType.STRING, "".join(value_chars), start))
            continue

        raise FormulaParseError(f"位置 {i}: 无法识别的字符 '{ch}'")

    tokens.append(_Token(_TokenType.EOF, "", length))
    return tokens


# ─── 语法分析（Parser）────────────────────────────────────────────────────────


def _parse_tokens(tokens: list[_Token]) -> ParsedFormula:
    """语法分析：从 token 序列构造 ParsedFormula。

    预期语法：FUNC_NAME '(' STRING (',' STRING)* ')'

    校验：
    - 必须有且仅有一个函数调用
    - 参数数量为 2 或 3
    - 函数名必须为 WP 或 PREV
    """
    pos = 0

    def current() -> _Token:
        return tokens[pos] if pos < len(tokens) else tokens[-1]

    def expect(tt: _TokenType) -> _Token:
        nonlocal pos
        tok = current()
        if tok.type != tt:
            raise FormulaParseError(
                f"位置 {tok.pos}: 期望 {tt.value}，实际为 '{tok.value}'"
            )
        pos += 1
        return tok

    # 解析函数名
    func_tok = expect(_TokenType.FUNC_NAME)
    func_name = func_tok.value

    # 解析左括号
    expect(_TokenType.LPAREN)

    # 解析参数列表
    args: list[str] = []
    if current().type == _TokenType.STRING:
        args.append(current().value)
        pos += 1
        while current().type == _TokenType.COMMA:
            pos += 1  # 跳过逗号
            if current().type != _TokenType.STRING:
                raise FormulaParseError(
                    f"位置 {current().pos}: 逗号后期望字符串参数，"
                    f"实际为 '{current().value}'"
                )
            args.append(current().value)
            pos += 1
    elif current().type != _TokenType.RPAREN:
        raise FormulaParseError(
            f"位置 {current().pos}: 期望字符串参数或右括号，"
            f"实际为 '{current().value}'"
        )

    # 解析右括号
    expect(_TokenType.RPAREN)

    # 应该到达 EOF
    if current().type != _TokenType.EOF:
        raise FormulaParseError(
            f"位置 {current().pos}: 函数调用后有多余内容 '{current().value}'"
        )

    # 校验 arity
    arity = len(args)
    if arity not in (2, 3):
        raise FormulaParseError(
            f"WP()/PREV() 仅支持 2 参或 3 参，实际提供了 {arity} 个参数"
        )

    # 确定 profile
    # 3 参 → standard（parent, sheet_name, cell|semantic）
    # 2 参 → 按 grammar_v1.json 规则：
    #   - 如果第一参匹配标准码 ^[A-S]\d 且第二参看起来是 sheet_name → standard sheet-level
    #   - 否则 → custom_flat
    #   注意：2 参 standard（sheet 级，无 cell）也是合法的
    #   根据 grammar_v1.json：standard wp_arity=[2,3], custom_flat wp_arity=[2]
    #   区分逻辑：2 参的 profile 判定依赖上下文（需 catalog），这里做最佳猜测
    if arity == 3:
        profile = FormulaProfile.STANDARD.value
    else:
        # 2 参：判断是 standard sheet-level 还是 custom_flat
        # 按 grammar_v1.json 规则：custom_flat 用于 CUST/单 sheet 自定义
        # standard 第二参是 sheet_name（中文或含 - 的编码），custom_flat 第二参是 cell（如 B7/E100）
        # 启发式：如果第二参看起来是 A1 坐标（1~3 字母 + 数字），倾向 custom_flat
        second_arg = args[1]
        _CELL_PATTERN = re.compile(r"^[A-Za-z]{1,3}\d+$")
        if _CELL_PATTERN.match(second_arg):
            profile = FormulaProfile.CUSTOM_FLAT.value
        else:
            # 第二参看起来是 sheet_name 或 sheet_code → standard (sheet-level)
            profile = FormulaProfile.STANDARD.value

    return ParsedFormula(
        func_name=func_name,
        args=args,
        arity=arity,
        profile=profile,
    )


# ─── 公开 API ────────────────────────────────────────────────────────────────


def parse_wp_formula(formula_ref: str) -> ParsedFormula:
    """解析 WP(...) 或 PREV(...) 公式引用，返回结构化结果。

    这是 ACNR M1 的核心解析器（R10.2, R10.5），支持：
    - 3 参 (standard): WP('D2', '明细表D2-2', 'E100')
    - 3 参 (standard semantic): WP('D2', '明细表D2-2', '合计行-期末余额')
    - 2 参 (custom_flat): WP('CUST-01', 'B7')
    - 2 参 (standard sheet-level): WP('D2', '明细表D2-2')
    - PREV 与 WP 相同的 2/3 参结构

    支持单引号和双引号字符串、参数间空白、转义字符。

    Args:
        formula_ref: 原始公式引用字符串，如 "WP('D2','明细表D2-2','E100')"

    Returns:
        ParsedFormula 实例

    Raises:
        FormulaParseError: 公式格式不合法

    Examples:
        >>> parse_wp_formula("WP('D2','明细表D2-2','E100')")
        ParsedFormula(func_name='WP', args=['D2', '明细表D2-2', 'E100'], arity=3, profile='standard')

        >>> parse_wp_formula("WP('CUST-01','B7')")
        ParsedFormula(func_name='WP', args=['CUST-01', 'B7'], arity=2, profile='custom_flat')

        >>> parse_wp_formula("PREV('D2', '明细表D2-2', '合计行-期末余额')")
        ParsedFormula(func_name='PREV', args=['D2', '明细表D2-2', '合计行-期末余额'], arity=3, profile='standard')
    """
    if not formula_ref or not formula_ref.strip():
        raise FormulaParseError("formula_ref 不能为空")

    formula_ref = formula_ref.strip()

    # 快速前置检查
    upper_ref = formula_ref.upper()
    if not (upper_ref.startswith("WP(") or upper_ref.startswith("PREV(")):
        raise FormulaParseError(
            f"仅支持 WP()/PREV() 函数，收到: '{formula_ref[:20]}...'"
        )

    tokens = _tokenize(formula_ref)
    return _parse_tokens(tokens)
