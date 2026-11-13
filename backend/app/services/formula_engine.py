"""统一公式引擎 — 企业级版本（L1 内核）

所有报表公式计算的唯一执行器。

设计原则：
- 纯函数，不依赖 async/db session
- 插件式函数注册（新增函数只需注册 handler）
- 返回 FormulaResult（含 value + errors + trace）
- 多列支持（TB 第二参数指定列名）
- 上年数据支持（PREV 函数）
- 公式解析缓存（同一公式不重复解析）

parse 层（Task 3 升级）：
- 递归下降 AST 解析（从 formula_parse_utils 并入）替换脆弱 regex token 替换
- 并行 diff 验证：新 AST 求值 vs 旧 regex 求值一致后才切换
- 保留 regex 路径一个版本周期作降级（_PARSE_MODE 控制）
- 对嵌套 PREV(TB(...)) / IF(TB>0, ROW, 0) 等更严谨

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
import os
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Callable, Protocol, runtime_checkable

from app.services.formula_arity import arity_problem, ast_budget_problem, call_argc

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Parse 模式控制（Task 3：递归下降替换 regex）
# ═══════════════════════════════════════════════════════════════════════════════
# "ast"   = 新递归下降 AST 求值（**生产默认**，并行 diff 验证已通过 + Decimal 全程精确）
# "regex" = 旧 regex token 替换（降级/调试路径，env-var 可切换）
# "parallel" = 并行跑两路径做 diff 对照（调试用，env-var 可切换）
_PARSE_MODE: str = os.environ.get("FORMULA_PARSE_MODE", "ast")


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类型定义
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FormulaResult:
    """公式执行结果。

    ``blocked``（P0-项2）：公式结构合法但含**非白名单**内容（未注册函数 / eval/exec /
    URL / 外链）。失败结果的 ``value`` 为 ``None``，``ok`` 为 False 且分类明确为
    blocked —— **不静默返 0 冒充正常**，供调用方区分「配置/注入问题」与「诚实的 0」。
    成功的真实零值仍使用 ``Decimal("0")``；调用方必须先判 ``ok`` 再消费 ``value``。
    """
    value: Decimal | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)  # 取数轨迹（审计用）
    blocked: bool = False  # 含非白名单函数/危险标识/外链（P0-项2）
    failure_kind: str | None = None  # None / business / technical；不按展示文案分类
    technical_error: Exception | None = field(default=None, repr=False, compare=False)

    def record_error(self, error: Exception, message: str | None = None) -> None:
        """保留异常对象与显式 cause 链；展示错误和重试分类相互独立。"""
        self.value = None
        self.errors.append(str(error) if message is None else message)
        if formula_technical_error(error):
            self.failure_kind = "technical"
            if self.technical_error is None:
                self.technical_error = error
        elif self.failure_kind != "technical":
            self.failure_kind = "business"

    def raise_for_technical_error(self) -> None:
        """strict 边界调用：重抛实际捕获对象，保留其 traceback / __cause__。"""
        if self.technical_error is not None:
            raise self.technical_error

    @property
    def ok(self) -> bool:
        return self.value is not None and len(self.errors) == 0 and not self.blocked

    @property
    def state(self) -> str:
        """求值态分类（ok/damaged/blocked）。missing 由调用方按 key 存在性判定，不在此。"""
        if self.blocked:
            return "blocked"
        if self.errors and any("解析失败" in e for e in self.errors):
            return "damaged"
        if self.errors:
            return "error"
        if self.value is None:
            return "error"
        return "ok"


@dataclass
class FormulaContext:
    """公式执行上下文（L2 编排层预载、传给 L1 内核的同步数据快照）。

    L1 内核纯函数所需的全部数据都在此对象内（无 DB/async 耦合）。各业务域由
    L2 编排层经 L3 AmountResolver 批量取数后填充对应字段，再调 ``execute``。
    """
    # 科目编码 → {列名: 金额}（试算表 TB / SUM_TB，支持多列取数）
    tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 行次编码 → 来源快照（保留 NULL/原值，在实际引用时校验，不把缺数转成零）
    row_cache: dict[str, Any] = field(default_factory=dict)
    # 上期报表行次编码 → 来源快照（供 REPORT('行次','上期') 引用）
    prior_row_cache: dict[str, Any] = field(default_factory=dict)
    # 上年科目数据（供 PREV 两参引用）
    prior_tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # PREV 三参（上年同底稿取数）预载值：(底稿, 表, 字段) → 值；取不到的原因另存，L1 据此报错、不按 0
    prev_wp_data: dict[tuple[str, str, str], Decimal] = field(default_factory=dict)
    prev_wp_missing: dict[tuple[str, str, str], str] = field(default_factory=dict)
    # 附注数据源（供 NOTE 函数）：section_code → {field_name: 金额}
    note_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 底稿数据源（供 WP 函数）：wp_code → {column: 金额}
    wp_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 辅助核算数据源（供 AUX 函数）：account_code → {辅助项: 金额}
    aux_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 调整额数据源（供 ADJ 函数）：account_code → {aje_net/aje_dr/aje_cr/rje_*: 金额}
    #
    # 结构与 `adjustment_amount_source.adj_net_batch` 的返回值**逐键相同**——
    # L2 直接塞批量取数结果，禁做键名转换（转换点就是漂移点）。
    # 🔴 与 `tb_data["AJE调整"]` 的语义差异：本字段是**实时汇总**，tb_data 那两键
    # 是 `trial_balance` 的**持久化快照**。两者可以不等 —— 不等即快照过期，
    # 那是需求 3.3 要暴露的信号，不是本字段要掩盖的事。
    adj_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 默认列名
    default_column: str = "期末余额"
    # ── 底稿预填充扩展（spec formula-execution-path-convergence Phase 1） ──
    # 序时账发生额：key = "{account}:{direction}:{period}" → Decimal
    ledger_data: dict[str, Decimal] = field(default_factory=dict)
    # 序时账明细行：key = "{account}:{period}:{amount_filter}" → [{voucher_date, ...}]
    ledger_detail_data: dict[str, list] = field(default_factory=dict)
    # 序时账笔数：key = "{account}:{period}" → int
    ledger_count_data: dict[str, int] = field(default_factory=dict)
    # TB_AUX 汇总：key = "{account}:{aux_type}:{column}" → Decimal
    tb_aux_data: dict[str, Decimal] = field(default_factory=dict)
    # 仅 execute(strict=True) 的复制快照启用；默认保持旧来源取值策略。
    strict: bool = False

    # ── 便捷构造方法 ──
    @classmethod
    def from_simple_map(
        cls,
        tb_map: dict[str, Decimal],
        row_cache: dict[str, Any] | None = None,
        prior_map: dict[str, Decimal] | None = None,
        adj_map: dict[str, dict[str, Decimal]] | None = None,
    ) -> "FormulaContext":
        """从简单的 科目→金额 字典构建上下文（向后兼容）。

        ``adj_map``（可选）：``adj_net_batch`` 的返回值。传入时一个参数服务两条
        取数路径 —— 往 ``tb_data`` 补 ``AJE调整``/``RJE调整`` 两键（供 ``TB()``）
        并原样塞进 ``adj_data``（供 ``ADJ()``），键名来源单一避免两处各写一份。

        🔴 **缺省时不产这两键**（需求 3.4）：既有 3 键的值与语义逐字不变，
        只增不改，既有调用方零回归。

        🔴 **本方法只产 3(+2) 键，不是完整预载**。需要全部 14 个注册列名的调用方
        走 `tb_formula_context.build_tb_formula_data` —— 方法名里的 "simple" 就是
        这个意思，扩成全键会让它变成第二份预载实现。
        """
        tb_data = {code: {"期末余额": val, "审定数": val, "未审数": val} for code, val in tb_map.items()}
        if adj_map:
            for code, adj in adj_map.items():
                # 只给 tb_map 里存在的科目补键：本方法的 tb_data 分母由 tb_map 决定，
                # 凭 adj_map 无中生有会让 `SUM_TB` 的科目区间多出 tb_map 没有的科目。
                if code in tb_data:
                    tb_data[code]["AJE调整"] = adj.get("aje_net", Decimal("0"))
                    tb_data[code]["RJE调整"] = adj.get("rje_net", Decimal("0"))
        prior_data = {}
        if prior_map:
            prior_data = {code: {"期末余额": val} for code, val in prior_map.items()}
        rc = dict(row_cache or {})
        return cls(
            tb_data=tb_data,
            row_cache=rc,
            prior_tb_data=prior_data,
            adj_data=dict(adj_map) if adj_map else {},
        )


# ── 列名映射（中文 → 标准字段名） ──
#
# 🔴 规范字段名（值）**必须**与已交付共享件
# `four_table/occurrence_by_standard_code.py` 的 `DEBIT_KEY`/`CREDIT_KEY` 一致
# （`本期借方`/`本期贷方`）—— 该件的守卫
# `test_formula_column_alias_coverage::test_occurrence_keys_match_engine_standard_fields`
# 断言 `DEBIT_KEY in set(COLUMN_ALIASES.values())`。写成 `借方发生额` 会立刻打红。
#
# 发生额四键的数据来源 = `tb_balance.debit_amount` / `credit_amount`
# （`trial_balance` **没有**发生额列，只有余额与调整），经
# `aggregate_occurrence()` 按标准码归集（含叶子聚合，父子不双算）。
COLUMN_ALIASES: dict[str, str] = {
    # ── 余额类（既有 8 键；「未审数」自 ADR-FHIC-18 起是规范列 ← unadjusted_amount，原指向期末余额 = 审定数） ──
    "期末余额": "期末余额",
    "审定数": "期末余额",
    "年初余额": "年初余额",
    "期初余额": "年初余额",
    "未审数": "未审数",
    "本期发生额": "本期发生额",
    "RJE调整": "RJE调整",
    "AJE调整": "AJE调整",
    # ── 发生额类（新增；两两同义，规范名 = 共享件 DEBIT_KEY/CREDIT_KEY） ──
    "本期借方": "本期借方",
    "借方发生额": "本期借方",
    "本期借方发生额": "本期借方",
    "本期贷方": "本期贷方",
    "贷方发生额": "本期贷方",
    "本期贷方发生额": "本期贷方",
}

#: 属「发生额」语义的**规范字段名**（不是别名）。单一真源，供 `tb_data`
#: 构造点与守卫共同引用，禁两处各写一份。
OCCURRENCE_COLUMNS: frozenset[str] = frozenset({"本期借方", "本期贷方", "本期发生额"})


def is_unregistered_column(col_name: str) -> bool:
    """列名是否**未注册**（配置错）。

    与「已注册但该科目无数据」（诚实的 0）区分开的唯一判据。调用方据此决定
    记 ``errors``（配置错）还是只记 ``trace``（数据缺）。

    🔴 `_resolve_tb_column` 的返回值**恒为 Decimal**（两种缺失态都返 0），
    不用哨兵对象 —— 因为 ``TB()`` 的结果要参与四则运算，哨兵会污染算术；
    且既有守卫 `test_resolver_distinguishes_unregistered_from_missing_data`
    按「返 0 + trace 区分」这一契约断言。
    """
    return col_name not in COLUMN_ALIASES


class FormulaColumnError(Exception):
    """公式引用了**未注册的列名**（配置错，不是数据缺失）。

    由 `_handle_tb` 抛出、`_execute_ast` 捕获后记入 ``FormulaResult.errors``。

    🔴 **必须是独立异常类**：`_execute_ast` 的兜底 ``except Exception`` 会把任何
    异常记成「AST 求值失败」，那样「列名拼错」与「解析崩溃」在 errors 里不可区分，
    审计师无法据此定位是公式写错还是引擎坏了（R3.2 要求二者可区分）。
    """


class FormulaEvalError(Exception):
    """求值失败：除零、ROW 缺行、未注册函数、参数个数不足、AST 超预算。

    与 :class:`FormulaColumnError` 同处捕获、记入 ``FormulaResult.errors``；失败结果的
    ``value`` 为 ``None``，调用方必须先判 ``ok``，不能把失败伪装成 0。
    """


class FormulaBusinessError(FormulaEvalError):
    """在已知校验边界产生的业务失败；其转换 cause 不是重试信号。"""


def formula_technical_error(error: Exception) -> bool:
    """只按类型和显式 cause 判定，绝不按中文文案或笼统 ValueError 分类。"""
    seen: set[int] = set()
    current: BaseException = error
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, FormulaBusinessError):
            return False
        if not isinstance(current, (FormulaParseError, FormulaColumnError, FormulaEvalError)):
            return True
        if current.__cause__ is None:
            return False
        current = current.__cause__
    return True  # 损坏的循环 cause 链不能伪装成正常业务失败


def formula_number(value: Any, source: str) -> Decimal:
    """引用值必须是有限数值；NULL、空白、布尔值不等于合法的零。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FormulaBusinessError(f"{source}：来源数值为空（NULL 或空白）")
    if isinstance(value, bool):
        raise FormulaBusinessError(f"{source}：布尔值不是金额")
    # 对象自身的 __str__ 故障不是金额格式错误，必须保留给 strict 重试边界。
    raw = value if isinstance(value, Decimal) else str(value)
    try:
        number = raw if isinstance(raw, Decimal) else Decimal(raw)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FormulaBusinessError(f"{source}：来源不是有效数值") from exc
    if not number.is_finite():
        raise FormulaBusinessError(f"{source}：来源不是有限数值")
    return number


