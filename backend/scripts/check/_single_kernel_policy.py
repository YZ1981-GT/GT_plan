"""single-kernel 守卫策略的**单一来源**。

两个守卫共用同一套"谁能直接导入低级求值原语"的策略：
  1. pytest 守卫  backend/tests/formula_runtime/test_single_kernel_guard.py
  2. CI strict 脚本 backend/scripts/check/check_formula_runtime_completion.py

历史上这套策略在两处各维护一份拷贝（白名单 + 保护 import 正则），已经漂移过一次：
CI 脚本缺 note_source_resolvers.py 豁免 → pytest 绿而 CI strict 恒红。为根除这类
漂移，把白名单与保护模式收敛到本模块作唯一来源，两处都 import 它，不再各留拷贝。

两处的调用约定（保持与历史一致）：
  · ALLOWED_FILES —— `rel_path.endswith(allowed)` 判定（相对 backend/app 的 posix 路径）。
  · PROTECTED_IMPORT_PATTERNS —— 每个用 `re.compile(p, re.IGNORECASE)` 编译后对
    **去除首尾空白、且非 '#' 注释**的行做 `search`。
"""
from __future__ import annotations

# ─── 被保护的低级求值符号：只能被下方 ALLOWED_FILES 直接导入 ──────────────────
#
# 保护对象是低级求值原语 formula_parse_utils.evaluate_formula 和 FormulaEvaluator，
# 不是 report_engine.evaluate_formula（那是合法的高层函数）。
PROTECTED_IMPORT_PATTERNS: tuple[str, ...] = (
    # from ...formula_parse_utils import ... evaluate_formula ...
    r"from\s+[\w.]*formula_parse_utils\s+import\s+.*\bevaluate_formula\b",
    # from ... import ... FormulaEvaluator ...
    r"from\s+[\w.]*\s+import\s+.*\bFormulaEvaluator\b",
    # import ...formula_parse_utils
    r"import\s+[\w.]*formula_parse_utils\b",
)

# ─── 允许直接导入低级求值的文件（唯一合法消费者）──────────────────────────────
# 路径相对 backend/app，用 endswith 匹配。
ALLOWED_FILES: frozenset[str] = frozenset(
    {
        # engine.py 本身是 single kernel 入口
        "formula_management/engine.py",
        # formula_engine.py 是 L1 内核本身（它定义了 execute）
        "services/formula_engine.py",
        # legacy adapter / deprecation shim 仍需暂时保留
        "services/formula_parse_utils.py",
        # ── note_source_resolvers.py：附注 SUM 绑定的**行内**求和 ─────────────
        # 🔴 这条豁免与守卫意图**同向**，不是开后门：
        #    `_resolve_formula_sum` 把 binding.cells 拼成 `ROW('c1') + ROW('c2') …`，
        #    连同一份**内存** row_values 字典交给 evaluate_formula 求值，其 docstring
        #    写明「复用既有 evaluate_formula 内核…不新造求值器，满足 Req1.2 / Property4」。
        #    走不了 engine.execute_formula 的原因是两者形态不兼容（已核实 2026-09-06）：
        #      · execute_formula 要 FormulaRecord + FormulaContext 两个结构化对象，
        #        而这里只有一个临时字符串表达式，没有落库的公式定义；
        #      · execute_formula **不支持** row_values（engine.py 内该标识符 0 次出现），
        #        而本场景的值全部来自当前附注表的同表坐标，不经任何 domain reader。
        #    强行改造 = 为「附注行内求和」凭空造一条 FormulaRecord，属功能改造而非修红。
        #    → 因此登记豁免。**新增**消费者仍应被守卫拦下（这正是它的价值）。
        "services/note_source_resolvers.py",
    }
)
