"""公式三态/四态分类（P0-项2 · spec d4-dual-mode-formula-governance）。

区分四态（与 preset/custom/stale/执行态**正交**，不混用）：

  - ``ok``       — 语法合法且只用白名单函数，可安全求值。
  - ``missing``  — 目标 key 不存在（调用方查不到该 (wp,stable_sheet_key,row,field) 公式）。
  - ``damaged``  — 表达式存在（非空）但 AST 解析失败（结构坏）。
  - ``blocked``  — 结构合法但含**非白名单**内容：未注册函数 / ``eval``/``exec`` 等危险标识 /
                   URL / 外链（``http(s)://`` / ``file:`` / ``//`` UNC）。**不静默返 0 冒充正常**，
                   保留原始表达式作证据。

单一真源：引擎（`_execute_ast` 标 blocked/damaged）、导入/保存入口、PBT 三处共用本模块，
不各写一份分类逻辑。
"""

from __future__ import annotations

import re
from enum import Enum


class FormulaState(str, Enum):
    OK = "ok"
    MISSING = "missing"
    DAMAGED = "damaged"
    BLOCKED = "blocked"


#: blocked 危险标识（大小写不敏感）：代码执行/反射/导入/属性穿透 + 外链。
#: 这些绝不是报表 DSL 的合法函数，出现即视为注入/越权，拒绝仅存值。
_DANGEROUS_TOKENS = (
    "eval", "exec", "compile", "__import__", "import ", "os.", "sys.",
    "subprocess", "open(", "globals", "locals", "getattr", "setattr", "lambda",
)

#: 外链/URL 模式：http(s)/ftp/file scheme + UNC(``\\host``) + 协议相对(``//host``)。
_URL_RE = re.compile(r"(?:https?://|ftp://|file:|\\\\[^\s]|(?<![:/])//[A-Za-z0-9.-]+)", re.IGNORECASE)

#: DSL 函数调用形态：大写标识后紧跟 ``(``。用于抽取公式引用的函数名做白名单核对。
_FUNC_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\s*\(")


def _dangerous_or_external(formula: str) -> bool:
    """公式是否含危险标识或外链（→ blocked）。"""
    low = formula.lower()
    if any(tok in low for tok in _DANGEROUS_TOKENS):
        return True
    if _URL_RE.search(formula):
        return True
    return False


def classify_formula(
    formula: str | None,
    *,
    key_exists: bool = True,
    known_functions: set[str] | None = None,
) -> FormulaState:
    """把一条公式分类为四态之一（纯函数，无求值副作用）。

    Args:
        formula: 公式表达式（None/空 → 视 key 是否存在判 missing/ok）。
        key_exists: 目标 key 是否存在。False → ``missing`` 优先（未找到该公式定义）。
        known_functions: 白名单函数名集合。缺省从 formula_engine 的 FunctionRegistry 取
            （单一真源），避免维护第二份函数清单。

    判定顺序（互斥，不混淆）：
        1. key 不存在 → missing。
        2. 空表达式（key 存在但无内容）→ ok（空公式合法，等价无计算）。
        3. 含危险标识/外链 → blocked。
        4. AST 解析失败 → damaged。
        5. 引用了非白名单函数 → blocked。
        6. 其余 → ok。
    """
    if not key_exists:
        return FormulaState.MISSING

    if not formula or not formula.strip():
        return FormulaState.OK

    text = formula.strip()

    # ③ 危险标识/外链 —— 结构可能合法，但语义越权，直接 blocked（先于解析，避免"坏结构掩盖越权"）
    if _dangerous_or_external(text):
        return FormulaState.BLOCKED

    # 白名单函数集合（默认取引擎 FunctionRegistry，单一真源）
    if known_functions is None:
        from app.services.formula_engine import _REGISTRY
        known_functions = _REGISTRY.known_function_names()

    # ④ AST 解析 —— 失败即 damaged
    from app.services.formula_engine import FormulaParseError, parse_to_ast

    try:
        parse_to_ast(text)
    except FormulaParseError:
        return FormulaState.DAMAGED
    except Exception:
        # 词法/其它解析异常同样归 damaged（结构坏），不冒充 ok
        return FormulaState.DAMAGED

    # ⑤ 非白名单函数 → blocked
    for m in _FUNC_CALL_RE.finditer(text):
        name = m.group(1)
        if name not in known_functions:
            return FormulaState.BLOCKED

    return FormulaState.OK