def _resolve_tb_column(
    account_data: dict[str, Any],
    col_name: str,
    *,
    code: str,
    trace: list[str],
) -> Decimal:
    """按列名从科目数据取值 —— **三态**，禁回退到「期末余额」。

    ====================  ==========================  ==================  ==============================
    态                    条件                        返回                记录
    ====================  ==========================  ==================  ==============================
    未注册列名            ``col_name`` 不在别名表     ``Decimal("0")``    trace「列名未注册」+ 调用方记 errors
    已注册但该科目无数据  规范名不在 ``account_data`` ``Decimal("0")``    trace「该科目列无数据」
    正常                  —                           值                  —
    ====================  ==========================  ==================  ==============================

    两种缺失态**返回值相同（0）、trace 标记不同**；调用方用
    :func:`is_unregistered_column` 判定是否要记 ``errors``。

    🔴 **改造前两处求值路径都写**::

        val = account_data.get(resolved_col, account_data.get("期末余额", Decimal("0")))

    即取不到目标列时**静默回退期末余额** ⇒ 「本期增加 / 本期减少 / 本期计提」列
    拿到的是**期末余额**。全库 48 个预设格中招（``本期借方`` 19 / ``本期贷方`` 17 /
    ``贷方发生额`` 7 / ``借方发生额`` 5，2026-08-06 实测），是**数字错不是取不到** ——
    界面有值、零报错、既有单测全绿。

    为什么「已注册但无数据」返 ``0`` 而不是 ``MISSING_COLUMN``：
    ``aggregate_occurrence()`` **有意不产出零值键**（借贷双方都为 0 的标准码不进
    结果），此时 0 是**诚实的 0**（该科目本期确实没有发生额），不该让整格公式失败。
    只有「列名压根没注册」才是配置错。

    spec: .kiro/specs/formula-management-runtime-closure/ R3.2 / R3.3 / Property 6~7
    """
    resolved = COLUMN_ALIASES.get(col_name)
    if resolved is None:
        trace.append(
            f"TB('{code}','{col_name}') 列名未注册（可用：{'/'.join(sorted(COLUMN_ALIASES))}）"
        )
        return Decimal("0")
    if resolved not in account_data:
        # 文案含「列无数据」四字 —— `test_formula_column_alias_coverage::
        # test_resolver_distinguishes_unregistered_from_missing_data` 按此断言，
        # 用于区分本分支与「列名未注册」分支。改文案前先看该守卫。
        trace.append(f"TB('{code}','{col_name}')：该科目列无数据（缺「{resolved}」）→ 0")
        return Decimal("0")
    return account_data[resolved]


# ═══════════════════════════════════════════════════════════════════════════════
# AddressValidator Protocol（Task 17：validate_formula 接 address_registry）
# ═══════════════════════════════════════════════════════════════════════════════
# 同步 Protocol：L1 内核纯函数不依赖 async/DB，由 L2 编排层预载后注入。
# 实现方可以是 AddressRegistryService 的同步适配器（预载地址集合后传入）。


@runtime_checkable
class AddressValidator(Protocol):
    """地址有效性校验器 Protocol（需求 7.5）。

    validate_formula 可选注入：当提供时，校验公式中引用的科目编码/行次编码
    是否在当前项目地址注册表中存在；悬空引用产生 validation error。

    实现者只需提供 validate_codes 方法：
    - 输入：一组待校验的编码（account codes / row codes）
    - 输出：其中无效（不存在）的编码子集
    """

    def validate_codes(self, codes: set[str]) -> set[str]:
        """返回 codes 中无效（不存在于注册表）的编码子集。"""
        ...


# 递归下降 AST 解析层已拆到 formula_ast_parse（行数门）；这里原样再导出，调用方不变。
from app.services.formula_ast_parse import (  # noqa: E402,F401
    ASTBinOp,
    ASTCompare,
    ASTFuncCall,
    ASTNumber,
    ASTRangeSum,
    ASTRowRef,
    ASTString,
    ASTUnary,
    FormulaBlockedError,
    FormulaParseError,
    _AST_TOKEN_PATTERNS,
    _AST_TOKEN_RE,
    _RecursiveDescentParser,
    _Token,
    _tokenize,
    parse_to_ast,
)


@lru_cache(maxsize=2048)
def _ast_budget_problem(formula: str) -> str | None:
    """AST 预算（需求 12.3 末句）按公式文本缓存：AST 本身已按文本缓存、构造后不改。"""
    return ast_budget_problem(parse_to_ast(formula))


# ─── AST 求值（纯函数，基于 FormulaContext） ─────────────────────────────────

def _eval_ast(node: Any, ctx: FormulaContext, trace: list[str]) -> Decimal:
    """递归求值 AST 节点（纯函数，无 DB/async）。

    所有数据从 FormulaContext 取，与旧 regex 路径语义对齐。
    """
    if isinstance(node, ASTNumber):
        return formula_number(node.value, "数字字面量") if ctx.strict else node.value

    if isinstance(node, ASTString):
        if ctx.strict:
            return formula_number(node.value, "字符串字面量")
        # 字符串字面量尝试转 Decimal（兼容 formula_parser 行为）
        try:
            return Decimal(node.value)
        except (InvalidOperation, ValueError):
            return Decimal("0")

    if isinstance(node, ASTBinOp):
        left = _eval_ast(node.left, ctx, trace)
        right = _eval_ast(node.right, ctx, trace)
        if node.op == '+':
            return left + right
        elif node.op == '-':
            return left - right
        elif node.op == '*':
            return left * right
        elif node.op == '/':
            if right == 0:
                raise FormulaEvalError(f"除数为 0（被除数 {left}）")
            return left / right
        return Decimal("0")

    if isinstance(node, ASTUnary):
        operand = _eval_ast(node.operand, ctx, trace)
        return -operand if node.op == '-' else operand

    if isinstance(node, ASTCompare):
        left = _eval_ast(node.left, ctx, trace)
        right = _eval_ast(node.right, ctx, trace)
        op = node.op
        if op == '>':
            return Decimal("1") if left > right else Decimal("0")
        elif op == '<':
            return Decimal("1") if left < right else Decimal("0")
        elif op == '>=':
            return Decimal("1") if left >= right else Decimal("0")
        elif op == '<=':
            return Decimal("1") if left <= right else Decimal("0")
        elif op == '==':
            return Decimal("1") if left == right else Decimal("0")
        elif op == '!=':
            return Decimal("1") if left != right else Decimal("0")
        return Decimal("0")

    if isinstance(node, ASTRowRef):
        val = _row_value(ctx, node.row_code)
        trace.append(f"ROW('{node.row_code}') = {val}")
        return val

    if isinstance(node, ASTRangeSum):
        total = _row_range_value(ctx, node.start_code, node.end_code)
        trace.append(f"SUM({node.start_code}:{node.end_code}) = {total}")
        return total

    if isinstance(node, ASTFuncCall):
        return _eval_func_node(node, ctx, trace)

    logger.warning("Unknown AST node type in _eval_ast: %s", type(node))
    return Decimal("0")


def _eval_func_node(node: ASTFuncCall, ctx: FormulaContext, trace: list[str]) -> Decimal:
    """求值函数调用 AST 节点：handler 取自 FunctionRegistry（Task 4 插件式）。

    未注册函数、内置函数参数个数不足（另查 IF 上限，表在 ``formula_arity``）⇒ :class:`FormulaEvalError`（原先按 0）。
    """
    name = node.name
    args = node.args
    handler = _REGISTRY.get(name)
    if handler is None:
        raise FormulaEvalError(f"未注册的函数：{name}()")
    if problem := arity_problem(name, call_argc(name, args)):
        raise FormulaEvalError(problem)
    return handler(args, ctx, trace)


def _row_value(ctx: FormulaContext, row_code: str) -> Decimal:
    """ROW 两种解析路径共用：缺行、NULL 和非法金额均明确失败。"""
    if row_code not in ctx.row_cache:
        raise FormulaEvalError(f"ROW('{row_code}')：引用的行次不存在或尚未计算")
    return formula_number(ctx.row_cache[row_code], f"ROW('{row_code}')")


def _row_range_value(ctx: FormulaContext, start_code: str, end_code: str) -> Decimal:
    """范围内每个现有来源都必须有效；空范围也不是有证据的零。"""
    codes = [code for code in ctx.row_cache if start_code <= code <= end_code]
    if not codes:
        raise FormulaEvalError(f"SUM_ROW('{start_code}','{end_code}')：范围内无报表来源行")
    return sum((_row_value(ctx, code) for code in codes), Decimal("0"))


