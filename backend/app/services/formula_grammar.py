"""formula_grammar.py — 公式 token 正则 + 函数名集 + arity 映射（单一来源）

所有使用公式 token 解析的模块统一从此处导入，避免多处重复定义。
两类正则：
  - 严格模式（无空格容忍）：formula_engine / report_engine 使用
  - 宽松模式（允许空格）：address_registry 使用
"""

from __future__ import annotations

import re

# ═══════════════════════════════════════════════════════════════════════════════
# 严格 token 正则（formula_engine / report_engine 求值路径）
# ═══════════════════════════════════════════════════════════════════════════════

TB_PATTERN = re.compile(r"TB\('([^']+)','([^']+)'\)")
SUM_TB_PATTERN = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
ROW_PATTERN = re.compile(r"ROW\('([^']+)'\)")
SUM_ROW_PATTERN = re.compile(r"SUM_ROW\('([^']+)','([^']+)'\)")
REPORT_PATTERN = re.compile(r"REPORT\('([^']+)','([^']+)'\)")
NOTE_PATTERN = re.compile(r"NOTE\('([^']+)','([^']+)','([^']+)'\)")
WP_PATTERN = re.compile(r"WP\('([^']+)','([^']+)'\)")
PREV_PATTERN = re.compile(r"PREV\('([^']+)','([^']+)'\)")
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
    'WP': re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
    'AUX': re.compile(r"AUX\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)"),
    'PREV': re.compile(r"PREV\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"),
}

# ═══════════════════════════════════════════════════════════════════════════════
# 函数名集合 + arity 映射
# ═══════════════════════════════════════════════════════════════════════════════

FORMULA_FUNCTION_NAMES: frozenset[str] = frozenset({
    "TB", "SUM_TB", "ROW", "SUM_ROW", "REPORT",
    "NOTE", "WP", "PREV", "AUX",
    "ABS", "ROUND", "MAX", "MIN", "IF",
})

FORMULA_ARITY: dict[str, int | None] = {
    "TB": 2,
    "SUM_TB": 2,
    "ROW": 1,
    "SUM_ROW": 2,
    "REPORT": 2,
    "NOTE": 3,
    "WP": 2,
    "PREV": 2,
    "AUX": 3,
    "ABS": 1,
    "ROUND": 2,
    "MAX": 2,
    "MIN": 2,
    "IF": 3,
}