def _report_value(row_code: str, period_raw: str, ctx: FormulaContext) -> Decimal:
    """AST / regex 两路径共用：REPORT 期间识别 + 缺行报错（ADR-FGR-05）。"""
    period_lower = period_raw.strip().lower()
    if period_lower in _REPORT_CURRENT_PERIOD:
        cache = ctx.row_cache
    elif period_lower in _REPORT_PRIOR_PERIOD:
        cache = ctx.prior_row_cache
    else:
        raise FormulaEvalError(
            f"REPORT('{row_code}','{period_raw}')：无法识别期间「{period_raw}」"
            f"（可选：本期/期末/current 或 上期/期初/prior）"
        )
    if row_code not in cache:
        raise FormulaEvalError(
            f"REPORT('{row_code}','{period_raw}')：报表行不存在或未生成：{row_code}"
        )
    return formula_number(cache[row_code], f"REPORT('{row_code}','{period_raw}')")


def _extract_string_args(args: list[Any], ctx: FormulaContext, trace: list[str]) -> list[str]:
    """从 AST 参数列表中提取字符串值。"""
    str_args: list[str] = []
    for a in args:
        if isinstance(a, ASTString):
            str_args.append(a.value)
        elif isinstance(a, ASTNumber):
            str_args.append(str(a.value))
        elif isinstance(a, ASTRowRef):
            str_args.append(a.row_code)
        else:
            # 对复杂表达式求值后转字符串
            val = _eval_ast(a, ctx, trace)
            str_args.append(str(val))
    return str_args


# ═══════════════════════════════════════════════════════════════════════════════
# FunctionRegistry 插件式函数注册（Task 4）
# ═══════════════════════════════════════════════════════════════════════════════
# 所有 DSL 函数的单一注册表。新增函数 = 注册一个 handler，全域可用。
# handler 签名：(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal

# 函数 handler 签名
FunctionHandler = Callable[[list[Any], "FormulaContext", list[str]], Decimal]


class FunctionRegistry:
    """插件式函数注册表（需求 3.1 · 属性 Q1）。

    所有 DSL 函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + ABS/ROUND/MAX/MIN/IF）
    的单一注册表。新增函数仅在此处 register 即全域可用。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, FunctionHandler] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: FunctionHandler,
        *,
        arity: int | None = None,
        description: str = "",
        syntax: str = "",
        category: str = "",
    ) -> None:
        """注册/覆盖一个 DSL 函数。

        Args:
            name: 函数名（大写，如 'TB'）
            handler: 函数处理器，签名 (args, ctx, trace) -> Decimal
            arity: 参数个数（None=不限）
            description: 函数描述
            syntax: 语法示例
            category: 分类（取数/引用/数学/逻辑/自定义）
        """
        self._handlers[name] = handler
        # 内置函数的参数个数 / 写法以函数目录为单一真源（S1 ADR-FGR-01）；这里手写的值只用于目录外的自定义函数，
        # 否则注册表与 FORMULA_ARITY / 求值期校验各说各话（如 TB 已支持单参，注册表仍写 2）。
        from app.services.formula_function_catalog import FUNCTIONS

        spec = next((f for f in FUNCTIONS if f.name == name and "l1" in f.engines), None)
        self._metadata[name] = {
            "name": name,
            "arity": spec.arity_min if spec is not None else arity,
            "arity_max": spec.arity_max if spec is not None else arity,
            "description": description,
            "syntax": spec.syntax if spec is not None and spec.syntax else syntax,
            "category": category,
        }

    def get(self, name: str) -> FunctionHandler | None:
        """获取函数 handler，不存在返回 None。"""
        return self._handlers.get(name)

    def known_function_names(self) -> set[str]:
        """返回所有已注册函数名集合（供 validate_formula 校验未知函数）。"""
        return set(self._handlers.keys())

    def list_all(self) -> list[dict]:
        """列出所有已注册函数信息（供 /formula router 展示）。"""
        return [dict(meta) for meta in self._metadata.values()]

    def unregister(self, name: str) -> bool:
        """注销函数，返回是否成功。"""
        if name in self._handlers:
            del self._handlers[name]
            del self._metadata[name]
            return True
        return False


# ─── 内置函数 handler 定义 ────────────────────────────────────────────────────

def _handle_abs(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ABS(value) — 绝对值"""
    if len(args) >= 1:
        val = _eval_ast(args[0], ctx, trace)
        return abs(val)
    return Decimal("0")


def _round_half_up(value: Decimal, ndigits: int) -> Decimal:
    """ROUND 统一 ROUND_HALF_UP（D4，需求 2.6；原先 ``round()`` = 银行家舍入）：L1 与 ``safe_eval_expr`` 共用。"""
    return value.quantize(Decimal(1).scaleb(-ndigits), rounding=ROUND_HALF_UP)


def _handle_round(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ROUND(value, ndigits) — 四舍五入（ROUND_HALF_UP：ROUND(1.005,2)=1.01、ROUND(-1.005,2)=-1.01）"""
    if len(args) >= 1:
        val = _eval_ast(args[0], ctx, trace)
        ndigits = int(_eval_ast(args[1], ctx, trace)) if len(args) > 1 else 2
        return _round_half_up(val, ndigits)
    return Decimal("0")


def _handle_max(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """MAX(a, b, ...) — 最大值"""
    if len(args) >= 2:
        vals = [_eval_ast(a, ctx, trace) for a in args]
        return max(vals)
    return Decimal("0")


def _handle_min(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """MIN(a, b, ...) — 最小值"""
    if len(args) >= 2:
        vals = [_eval_ast(a, ctx, trace) for a in args]
        return min(vals)
    return Decimal("0")


def _handle_if(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """IF(cond, true_val, false_val) — 条件判断"""
    if len(args) == 3:
        cond = _eval_ast(args[0], ctx, trace)
        return _eval_ast(args[1], ctx, trace) if cond != 0 else _eval_ast(args[2], ctx, trace)
    return Decimal("0")


def _handle_tb(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """TB('code','column') — 单科目取值

    列名未注册时抛 :class:`FormulaColumnError`，由 `_execute_ast` 记入
    ``FormulaResult.errors`` —— **禁**静默回退期末余额（R3.2）。
    """
    str_args = _extract_string_args(args, ctx, trace)
    code = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    account_data = ctx.tb_data.get(code, {})
    val = _resolve_tb_column(account_data, col_name, code=code, trace=trace)
    if is_unregistered_column(col_name):
        raise FormulaColumnError(
            f"TB('{code}','{col_name}')：列名「{col_name}」未注册，无法取值"
        )
    if ctx.strict:
        val = formula_number(val, f"TB('{code}','{col_name}')")
    trace.append(f"TB('{code}','{col_name}') = {val}")
    return val


def _handle_sum_tb(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """SUM_TB('range','column') — 范围科目求和（**按列名**求和）。

    🔴 改造前本函数**取了 `col_name` 却丢弃**，写死 ``data.get("期末余额")`` ——
    连 `COLUMN_ALIASES` 都不查、trace 也不打印列名，比 ``TB`` 的静默回退更彻底。
    实测当前预设里 ``SUM_TB`` 第二实参**全是期末余额语义**（影响 0 格）⇒ 属
    **潜伏缺陷**：任何新增「``SUM_TB`` + 发生额列」的预设都会静默按期末余额求和。

    零回归：``期末余额`` 走 `_resolve_tb_column` 与原 ``data.get("期末余额", 0)``
    逐字等价（命中返值 / 缺键返 0）。
    """
    str_args = _extract_string_args(args, ctx, trace)
    code_range = str_args[0] if str_args else ''
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    # 未注册列名 → 早退报错（放在循环前，避免逐科目刷 N 条 trace）
    if is_unregistered_column(col_name):
        raise FormulaColumnError(
            f"SUM_TB('{code_range}','{col_name}')：列名「{col_name}」未注册，无法取值"
        )
    # 逐科目的「列无数据」只汇总计数，不逐条进 trace（宽区间如 1401~1499 会刷屏）
    sink: list[str] = []
    val = _sum_tb_value(ctx, code_range, col_name, sink)
    missing = sum(1 for t in sink if "列无数据" in t)
    if missing:
        trace.append(
            f"SUM_TB('{code_range}','{col_name}')：{missing} 个科目无该列数据（按 0 计）"
        )
    trace.append(f"SUM_TB('{code_range}','{col_name}') = {val}")
    return val


def _sum_tb_value(ctx: FormulaContext, code_range: str, col_name: str, sink: list[str]) -> Decimal:
    """区间求和（AST / 正则两条路径共用）。

    统一预载层按区间聚合好的值存在区间本身这个键下（``formula_preloader._load_tb``）⇒ 优先用它；原先预载层把
    ``'6601~6699'`` 当科目前缀、一条也匹配不到，区间求和恒为 0（spec formula-fetch-followup-defect-closure R7）。
    没有区间键时（报表路径给的是逐科目全量）逐科目按前缀区间求和；其他区间的聚合键不是科目，跳过。
    """
    precomputed = ctx.tb_data.get(code_range)
    if precomputed is not None:
        value = _resolve_tb_column(precomputed, col_name, code=code_range, trace=sink)
        return formula_number(value, f"SUM_TB('{code_range}','{col_name}')") if ctx.strict else value
    val = Decimal("0")
    parts = code_range.split("~")
    if len(parts) == 2:
        start, end = parts[0], parts[1]
        prefix_len = len(start)
        for code, data in ctx.tb_data.items():
            if "~" not in code and start <= code[:prefix_len] <= end:
                value = _resolve_tb_column(data, col_name, code=code, trace=sink)
                val += formula_number(value, f"TB('{code}','{col_name}')") if ctx.strict else value
    return val


def _handle_row(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ROW('code') — 引用其他行次"""
    str_args = _extract_string_args(args, ctx, trace)
    row_code = str_args[0] if str_args else ''
    val = _row_value(ctx, row_code)
    trace.append(f"ROW('{row_code}') = {val}")
    return val


def _handle_sum_row(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """SUM_ROW('start','end') — 范围行次求和"""
    str_args = _extract_string_args(args, ctx, trace)
    start_code = str_args[0] if str_args else ''
    end_code = str_args[1] if len(str_args) > 1 else ''
    val = _row_range_value(ctx, start_code, end_code)
    trace.append(f"SUM_ROW('{start_code}','{end_code}') = {val}")
    return val


# ── REPORT 期间映射（ADR-FGR-05）──────────────────────────────────────────────
_REPORT_CURRENT_PERIOD: frozenset[str] = frozenset({"本期", "期末", "current"})
_REPORT_PRIOR_PERIOD: frozenset[str] = frozenset({"上期", "期初", "prior"})


def _handle_report(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """REPORT('row_code', 'period') — 跨报表引用。

    期间参数认「本期/期末/current」（取 ``row_cache``）和「上期/期初/prior」（取 ``prior_row_cache``）；
    无法识别的期间 ⇒ 报错；行次不存在 ⇒ 报错（不再按 0）。ADR-FGR-05。
    """
    str_args = _extract_string_args(args, ctx, trace)
    row_code = str_args[0].strip() if str_args else ""
    period_raw = str_args[1].strip() if len(str_args) > 1 else "本期"
    val = _report_value(row_code, period_raw, ctx)
    trace.append(f"REPORT('{row_code}','{period_raw}') = {val}")
    return val


def _handle_prev(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """PREV('科目','列') / PREV(TB('科目','列'))：上年试算表按列取；PREV('底稿','表','字段')：上年同底稿取数（预载值）。"""
    if len(args) >= 1 and isinstance(args[0], ASTFuncCall) and args[0].name == "TB":
        args = args[0].args
    return _prev_value(_extract_string_args(args, ctx, trace), ctx, trace)


def _prev_value(str_args: list[str], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """AST / regex 两路径共用：三参缺预载值、两参列名未注册 ⇒ 抛 FormulaColumnError（报错，不按 0）。"""
    shown = ",".join(f"'{a}'" for a in str_args)
    if len(str_args) >= 3:
        key = (str_args[0].strip(), str_args[1].strip(), str_args[2].strip())
        if key not in ctx.prev_wp_data:
            raise FormulaColumnError(f"PREV({shown})：{ctx.prev_wp_missing.get(key, '上年同底稿取数未预载')}")
        val = ctx.prev_wp_data[key]
    else:
        code = str_args[0] if str_args else ''
        col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
        if is_unregistered_column(col_name):
            raise FormulaColumnError(f"PREV('{code}','{col_name}')：列名「{col_name}」未注册，无法取值")
        prior_data = ctx.prior_tb_data.get(code, {})
        if ctx.strict and COLUMN_ALIASES[col_name] not in prior_data:
            raise FormulaBusinessError(f"PREV({shown})：上年来源未预载")
        val = _resolve_tb_column(prior_data, col_name, code=code, trace=trace)
    if ctx.strict:
        val = formula_number(val, f"PREV({shown})")
    trace.append(f"PREV({shown}) = {val}")
    return val


def aux_ref_key(args: list[str] | tuple[str, ...]) -> str:
    """AUX 预载值在 ``ctx.aux_data[科目]`` 里的键：科目之后的参数原样拼接。

    统一预载层（``formula_preloader._load_aux``）按引用写法逐个取数后用本键存值，
    覆盖四参（类型, 辅助项, 列）/ 三参 / 两参全部写法与列名；单一来源，两侧同函数计算。
    spec formula-governance-coverage-closure R6.5。
    """
    return "\x1f".join(str(a) for a in args[1:])


def _aux_value(str_args: list[str], ctx: FormulaContext) -> Decimal:
    """先取预载键（按写法取到的值）；没有时退回旧口径 ``aux_data[科目][维度]``（报表路径按维度预载）。"""
    account = str_args[0] if str_args else ''
    account_data = ctx.aux_data.get(account, {})
    key = aux_ref_key(str_args)
    if key in account_data:
        val = account_data[key]
    else:
        dimension = str_args[1] if len(str_args) > 1 else ''
        if ctx.strict and dimension not in account_data:
            raise FormulaBusinessError(f"AUX({','.join(repr(a) for a in str_args)})：来源未预载")
        val = account_data.get(dimension, Decimal("0"))
    return formula_number(val, "AUX") if ctx.strict else val


def _handle_aux(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """AUX('account','dimension','column') / AUX('account','aux_type','item','column') — 辅助核算取值"""
    str_args = _extract_string_args(args, ctx, trace)
    val = _aux_value(str_args, ctx)
    trace.append(f"AUX({','.join(repr(a) for a in str_args)}) = {val}")
    return val


def _handle_adj(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """ADJ('code','adj_type') — 调整额**实时汇总**（归一净额口径）。

    ``adj_type`` 接受 `normalize_adj_type` 的全部写法（aje_net / aje / AJE /
    审计调整 / rje_net / rje / RJE / 重分类）。归一失败抛
    :class:`FormulaColumnError`（配置错，与 ``TB`` 未注册列名同语义），
    **禁**静默返 0 —— 那会让写错的第二参看起来像"该科目无调整"。

    🔴 **只给净额不给 dr/cr**：ADR-ADJ-005 的 ``*_dr``/``*_cr`` 是展示用原始
    借贷（恒非负未归一），参与算式会对贷方正常类方向反掉（Phase 0 的 B4）。
    故 ``ADJ('6001','aje_dr')`` 走归一失败报错，而非返回借方合计。

    🔴 **与 ``TB(code,'AJE调整')`` 的差异**：本函数取 `ctx.adj_data` = 实时汇总；
    ``TB()`` 取 `ctx.tb_data` = `trial_balance` 持久化快照。不等即快照过期。
    完整说明见 `adjustment_amount_source` 文件头。
    """
    str_args = _extract_string_args(args, ctx, trace)
    code = str_args[0] if str_args else ''
    raw_type = str_args[1] if len(str_args) > 1 else ''

    # 归一复用单一真源（禁另写一份表）。函数体内 import 是为保住 L1「无 DB/async
    # 耦合」声明 —— 该模块同时导出 async 取数函数，模块级 import 会把它拉进 L1。
    from app.services.adjustment_amount_source import normalize_adj_type

    try:
        norm_type = normalize_adj_type(raw_type)
    except ValueError as exc:
        if ctx.strict:
            raise FormulaBusinessError(f"ADJ('{code}','{raw_type}')：{exc}") from exc
        raise FormulaColumnError(f"ADJ('{code}','{raw_type}')：{exc}") from exc

    val = ctx.adj_data.get(code, {}).get(f"{norm_type}_net", Decimal("0"))
    if ctx.strict:
        val = formula_number(val, f"ADJ('{code}','{raw_type}')")
    trace.append(f"ADJ('{code}','{raw_type}') = {val}")
    return val


def note_value_key(label: str, column: str) -> str:
    """NOTE 预载值在 ``ctx.note_data[章节]`` 里的键：行 + 列（两参写法列为空串 = 第一个数据列）。

    预载（``formula_ref_preload.load_note_values``，NOTE 取数的唯一实现）按本键存值，本模块 ``_handle_note`` 按本键取值；
    单一来源，两侧同函数计算（同 ``aux_ref_key``）。原先只按第二参存取：同章节同行不同列（期末 / 期初）会撞成一个值。
    """
    return f"{(label or '').strip()}\x1f{(column or '').strip()}"


def _handle_note(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """NOTE('section','row','column') — 附注数据取值：先取预载键（行 + 列），没有时退回旧口径 ``note_data[章节][第二参]``。"""
    str_args = _extract_string_args(args, ctx, trace)
    section = (str_args[0] if str_args else '').strip()
    field_name = str_args[1] if len(str_args) > 1 else ''
    column = str_args[2] if len(str_args) > 2 else ''
    section_data = ctx.note_data.get(section, {})
    key = note_value_key(field_name, column)
    if ctx.strict and key not in section_data and field_name not in section_data:
        raise FormulaBusinessError(f"NOTE('{section}','{field_name}','{column}')：来源未预载")
    val = section_data[key] if key in section_data else section_data.get(field_name, Decimal("0"))
    if ctx.strict:
        val = formula_number(val, f"NOTE('{section}','{field_name}','{column}')")
    trace.append(f"NOTE('{section}','{field_name}','{column or ctx.default_column}') = {val}")
    return val


def _handle_wp(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """WP('wp_code','column') — 底稿数据取值（列名或单元格地址 B5）；三参见下"""
    str_args = _extract_string_args(args, ctx, trace)
    wp_code = str_args[0] if str_args else ''
    wp_data = ctx.wp_data.get(wp_code, {})
    if len(str_args) > 2:  # WP('底稿','表','锚点')：预载层 _load_wp 按「表!锚点」存值；取不到报错不代 0（原先读成列名「表」恒 0）
        key = f"{str_args[1].strip()}!{str_args[2].strip()}"
        if key not in wp_data:
            raise FormulaColumnError(f"WP('{wp_code}','{str_args[1]}','{str_args[2]}')：锚点未对齐或底稿未录入，取不到数")
        val = wp_data[key]
        if ctx.strict:
            val = formula_number(val, f"WP('{wp_code}','{key}')")
        trace.append(f"WP('{wp_code}','{key}') = {val}")
        return val
    col_name = str_args[1] if len(str_args) > 1 else ctx.default_column
    col = (col_name or "").strip()
    key = col.upper() if re.match(r"^[A-Z]+\d+$", col, re.IGNORECASE) and col.upper() in wp_data else col_name
    if ctx.strict and key not in wp_data:
        raise FormulaBusinessError(f"WP('{wp_code}','{col_name}')：来源未预载")
    val = wp_data.get(key, Decimal("0"))
    if ctx.strict:
        val = formula_number(val, f"WP('{wp_code}','{col_name}')")
    trace.append(f"WP('{wp_code}','{col_name}') = {val}")
    return val


# ─── 全局 FunctionRegistry 实例 + 内置函数注册 ────────────────────────────────

_REGISTRY = FunctionRegistry()

# 取数函数
_REGISTRY.register("TB", _handle_tb, arity=2, description="取科目余额", syntax="TB('科目编码','列名')", category="取数")
_REGISTRY.register("SUM_TB", _handle_sum_tb, arity=2, description="范围科目求和", syntax="SUM_TB('起始~结束','列名')", category="取数")
_REGISTRY.register("PREV", _handle_prev, arity=2, description="上年同期值", syntax="PREV('科目编码','列名') / PREV('底稿','表','字段')", category="取数")
_REGISTRY.register("AUX", _handle_aux, arity=3, description="辅助核算取值", syntax="AUX('科目','维度','列名')", category="取数")
_REGISTRY.register("NOTE", _handle_note, arity=3, description="附注数据取值", syntax="NOTE('章节','字段','列名')", category="取数")
_REGISTRY.register("WP", _handle_wp, arity=2, description="底稿数据取值", syntax="WP('底稿编码','列名')", category="取数")
_REGISTRY.register("ADJ", _handle_adj, arity=2, description="调整额实时汇总（净额）", syntax="ADJ('科目编码','aje_net|rje_net')", category="取数")

# 引用函数
_REGISTRY.register("ROW", _handle_row, arity=1, description="引用其他行次", syntax="ROW('行次编码')", category="引用")
_REGISTRY.register("SUM_ROW", _handle_sum_row, arity=2, description="范围行次求和", syntax="SUM_ROW('起始','结束')", category="引用")
_REGISTRY.register("REPORT", _handle_report, arity=2, description="跨报表引用", syntax="REPORT('行次编码','期间')", category="引用")

# 数学/逻辑函数
_REGISTRY.register("ABS", _handle_abs, arity=1, description="绝对值", syntax="ABS(值)", category="数学")
_REGISTRY.register("ROUND", _handle_round, arity=2, description="四舍五入", syntax="ROUND(值, 位数)", category="数学")
_REGISTRY.register("MAX", _handle_max, arity=2, description="最大值", syntax="MAX(值1, 值2)", category="数学")
_REGISTRY.register("MIN", _handle_min, arity=2, description="最小值", syntax="MIN(值1, 值2)", category="数学")
_REGISTRY.register("IF", _handle_if, arity=3, description="条件判断", syntax="IF(条件, 真值, 假值)", category="逻辑")

# ── 底稿预填充函数（L1 handler 从 ctx 新字段取值） ──
# spec: formula-execution-path-convergence Phase 1 · Task 7
# preloader 已按 key 格式批量查好 DB 数据并填入 FormulaContext 的扩展字段；序时账三个函数的键预载层没取
# （方向 / 期间 / 金额条件无法识别、写法不对、本求值路径不取序时账）⇒ 报错不代 0（formula-fetch-followup 6.5）。


def _handle_ledger(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """LEDGER('科目','方向','范围') — 序时账发生额；方向只认 debit / credit / 借 / 贷。"""
    str_args = _extract_string_args(args, ctx, trace)
    code, direction, period = (str_args + ["", "debit", "全年"][len(str_args):])[:3]
    key = f"{code}:{direction}:{period}"
    if key not in ctx.ledger_data:
        raise FormulaColumnError(f"LEDGER('{code}','{direction}','{period}')：未取数（方向 / 期间无法识别，或本路径不取序时账）")
    val = ctx.ledger_data[key]
    trace.append(f"LEDGER('{code}','{direction}','{period}') = {val}")
    return val


def _handle_ledger_detail(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """LEDGER_DETAIL('科目','月份','金额条件') — 符合条件的序时账笔数（明细行在 ``ctx.ledger_detail_data``）。"""
    str_args = _extract_string_args(args, ctx, trace)
    code, period, amount_filter = (str_args + ["", "全年", "*"][len(str_args):])[:3]
    key = f"{code}:{period}:{amount_filter}"
    if key not in ctx.ledger_detail_data:
        raise FormulaColumnError(f"LEDGER_DETAIL('{code}','{period}','{amount_filter}')：未取数（期间 / 金额条件无法识别、明细超过上限，或本路径不取序时账）")
    val = Decimal(len(ctx.ledger_detail_data[key]))
    trace.append(f"LEDGER_DETAIL('{code}','{period}','{amount_filter}') = {val}")
    return val


def _handle_tb_aux(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """TB_AUX('科目','维度','列名') — 辅助维度汇总。"""
    str_args = _extract_string_args(args, ctx, trace)
    code = str_args[0] if str_args else ""
    aux_type = str_args[1] if len(str_args) > 1 else ""
    column = str_args[2] if len(str_args) > 2 else "期末余额"
    key = f"{code}:{aux_type}:{column}"
    val = ctx.tb_aux_data.get(key, Decimal("0"))
    trace.append(f"TB_AUX('{code}','{aux_type}','{column}') = {val}")
    return val


def _handle_count_ledger(args: list[Any], ctx: FormulaContext, trace: list[str]) -> Decimal:
    """COUNT_LEDGER('科目','范围') — 序时账笔数。"""
    str_args = _extract_string_args(args, ctx, trace)
    code, period = (str_args + ["", "全年"][len(str_args):])[:2]
    key = f"{code}:{period}"
    if key not in ctx.ledger_count_data:
        raise FormulaColumnError(f"COUNT_LEDGER('{code}','{period}')：未取数（期间无法识别，或本路径不取序时账）")
    val = Decimal(ctx.ledger_count_data[key])
    trace.append(f"COUNT_LEDGER('{code}','{period}') = {val}")
    return val


_REGISTRY.register("LEDGER", _handle_ledger, arity=3, description="序时账取数", syntax="LEDGER('科目','方向','范围')", category="底稿取数")
_REGISTRY.register("LEDGER_DETAIL", _handle_ledger_detail, arity=3, description="序时账明细筛选", syntax="LEDGER_DETAIL('科目','月份','阈值')", category="底稿取数")
_REGISTRY.register("TB_AUX", _handle_tb_aux, arity=3, description="辅助维度汇总", syntax="TB_AUX('科目','维度','列名')", category="底稿取数")
_REGISTRY.register("COUNT_LEDGER", _handle_count_ledger, arity=2, description="序时账笔数统计", syntax="COUNT_LEDGER('科目','范围')", category="底稿取数")
_REGISTRY.register("PLACEHOLDER", lambda a, c, t: Decimal("0"), arity=0, description="预留占位", syntax="PLACEHOLDER()", category="底稿取数")


# ═══════════════════════════════════════════════════════════════════════════════
# 公式 Token 解析（Regex）
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.formula_grammar import TOKEN_PATTERNS as _TOKEN_PATTERNS


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


#: safe_eval_expr 认的函数（IF 另行惰性求值，只算被选中的分支，与 L1 ``_handle_if`` 同口径）
_SAFE_FUNCS: dict[str, Callable[[list[Decimal]], Decimal]] = {
    "ABS": lambda a: abs(a[0]),
    "ROUND": lambda a: _round_half_up(a[0], int(a[1]) if len(a) > 1 else 2),
    "MAX": max,
    "MIN": min,
}


def safe_eval_expr(expr: str) -> Decimal:
    """安全求值纯算术表达式（+−×÷ 括号、比较、ABS/ROUND/MAX/MIN/IF），基于 Python AST；正则降级路径的最后一步。

    与 L1 同口径（需求 2.3、2.6）：空串 = 0；语法错误、除零、不支持的运算 / 函数、参数个数不足（另查 IF 上限）、
    超出 AST 预算一律抛 :class:`FormulaEvalError`（原先一律返回 0）；ROUND 为 ROUND_HALF_UP。
    """
    text = expr.strip()
    if not text:
        return Decimal("0")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise FormulaBusinessError(f"算术表达式语法错误：{text[:200]}") from exc
    if problem := ast_budget_problem(tree, ast.iter_child_nodes):
        raise FormulaEvalError(problem)

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
                raise FormulaEvalError(f"算术表达式不支持运算符 {type(node.op).__name__}")
            if isinstance(node.op, ast.Div) and right == 0:
                raise FormulaEvalError(f"除数为 0（被除数 {left}）")
            return op_func(left, right)
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise FormulaEvalError(f"算术表达式不支持运算符 {type(node.op).__name__}")
            return op_func(operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn != "IF" and fn not in _SAFE_FUNCS:
                raise FormulaEvalError(f"未注册的函数：{fn}()")
            if problem := arity_problem(fn, len(node.args)):
                raise FormulaEvalError(problem)
            if fn == "IF":
                return _eval_node(node.args[1] if _eval_node(node.args[0]) != 0 else node.args[2])
            return _SAFE_FUNCS[fn]([_eval_node(a) for a in node.args])
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
        raise FormulaEvalError(f"算术表达式不支持的写法：{type(node).__name__}")

    try:
        return _eval_node(tree)
    except (ValueError, InvalidOperation, ZeroDivisionError, TypeError) as exc:
        raise FormulaEvalError(f"算术求值失败：{exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════════
# 核心执行函数
# ═══════════════════════════════════════════════════════════════════════════════

def execute_formula(
    formula: str | None,
    tb_map: dict[str, Decimal],
    row_cache: dict[str, Any],
    column: str = "期末余额",
    adj_map: dict[str, dict[str, Decimal]] | None = None,
) -> Decimal | None:
    """简易版执行（向后兼容）。返回成功的 Decimal 值，失败返回 ``None``。

    ``adj_map``：``adj_net_batch`` 的返回值。**本函数同步**不能自己取数 ——
    调用方（async）取好传进来；不传则 ``ADJ()`` 返 0（既有行为，零回归）。
    """
    ctx = FormulaContext.from_simple_map(tb_map, row_cache, adj_map=adj_map)
    result = execute(formula, ctx)
    if not result.ok or result.value is None:
        return None
    return result.value


def execute(formula: str | None, ctx: FormulaContext, *, strict: bool = False) -> FormulaResult:
    """L1 内核唯一求值入口（Single Kernel Entry Point）。

    契约（需求 3.3/3.4 · 属性 Q2）：
      - 纯函数：同 formula + 同 ctx → 同 FormulaResult（确定性，可单测可缓存）。
      - 无 DB/async 耦合：所有取数由 L2 编排层预载进 ctx，本函数只做求值。
      - 返回 FormulaResult（含 value + errors + warnings + trace）。

    parse 层（Task 3）：
      - _PARSE_MODE="ast"      → 纯递归下降 AST 求值
      - _PARSE_MODE="regex"    → 旧 regex token 替换（降级路径）
      - _PARSE_MODE="parallel" → 并行跑两路径，diff 一致用 AST 结果，不一致 warn 回退 regex
    """
    result = FormulaResult()

    if not formula or not formula.strip():
        # 空公式是成功的空计算，保持兼容入口的零值语义；真正失败路径不走这里。
        result.value = Decimal("0")
        return result

    # 不修改调用者快照；strict 只作用于本次求值。
    if strict:
        from dataclasses import replace
        ctx = replace(ctx, strict=True)
    try:
        if _PARSE_MODE == "regex":
            result = _execute_regex(formula, ctx)
        elif _PARSE_MODE == "ast":
            result = _execute_ast(formula, ctx)
        else:
            result = _execute_parallel(formula, ctx, strict=strict)
    except Exception as exc:
        if not strict:
            raise  # 保留旧入口未捕获异常的行为
        result.record_error(exc)
    if strict:
        result.raise_for_technical_error()
    return result


def _is_blocked_formula(formula: str | None) -> bool:
    """公式是否含非白名单内容（未注册函数 / eval/exec / URL / 外链）→ blocked（P0-项2）。

    委托 ``formula_management.formula_state``（单一真源，避免第二份白名单/危险表）。
    仅判 blocked（不判 damaged —— 解析失败仍走 parse_to_ast 的既有 error 路径）。
    """
    if not formula or not formula.strip():
        return False
    from app.services.formula_management.formula_state import (
        _dangerous_or_external,
    )

    text = formula.strip()
    if _dangerous_or_external(text):
        return True
    # 非白名单函数（白名单 = 本模块 FunctionRegistry，单一真源）
    import re as _re
    known = _REGISTRY.known_function_names()
    for m in _re.finditer(r"([A-Za-z_][A-Za-z_0-9]*)\s*\(", text):
        if m.group(1) not in known:
            return True
    return False


def _blocked_reason(formula: str) -> str:
    """被拦截的原因：点名第一个未注册函数；否则是危险内容 / 外链（与 ``_is_blocked_formula`` 同一判据）。"""
    import re as _re
    known = _REGISTRY.known_function_names()
    for m in _re.finditer(r"([A-Za-z_][A-Za-z_0-9]*)\s*\(", formula.strip()):
        if m.group(1) not in known:
            return f"未注册的函数：{m.group(1)}()"
    return "公式含非白名单内容（eval/exec/URL/外链），已拦截"


def _execute_ast(formula: str, ctx: FormulaContext) -> FormulaResult:
    """新 AST 递归下降求值路径。

    P0-项2：求值前先做 blocked 判定（非白名单函数 / eval/exec / URL / 外链）——
    命中则标 ``result.blocked=True`` 并记 error，**不静默返 0 冒充正常**。
    失败结果保持 ``value=None``，成功求值才写入 Decimal 值。
    """
    result = FormulaResult()
    # 保留非 strict 前置校验直接抛出的边界；strict 由 execute 捕获并原样上抛。
    if _is_blocked_formula(formula):
        result.blocked = True
        result.record_error(FormulaBusinessError(
            f"公式含非白名单内容（未注册函数/eval/URL/外链），已拦截: {formula}"
        ))
        result.trace.append(f"BLOCKED: {formula}")
        logger.warning("Formula blocked (non-whitelist/dangerous): %s", formula)
        return result
    try:
        ast_node = parse_to_ast(formula)
        if problem := _ast_budget_problem(formula):
            raise FormulaEvalError(problem)
        result.value = _eval_ast(ast_node, ctx, result.trace)
    except FormulaParseError as e:
        result.record_error(e, f"AST 解析失败: {e}")
        logger.warning("AST parse error: %s (formula=%s)", e, formula)
    except (FormulaColumnError, FormulaEvalError) as e:
        result.record_error(e)
        logger.warning("Formula fetch / eval error: %s (formula=%s)", e, formula)
    except Exception as e:
        result.record_error(e, f"AST 求值失败: {e}")
        logger.warning("AST eval error: %s (formula=%s)", e, formula)
    if "PREV" in formula:
        try:
            _check_prev_warnings(formula, ctx, result)
        except Exception as exc:
            if not ctx.strict:
                raise
            result.record_error(exc)
    return result


def _formula_ast_expression(
    node: Any, ctx: FormulaContext | None = None, trace: list[str] | None = None,
    *, address: bool = False,
) -> str:
    """把已解析节点写成兼容表达式；降级路径按真实 IF 条件裁掉未执行分支。"""
    def render(child: Any, *, literal: bool = False) -> str:
        return _formula_ast_expression(child, ctx, trace, address=literal)

    if isinstance(node, ASTNumber):
        text = format(node.value, "f")
        return repr(text) if address else text
    if isinstance(node, ASTString):
        return repr(node.value)
    if isinstance(node, ASTRowRef):
        return repr(node.row_code) if address else f"ROW({node.row_code!r})"
    if isinstance(node, ASTRangeSum):
        return f"SUM_ROW({node.start_code!r},{node.end_code!r})"
    if isinstance(node, (ASTBinOp, ASTCompare)):
        return f"({render(node.left)}{node.op}{render(node.right)})"
    if isinstance(node, ASTUnary):
        return f"({node.op}{render(node.operand)})"
    if isinstance(node, ASTFuncCall):
        if ctx is not None and node.name == "IF":
            if problem := arity_problem(node.name, len(node.args)):
                raise FormulaEvalError(problem)
            condition = _eval_ast(node.args[0], ctx, trace if trace is not None else [])
            return render(node.args[1] if condition != 0 else node.args[2])
        literal = node.name not in {"ABS", "ROUND", "MAX", "MIN", "IF"}
        args = ",".join(render(arg, literal=literal) for arg in node.args)
        return f"{node.name}({args})"
    raise FormulaEvalError(f"无法序列化公式节点：{type(node).__name__}")


def _execute_regex(formula: str, ctx: FormulaContext) -> FormulaResult:
    """兼容 token 替换路径；地址与条件结构复用同一 AST，不丢三参或短路。"""
    result = FormulaResult()
    try:
        if _is_blocked_formula(formula):
            result.blocked = True
            raise FormulaEvalError(_blocked_reason(formula))
        if problem := _ast_budget_problem(formula):
            raise FormulaEvalError(problem)
        formula = _formula_ast_expression(parse_to_ast(formula), ctx, result.trace)
    except (FormulaParseError, FormulaColumnError, FormulaEvalError) as exc:
        result.record_error(exc)
        return result
    expression = formula

    # ── 逐 token 替换 ──
    for token_name, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(formula):
            val = Decimal("0")
            trace_msg = ""

            if token_name == "TB":
                code, col_name = match.group(1), match.group(2)
                account_data = ctx.tb_data.get(code, {})
                # 🔴 `_TOKEN_PATTERNS` 的 TB 正则缺词边界，会匹配到
                # `SUM_TB('a~b','col')` 的后半段（实测混合公式里 TB 命中 2 次）。
                # 旧实现靠「`a~b` 在 tb_data 里查不到 → 0」侥幸不影响最终值，
                # 但改造后会**多记一条 error** 把 `ok` 误判成 False ⇒ 显式跳过
                # 区间形态（真正的 SUM_TB 由其自己的 token 分支处理）。
                if "~" in code:
                    continue
                val = _resolve_tb_column(
                    account_data, col_name, code=code, trace=result.trace
                )
                if is_unregistered_column(col_name):
                    # 与 AST 路径同口径：列名未注册 → 记 error，禁回退期末余额
                    result.record_error(FormulaColumnError(
                        f"TB('{code}','{col_name}')：列名「{col_name}」未注册，无法取值"
                    ))
                elif ctx.strict:
                    val = formula_number(val, f"TB('{code}','{col_name}')")
                trace_msg = f"TB('{code}','{col_name}') = {val}"

            elif token_name == "SUM_TB":
                code_range, col_name = match.group(1), match.group(2)
                # 与 AST 路径同口径：按列名求和，未注册列名记 error 而非静默按期末余额
                if is_unregistered_column(col_name):
                    result.record_error(FormulaColumnError(
                        f"SUM_TB('{code_range}','{col_name}')："
                        f"列名「{col_name}」未注册，无法取值"
                    ))
                else:
                    sink: list[str] = []
                    val = _sum_tb_value(ctx, code_range, col_name, sink)
                    missing = sum(1 for t in sink if "列无数据" in t)
                    if missing:
                        result.trace.append(
                            f"SUM_TB('{code_range}','{col_name}')："
                            f"{missing} 个科目无该列数据（按 0 计）"
                        )
                trace_msg = f"SUM_TB('{code_range}','{col_name}') = {val}"

            elif token_name == "ROW":
                row_code = match.group(1)
                try:  # 与 AST 路径同一取值函数：缺行报错，不按 0
                    val = _row_value(ctx, row_code)
                except FormulaEvalError as exc:
                    result.record_error(exc)
                trace_msg = f"ROW('{row_code}') = {val}"

            elif token_name == "SUM_ROW":
                start_code, end_code = match.group(1), match.group(2)
                try:
                    val = _row_range_value(ctx, start_code, end_code)
                except FormulaEvalError as exc:
                    result.record_error(exc)
                trace_msg = f"SUM_ROW('{start_code}','{end_code}') = {val}"

            elif token_name == "REPORT":
                row_code = match.group(1)
                period_raw = match.group(2).strip() if match.group(2) else "本期"
                # 与 AST 路径同一取值逻辑（ADR-FGR-05）
                try:
                    val = _report_value(row_code, period_raw, ctx)
                except FormulaEvalError as exc:
                    result.record_error(exc)
                trace_msg = f"REPORT('{row_code}','{period_raw}') = {val}"

            elif token_name == "PREV":
                # 与 AST 路径同一取值函数（三参读预载值、两参按列名；取不到报错不按 0）
                try:
                    val = _prev_value([g for g in match.groups() if g is not None], ctx, result.trace)
                except FormulaColumnError as exc:
                    result.record_error(exc)
                if val == 0 and match.group(3) is None:
                    result.warnings.append(f"PREV('{match.group(1)}'): 无上年数据")

            elif token_name in ("AUX", "NOTE", "WP"):
                if token_name == "AUX":
                    account = match.group(1)
                    dimension = match.group(2)
                    # 与 AST 路径同一取值函数（预载键优先，旧口径兜底）
                    val = _aux_value([account, dimension, match.group(3)], ctx)
                    trace_msg = f"AUX('{account}','{dimension}') = {val}"
                elif token_name in ("NOTE", "WP"):
                    handler = _handle_note if token_name == "NOTE" else _handle_wp
                    args = [ASTString(group) for group in match.groups() if group is not None]
                    try:
                        val = formula_number(handler(args, ctx, result.trace), token_name)
                    except (FormulaColumnError, FormulaEvalError) as exc:
                        result.record_error(exc)

            elif token_name == "ADJ":
                # 🔴 本分支**必须存在**：`val` 初值是 0 且循环末尾无条件替换 ⇒
                # 缺分支的 token 会被静默置 0，且只在降级路径错（AST 路径正常），
                # 是最难发现的形态。守卫 `test_every_token_pattern_has_regex_branch`。
                #
                # 🔴 **直接复用 AST 路径的 handler**，不另写一份归一+取值 ——
                # 两路径等值由「同一个函数」保证，而非靠测试比对两份平行实现。
                try:
                    val = _handle_adj(
                        [ASTString(match.group(1)), ASTString(match.group(2))],
                        ctx, result.trace,
                    )
                except FormulaColumnError as exc:
                    result.record_error(exc)

            expression = expression.replace(match.group(0), str(val), 1)
            if trace_msg:
                result.trace.append(trace_msg)

    # ── 安全求值 ──
    try:
        result.value = safe_eval_expr(expression)
    except Exception as e:
        result.record_error(e, f"算术求值失败: {e} (expr={expression})")
        logger.warning("Formula eval error: %s (expr=%s, formula=%s)", e, expression, formula)

    # token 取数或最终算术任一路径失败时，禁止把部分替换结果作为成功值返回。
    if result.errors:
        result.value = None
    return result


def _execute_parallel(
    formula: str, ctx: FormulaContext, *, strict: bool = False,
) -> FormulaResult:
    """默认保留对照回退；strict 中任一路径的技术故障不可被成功结果掩盖。"""
    regex_result = _execute_regex(formula, ctx)
    if strict:
        regex_result.raise_for_technical_error()
    ast_result = _execute_ast(formula, ctx)
    if strict:
        ast_result.raise_for_technical_error()

    # 如果 AST 解析/求值失败，直接回退 regex
    if not ast_result.ok:
        regex_result.warnings.append(
            f"[parallel] AST 路径失败({ast_result.errors[0] if ast_result.errors else '?'})，回退 regex"
        )
        return regex_result

    # diff 比较：value 逐位一致
    if ast_result.value == regex_result.value:
        # 一致 → 使用 AST 结果（更严谨的解析）
        return ast_result
    else:
        # 不一致 → warn 并回退 regex 结果
        diff_msg = (
            f"[parallel] AST={ast_result.value} vs regex={regex_result.value}，回退 regex"
        )
        logger.warning("Parse diff: %s (formula=%s)", diff_msg, formula)
        regex_result.warnings.append(diff_msg)
        return regex_result


def _check_prev_warnings(formula: str, ctx: FormulaContext, result: FormulaResult):
    """检查 PREV 函数是否有上年数据缺失的 warning。"""
    import re as _re
    for m in _re.finditer(r"PREV\(\s*(?:TB\(\s*)?'([^']+)'\s*,\s*'[^']*'\s*\)", formula):  # 两参；三参缺数已是 error
        code = m.group(1)
        prior_data = ctx.prior_tb_data.get(code, {})
        if prior_data.get("期末余额", Decimal("0")) == 0:
            warning = f"PREV('{code}'): 无上年数据"
            if warning not in result.warnings:
                result.warnings.append(warning)


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


def validate_formula(formula: str, address_validator: AddressValidator | None = None) -> list[str]:
    """校验公式语法，返回错误列表（空=合法）。

    使用 FunctionRegistry.known_function_names 校验未知函数（Task 4）。
    当提供 address_validator 时，额外校验公式中引用的科目编码/行次编码
    是否存在于地址注册表（Task 17，需求 7.5：悬空引用即拒）。
    """
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
    # 检查是否有未识别的函数（从 registry 获取已知函数名）
    import re as _re
    unknown = _re.findall(r"([A-Z_]+)\(", formula)
    known_funcs = _REGISTRY.known_function_names()
    for fn in unknown:
        if fn not in known_funcs:
            errors.append(f"未知函数: {fn}()")

    # ── 地址有效性校验（Task 17：address_validator 注入时启用） ──
    if address_validator is not None:
        codes = _extract_formula_codes(formula)
        if codes:
            invalid_codes = address_validator.validate_codes(codes)
            for code in sorted(invalid_codes):
                errors.append(f"悬空引用: '{code}' 在地址注册表中不存在")

    return errors


def _extract_formula_codes(formula: str) -> set[str]:
    """从公式中提取所有引用的编码（科目编码 + 行次编码）。

    用于 validate_formula 的地址有效性校验（Task 17）。
    提取范围：
    - TB('code', ...) → account code
    - SUM_TB('start~end', ...) → range start/end codes
    - ROW('code') → row code
    - SUM_ROW('start','end') → row codes
    - REPORT('code', ...) → row code
    - PREV('code', ...) → account code
    - AUX('code', ...) → account code
    - NOTE('section', ...) → section code
    - WP('code', ...) → wp code
    """
    import re as _re
    codes: set[str] = set()

    # TB / PREV — 科目编码（排除 SUM_TB 的匹配）
    for m in _re.finditer(r"(?<!SUM_)TB\(\s*'([^']+)'", formula):
        codes.add(m.group(1))
    for m in _re.finditer(r"PREV\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # SUM_TB — 范围编码（拆 start~end 为两个编码）
    for m in _re.finditer(r"SUM_TB\(\s*'([^']+)'", formula):
        range_str = m.group(1)
        parts = range_str.split("~")
        if len(parts) == 2:
            codes.add(parts[0])
            codes.add(parts[1])
        else:
            codes.add(range_str)

    # ROW — 行次编码（排除 SUM_ROW 的匹配）
    for m in _re.finditer(r"(?<!SUM_)ROW\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # SUM_ROW — 范围行次编码
    for m in _re.finditer(r"SUM_ROW\(\s*'([^']+)'\s*,\s*'([^']+)'", formula):
        codes.add(m.group(1))
        codes.add(m.group(2))

    # REPORT — 行次编码
    for m in _re.finditer(r"REPORT\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # AUX — 科目编码
    for m in _re.finditer(r"AUX\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # NOTE — 章节编码
    for m in _re.finditer(r"NOTE\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    # WP — 底稿编码
    for m in _re.finditer(r"WP\(\s*'([^']+)'", formula):
        codes.add(m.group(1))

    return codes


def _extract_wp_refs(formula: str) -> list[tuple[str, str]]:
    """从公式中提取 WP() 引用的 (wp_code, column) 参数对。

    用于 FormulaEngine.execute 的 L2 预载：提取后按 wp_code 分组批量查库。
    spec: formula-push-user-custom-cross-module Task 5
    """
    import re as _re
    refs: list[tuple[str, str]] = []
    for m in _re.finditer(r"WP\(\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)", formula):
        wp_code = m.group(1)
        column = m.group(2) or "审定数"
        refs.append((wp_code, column))
    return refs


def _extract_note_refs(formula: str) -> list[tuple[str, str]]:
    """从公式中提取 NOTE() 引用的 (section, field_name) 参数对。

    用于 FormulaEngine.execute 的 L2 预载：提取后按 section 分组批量查库。
    spec: formula-push-user-custom-cross-module Task 5
    """
    import re as _re
    refs: list[tuple[str, str]] = []
    for m in _re.finditer(r"NOTE\(\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*(?:,\s*'([^']+)')?\s*\)", formula):
        section = m.group(1)
        field_name = m.group(2) or "合计"
        refs.append((section, field_name))
    return refs


# ═══════════════════════════════════════════════════════════════════════════════
# FormulaEngine 类（向后兼容 formula.py 路由）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaEngine:
    """公式引擎类（兼容旧 API 路由）。

    旧路由 formula.py 需要一个带 redis_client 的类实例，
    提供 execute/list_all_functions/register_custom_function 等方法。

    注：函数清单的**单一权威来源**是模块级 ``_REGISTRY``（FunctionRegistry）。
    本类不再维护独立的内置函数静态表，``list_all_functions`` 与冲突校验均从
    ``_REGISTRY`` 派生，避免清单漂移（此前 _BUILTIN_FUNCTIONS 缺 NOTE/WP，
    导致用户可注册自定义函数覆盖内置 NOTE/WP）。
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._custom_functions: dict[str, dict] = {}

    def list_all_functions(self) -> list[dict]:
        """列出所有可用函数（从 FunctionRegistry 获取，含内置 + 自定义）"""
        return _REGISTRY.list_all()

    def list_custom_functions(self) -> list[dict]:
        """列出自定义函数（转发 formula_custom_functions，ADR-FHIC-17 任务 33）。"""
        from app.services.formula_custom_functions import list_custom_functions as _list
        return _list()

    def register_custom_function(
        self,
        name: str,
        description: str = "",
        syntax: str = "",
        formula: str = "",
        expression: str = "",
        param_names: tuple[str, ...] | list[str] = (),
    ) -> dict:
        """注册自定义函数（转发 formula_custom_functions，ADR-FHIC-17 任务 33）。"""
        from app.services.formula_custom_functions import register_custom_function as _reg
        return _reg(
            name=name,
            expression=expression or formula,
            description=description,
            param_names=param_names,
        )

    def unregister_custom_function(self, name: str) -> bool:
        """注销自定义函数（转发 formula_custom_functions，ADR-FHIC-17 任务 33）。"""
        from app.services.formula_custom_functions import unregister_custom_function as _unreg
        return _unreg(name)

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
        """执行公式（``POST /api/formula/execute`` 与 ``/batch-execute``）：薄转发到中央执行合同。

        求值、预检、缺科目与告警合并全在 ``formula_central_execute.execute_central``（ADR-FHIC-19）；``formula_type``
        只是请求里的说明字段，不参与求值（预检按表达式内全部函数调用名分类）。原实现自拼 ``tb_map``（全部列取
        ``unadjusted_amount`` ⇒ 「审定数」取到未审数、不分叶子）、失败一律 ``error=None``，已删。
        """
        from app.services.formula_central_execute import execute_central

        return await execute_central(db, project_id, year, (params or {}).get("formula", ""))

    async def batch_execute(self, db, project_id, year, formulas: list[dict], **kwargs) -> list[dict]:
        """批量执行：同一会话上逐条串行（不并发）。"""
        return [await self.execute(db, project_id, year, f.get("formula_type", ""), f.get("params", {}))
                for f in formulas]


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容导出（旧测试和旧模块依赖的名称）
# ═══════════════════════════════════════════════════════════════════════════════

class FormulaError(Exception):
    """公式执行错误"""
    pass


# parse 层公开 API（Task 3 新增）
__all__ = [
    "FormulaResult", "FormulaContext", "execute", "execute_formula",
    "validate_formula", "safe_eval_expr", "get_formula_account_codes",
    "FormulaEngine", "FormulaError", "FormulaEvalError", "FormulaBusinessError",
    "formula_technical_error", "formula_number",
    # Task 3: parse 层
    "parse_to_ast", "FormulaParseError", "_PARSE_MODE",
    "ASTNumber", "ASTString", "ASTFuncCall", "ASTBinOp", "ASTUnary",
    "ASTRowRef", "ASTRangeSum", "ASTCompare",
    # Task 4: FunctionRegistry
    "FunctionRegistry", "FunctionHandler", "_REGISTRY",
    # Task 17: AddressValidator Protocol
    "AddressValidator", "_extract_formula_codes",
    # spec: formula-push-user-custom-cross-module Task 5
    "_extract_wp_refs", "_extract_note_refs",
]


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


# ─── D2-3 坏账准备明细表嵌套结构寻址 ───────────────────────────────────────────
# 标识 D2-3 底稿的 sheet 名标记（第二参含此子串则走 NestedTableService 而非 parsed_data）
_D23_SHEET_MARKER = "坏账准备明细表"
#: 三参 WP 第三参为单元格地址（与 exact_identity.cell_of 同一 A1 口径）
_A1_FIELD = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")

# D2-3 字段中文名 → bad_debt_detail_rows 金额列（13 列语义 B~N + 合计/期末余额别名）
_D23_FIELD_TO_COLUMN: dict[str, str] = {
    # 期初系列
    "期初未审数": "amount_b",
    "期初账项调整": "amount_c",
    "重分类调整(期初)": "amount_d",
    "重分类调整（期初）": "amount_d",
    "重分类期初": "amount_d",
    "期初审定数": "amount_e",
    # 本期增加
    "本期计提": "amount_f",
    "本期计提合计": "amount_f",
    "其他增加": "amount_g",
    # 本期减少
    "本期转回": "amount_h",
    "本期转回合计": "amount_h",
    "核销": "amount_i",
    "核销合计": "amount_i",
    "其他减少": "amount_j",
    # 期末系列
    "期末未审数": "amount_k",
    "期末账项调整": "amount_l",
    "重分类调整(期末)": "amount_m",
    "重分类调整（期末）": "amount_m",
    "重分类期末": "amount_m",
    "期末审定数": "amount_n",
    "期末余额": "amount_n",
}


def _normalize_provision_name(name: str) -> str:
    """归一父行/计提方法中文名用于模糊匹配：去前缀"按"、空白与全/半角括号差异。"""
    out = (name or "").strip()
    if out.startswith("按"):
        out = out[1:]
    return out.replace(" ", "").replace("　", "")


#: 两参 WP() 中文列名 → parsed_data 顶层键（ADR-FHIC-06 第 2 点）。
WP_COLUMN_KEYS: dict[str, str] = {
    "审定数": "audited_amount",
    "未审数": "unadjusted_amount",
    "期初余额": "opening_balance",
    "期末余额": "audited_amount",
}


class WPExecutor:
    """WP 函数执行器：从底稿 parsed_data 取数

    语法:
    - 两参列名/单元格: WP('E1','审定数') / WP('D1-1','B5')
    - 三参 D2-3 嵌套寻址（合计级）: WP('D2','坏账准备明细表D2-3','本期计提合计')
    - 三参 D2-3 嵌套寻址（父行级）: WP('D2','坏账准备明细表D2-3','单项评估计提.期末审定数')

    两参时从 WorkingPaper 的 parsed_data 中按 wp_code 和列名取数；
    第二参含「坏账准备明细表」标记时走 NestedTableService（D2-3 专用表 bad_debt_detail_rows）。

    Requirements: 9.1, 9.2, 9.3, 9.4, 39.1
    """

    @staticmethod
    async def _resolve_d23(
        db, project_id, wp_code: str, sheet_name: str, field: str | None
    ):
        """精确定位 D2-3 来源；校验实际参与汇总的原始金额后复用既有汇总器。"""
        import sqlalchemy as sa

        from app.models.bad_debt_models import BadDebtDetailRow
        from app.models.workpaper_models import WpIndex
        from app.services.bad_debt_nested_table_service import NestedTableService

        source = f"WP('{wp_code}','{sheet_name}','{field or ''}')"
        field_str = (field or "").strip()
        parent_key, separator, sub_field = field_str.partition(".")
        col = _D23_FIELD_TO_COLUMN.get(sub_field.strip() if separator else field_str)
        if col is None:
            raise FormulaEvalError(f"{source}：未知或缺少金额字段")
        indexes = (await db.execute(
            sa.select(WpIndex.id).where(
                WpIndex.project_id == project_id, WpIndex.wp_code == wp_code,
                WpIndex.is_deleted == sa.false(),
            ).limit(2)
        )).scalars().all()
        if not indexes:
            raise FormulaEvalError(f"{source}：底稿不存在或已删除")
        if len(indexes) != 1:
            raise FormulaEvalError(f"{source}：存在多个底稿来源，无法唯一定位")
        wp_index_id = indexes[0]
        raw_rows = (await db.execute(sa.select(BadDebtDetailRow).where(
            BadDebtDetailRow.wp_index_id == wp_index_id))).scalars().all()
        parents = [row for row in raw_rows if row.parent_row_id is None]
        if not parents:
            raise FormulaEvalError(f"{source}：未录入坏账准备父行")
        children: dict[Any, list[Any]] = {}
        parent_ids = {row.id for row in parents}
        for row in raw_rows:
            if row.parent_row_id is not None:
                if row.parent_row_id not in parent_ids:
                    raise FormulaEvalError(f"{source}：明细行缺少所属父行")
                children.setdefault(row.parent_row_id, []).append(row)
        tree = await NestedTableService(db).get_tree(wp_index_id)
        targets = list(tree.parents)
        if separator:
            key = _normalize_provision_name(parent_key)
            exact, fuzzy = [], []
            for parent in targets:
                labels = [_normalize_provision_name(text) for text in (
                    parent.provision_method_label, parent.row_label) if text]
                if key and key in labels:
                    exact.append(parent)
                elif key and any(key in label or label in key for label in labels if label):
                    fuzzy.append(parent)
            targets = exact or fuzzy
            if len(targets) != 1:
                reason = "父行匹配存在歧义" if targets else "未找到引用父行"
                raise FormulaEvalError(f"{source}：{reason}")
        if not targets:
            raise FormulaEvalError(f"{source}：无可用坏账准备来源")
        selected = {parent.id for parent in targets}
        for parent in parents:
            if parent.id in selected:
                for row in children.get(parent.id) or [parent]:
                    formula_number(getattr(row, col), f"{source} 明细行 {row.row_label}")
        value = (getattr(targets[0].amounts, col) if separator
                 else getattr(tree.summary.amounts, col))
        return formula_number(value, source)

    @staticmethod
    async def _source_rows(db, project_id, wp_code: str):
        """普通列与 A1 引用共用同一活跃、唯一底稿约束。"""
        import sqlalchemy as sa

        from app.models.workpaper_models import WorkingPaper, WpIndex

        rows = (await db.execute(
            sa.select(WorkingPaper.id, WorkingPaper.parsed_data)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WpIndex.project_id == project_id,
                WpIndex.wp_code == wp_code,
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.is_deleted == sa.false(),
            ).limit(2)
        )).all()
        if not rows:
            raise FormulaEvalError(f"底稿 {wp_code} 不存在或未找到")
        if len(rows) != 1:
            raise FormulaEvalError(f"底稿 {wp_code} 存在多个来源，无法唯一定位")
        return rows

    @staticmethod
    async def read_sheet_cell(db, project_id, year, wp_code: str, sheet_text: str, cell: str):
        """三参 A1 委托 ACNR 判表与取数；对实际绑定的底稿补齐活跃、唯一约束。"""
        from app.services.acnr.wp_cell_target import effective_catalog, read_formula_cell

        index = await effective_catalog(db, project_id)
        target = await read_formula_cell(
            db, project_id=project_id, year=year, wp_code=wp_code, sheet_text=sheet_text, cell=cell, index=index)
        if target.read.state == "ok":
            await WPExecutor._source_rows(db, project_id, target.bound_wp_code or wp_code)
        return target

    @staticmethod
    async def execute(
        db, project_id, wp_code: str, column: str = "审定数", field: str | None = None,
        *, year: int | None = None,
    ):
        """按本次年度读取唯一底稿来源；缺数、歧义与非法金额均明确失败。

        WorkingPaper/WpIndex 没有年度列，年度边界取项目的真实审计年度；
        请求年度必须显式传入且与项目一致，不按自然年或其他项目兜底。
        """
        try:
            from app.services.project_audit_year import fetch_project_audit_year

            if year is None:
                raise FormulaEvalError(f"底稿 {wp_code}：缺少本次审计年度")
            if isinstance(year, bool) or not isinstance(year, int):
                raise FormulaEvalError(f"底稿 {wp_code}：本次审计年度无效")
            project_year = await fetch_project_audit_year(db, project_id)
            if project_year is None:
                raise FormulaEvalError(f"底稿 {wp_code}：项目未设置审计年度")
            if project_year != year:
                raise FormulaEvalError(
                    f"底稿年度与项目年度不符（项目 {project_year}，请求 {year}）")
            if _D23_SHEET_MARKER in (column or ""):
                return await WPExecutor._resolve_d23(db, project_id, wp_code, column, field)
            if field is not None:
                cell = field.strip().upper()
                if not _A1_FIELD.fullmatch(cell):
                    raise FormulaEvalError(f"底稿 {wp_code}：无法识别表内字段「{field}」")
                target = await WPExecutor.read_sheet_cell(
                    db, project_id, year, wp_code, column or "", cell)
                if target.read.state != "ok":
                    raise FormulaEvalError(target.read.reason or f"底稿 {wp_code} 单元格 {cell} 取不到数")
                return formula_number(target.read.value, f"底稿 {wp_code} 单元格 {cell}")

            rows = await WPExecutor._source_rows(db, project_id, wp_code)
            col = (column or "").strip()
            if re.fullmatch(r"[A-Z]+\d+", col, re.IGNORECASE):
                from app.services.wp_cell_reader import resolve_wp_cell

                read = await resolve_wp_cell(db, project_id, year, wp_code, None, col.upper())
                if read.matches > 1:
                    raise FormulaEvalError(f"底稿 {wp_code} 单元格 {col} 存在多个工作表来源，请指定工作表")
                if read.state != "ok":
                    raise FormulaEvalError(read.reason or f"底稿 {wp_code} 单元格 {col} 取不到数")
                return formula_number(read.value, f"底稿 {wp_code} 单元格 {col}")
            parsed_data = rows[0][1]
            if not isinstance(parsed_data, dict):
                raise FormulaEvalError(f"底稿 {wp_code} 未录入有效的解析数据")
            key = WP_COLUMN_KEYS.get(col, col)
            return formula_number(parsed_data.get(key), f"底稿 {wp_code}「{col}」")
        except FormulaEvalError:
            raise
        except Exception as exc:
            raise FormulaEvalError(f"底稿 {wp_code} 取值异常：{exc}") from exc


class REPORTExecutor:
    """REPORT 函数执行器：按行次取本年度已生成报表的本期金额（取不到 ⇒ ``None``，不代入 0）。

    口径同严格代入（``formula_ref_preload.load_report_rows``）。原实现引用了本模块从未导入的 ``sa`` ⇒ NameError
    被自身 ``except`` 吞掉、恒返回 0（spec formula-fetch-followup-defect-closure 7.2 发现）；行次在各报表间唯一，
    ``report_type`` 只为兼容旧签名保留。

    Requirements: 39.1
    """

    @staticmethod
    async def execute(db, project_id, year: int, report_type: str, row_code: str):
        """本年度报表 ``row_code`` 行的本期金额；报表未生成 / 没有该行 / 金额为空 ⇒ ``None``。"""
        from app.services.formula_ref_preload import load_report_rows

        rows = await load_report_rows(db, project_id, year)
        current = rows.get((row_code or "").strip(), (None, None))[0]
        return None if current is None else Decimal(str(current))


class NOTEExecutor:
    """NOTE 函数执行器：按章节 / 行 / 列取本年度附注单元格（取不到 ⇒ ``None``，不代入 0）。

    语法: ``NOTE('五、1','合计')`` / ``NOTE('五、1','银行存款','期初')``。委托 NOTE 取数的唯一实现
    ``formula_ref_preload.load_note_values``（与引用校验同一套匹配）。原实现引用了未导入的 ``sa`` ⇒ NameError 被吞、
    恒返回 0，且忽略行和列、一律取合计行第一列（spec formula-fetch-followup-defect-closure 7.2 发现）。

    Requirements: 39.1
    """

    @staticmethod
    async def execute(db, project_id, year: int, section_code: str, field_name: str = "合计", column: str = ""):
        """附注单元格的数值；章节 / 行 / 列找不到或单元格为空 ⇒ ``None``。"""
        from app.services.formula_ref_preload import load_note_values

        ref = ((section_code or "").strip(), field_name or "", column or "")
        values, _missing = await load_note_values(db, project_id, year, [ref])
        return values.get(ref[0], {}).get(note_value_key(ref[1], ref[2]))


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
