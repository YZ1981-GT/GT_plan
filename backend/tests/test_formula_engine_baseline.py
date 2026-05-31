"""阶段 0 — 4 套公式引擎对照基线测试（迁移安全网）

spec: formula-engine-unification / tasks.md Task 1
Validates: Requirements 2.1, 2.2  |  关联属性: Q1, Q4

═══════════════════════════════════════════════════════════════════════════════
目的
═══════════════════════════════════════════════════════════════════════════════
在对 4 套并行求值器做任何收敛之前，先用一组代表性公式记录每套引擎当前的
输出（冻结快照）。一旦后续收敛改动让某条公式的输出发生漂移（收敛/分歧关系
变化），本测试立即失败，强制人工复核目标语义 —— 不静默通过（需求 2.2）。

4 套引擎（设计 §三 能力实测对照）：
  1. formula_engine.execute()        纯函数 + FormulaContext 注入（报表 DSL，最全函数集）
  2. report_engine.evaluate_formula() DB 取数编排（注入 AmountResolver；本测试注入内存 resolver 做到无 DB）
  3. formula_parser.evaluate_formula() 递归下降解析；数据函数委托 FormulaEngine（需 DB）
  4. cell_formula_evaluator.execute_formula() 底稿单元格 Excel 语法（=A1+B2）—— 与报表 DSL 是**不同语法域**

═══════════════════════════════════════════════════════════════════════════════
冻结基线发现（人工需确认目标语义的【语义分歧】= formula_engine vs report_engine 同数据）
═══════════════════════════════════════════════════════════════════════════════
  ▸ D1 [公式 #4 SUM_TB 区间匹配]
        formula_engine 用「前缀截断」匹配（code[:len(start)] 落在 start..end）
          → '14999' 的前 4 位 '1499' ∈ ['1400','1499'] → 计入  → 42777
        report_engine 用「整串字典序」匹配（start <= code <= end）
          → '14999' > '1499' → 不计入                          → 35000
        ⟹ 同一 SUM_TB('1400~1499') 两引擎差 7777，须人工拍板目标区间语义。

  ▸ D2 [公式 #8 PREV 上年取数]
        formula_engine 从 ctx.prior_tb_data 取上年值                → 80000
        report_engine 在报表语境强制把 PREV/NOTE/WP/AUX 置 0        → 0
        ⟹ PREV 在报表域是否应取上年数，须人工拍板。

  ▸ D2-nested [公式 #10 嵌套 PREV(TB(...))]（P0 技术债修复后新增登记）
        _PARSE_MODE 默认由 parallel 切到 ast（递归下降已验证更正确 + Decimal 全程精确）后，
        formula_engine 经 AST 正确求值嵌套 PREV(TB('1002'))=上年值 → 80000
        report_engine 报表语境仍强制 PREV→0                         → 0
        ⟹ 与 D2 同根因的嵌套形态。旧 parallel 模式下 regex 不识别嵌套 → 两引擎都返 0
           （伪收敛），AST 默认后暴露真实分歧，已登记 KNOWN_DIVERGENCES。

【结构性差异】（非语义分歧，是调用契约差异，归档备查，不需逐条人工拍板）：
  ▸ formula_parser 不是独立纯求值器：TB/SUM_TB/PREV/REPORT 等数据函数委托 FormulaEngine
    （需 DB）。无 DB 注入时这些函数一律返回 0；且**原生不支持 IF/ABS/ROUND/MAX/MIN**，
    比较运算符 '>' 不在词法表内（IF(...>0,...) 直接解析报错）。
  ▸ cell_formula_evaluator 是底稿 Excel 语法域（=B2+B3 / SUM(B2:B5)），报表 DSL 对它 N/A。
  ▸ 4 套引擎的纯算术内核（+−×÷、括号）对 '100+200*3' 一致 == 700（见 TestArithmeticCoreConvergence）。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.services.formula_engine import execute as fe_execute, FormulaContext, safe_eval_expr
from app.services.report_engine import evaluate_formula as re_evaluate, _safe_eval_expr as re_safe_eval
from app.services.formula_parse_utils import evaluate_formula as fp_evaluate
from app.services.cell_formula_evaluator import (
    execute_formula as fu_execute,
    _safe_eval as fu_safe_eval,
    parse_formula as fu_parse,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 代表性数据集（无 DB，全内存）
# ═══════════════════════════════════════════════════════════════════════════════

BASELINE_TB: dict[str, Decimal] = {
    "1002": Decimal("100000"),   # 货币资金
    "1012": Decimal("50000"),    # 其他货币资金
    "1122": Decimal("500000"),   # 应收账款
    "1231": Decimal("-30000"),   # 坏账准备（备抵，负数）
    "1401": Decimal("10000"),    # 材料采购
    "1406": Decimal("20000"),    # 库存商品
    "1411": Decimal("5000"),     # 周转材料
    "14999": Decimal("7777"),    # 5 位编码：用于暴露 SUM_TB 前缀截断 vs 整串字典序分歧
}
BASELINE_PRIOR: dict[str, Decimal] = {"1002": Decimal("80000")}
BASELINE_ROWS: dict[str, Decimal] = {
    "BS-002": Decimal("100"),
    "BS-003": Decimal("200"),
    "BS-004": Decimal("300"),
    "BS-010": Decimal("50"),
    "BS-027": Decimal("1000000"),
}


class InMemoryResolver:
    """实现 AmountResolver Protocol 的内存取数器 —— 让 report_engine 无需 DB 即可对照。

    取数口径刻意复刻 report_engine 经 DB 查询时的语义：
      resolve_tb  → 直接按科目编码返回（忽略列名，与基线数据单列一致）
      resolve_sum → 整串字典序区间 start <= code <= end（= DB 的 >= / <= 谓词）
    """

    def __init__(self, tb_map: dict[str, Decimal]):
        self.db = None
        self.project_id = None
        self.year = 2024
        self._tb = tb_map

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        return self._tb.get(account_code, Decimal("0"))

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start, end = parts[0].strip(), parts[1].strip()
        total = Decimal("0")
        for code, val in self._tb.items():
            if start <= code <= end:   # 整串字典序（复刻 report_engine 的 DB 区间谓词）
                total += val
        return total


def _run(coro):
    """用独立事件循环跑协程，避免 pytest-asyncio mode=auto 的全局循环污染（与 test_formula_parser 同策略）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 引擎调用包装（统一成可比较的返回）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_fe_ctx() -> FormulaContext:
    ctx = FormulaContext.from_simple_map(
        BASELINE_TB, row_cache=dict(BASELINE_ROWS), prior_map=BASELINE_PRIOR
    )
    return ctx


def eval_formula_engine(formula: str) -> Decimal:
    """① formula_engine：纯函数求值。"""
    return fe_execute(formula, _build_fe_ctx()).value


def eval_report_engine(formula: str) -> Decimal:
    """② report_engine：注入内存 resolver + row_cache，无 DB。"""
    resolver = InMemoryResolver(BASELINE_TB)
    return _run(re_evaluate(formula, resolver=resolver, row_cache=dict(BASELINE_ROWS)))


def eval_formula_parser(formula: str):
    """③ formula_parser：无 engine（无 DB）。返回 dict['value']（float | None）。"""
    res = _run(fp_evaluate(formula, db=None, project_id=None, year=2024,
                           engine=None, row_values=dict(BASELINE_ROWS)))
    return res["value"], res["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# 代表性公式集（设计 §需求 2.1 要求覆盖）
#   每条： (id, 公式, 说明)
# ═══════════════════════════════════════════════════════════════════════════════

REPRESENTATIVE_FORMULAS: list[tuple[str, str, str]] = [
    ("F01_TB",            "TB('1002','期末余额')",                          "单科目取值"),
    ("F02_TB_ADD",        "TB('1002','期末余额')+TB('1012','期末余额')",      "两科目相加"),
    ("F03_TB_CONTRA",     "TB('1122','期末余额')-TB('1231','期末余额')",      "备抵扣减（应收-坏账）"),
    ("F04_SUM_TB",        "SUM_TB('1400~1499','期末余额')",                 "范围科目求和（暴露区间匹配分歧 D1）"),
    ("F05_ROW",           "ROW('BS-027')",                                 "引用其他行次"),
    ("F06_SUM_ROW",       "SUM_ROW('BS-002','BS-008')",                    "范围行次求和"),
    ("F07_REPORT",        "REPORT('BS-002','current')",                    "跨报表引用"),
    ("F08_PREV",          "PREV('1002','期末余额')",                        "上年同期值（暴露 PREV 取数分歧 D2）"),
    ("F09_AUX",           "AUX('1122','客户A','期末余额')",                  "辅助核算取值（跨模块）"),
    ("F10_NESTED_PREV_TB","PREV(TB('1002','期末余额'))",                    "嵌套 PREV(TB(...))"),
    ("F11_IF",            "IF(TB('1002','期末余额')>0,TB('1002','期末余额'),0)", "IF + 比较"),
    ("F12_ABS",           "ABS(TB('1231','期末余额'))",                     "ABS 绝对值（坏账负数）"),
    ("F13_ROUND",         "ROUND(TB('1002','期末余额')/3,2)",               "ROUND 四舍五入"),
    ("F14_MAX",           "MAX(TB('1002','期末余额'),TB('1012','期末余额'))", "MAX 取大"),
    ("F15_MIN",           "MIN(TB('1002','期末余额'),TB('1012','期末余额'))", "MIN 取小"),
    ("F16_ARITH",         "100+200*3",                                     "纯算术（4 套内核应一致）"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 冻结基线快照
#   值为各引擎在【当前代码】下的真实输出（首次运行实测后写入冻结）。
#   None = 该引擎对该公式不适用 / 报错（结构性差异，见文件头说明）。
#   一旦后续收敛让任一格子漂移，对应断言失败 → 强制人工复核（需求 2.2）。
# ═══════════════════════════════════════════════════════════════════════════════

# formula_engine.execute → Decimal
FE_BASELINE: dict[str, Decimal] = {
    "F01_TB":             Decimal("100000"),
    "F02_TB_ADD":         Decimal("150000"),
    "F03_TB_CONTRA":      Decimal("530000"),
    "F04_SUM_TB":         Decimal("42777"),    # 含 14999（前缀截断匹配）→ D1
    "F05_ROW":            Decimal("1000000"),
    "F06_SUM_ROW":        Decimal("600"),
    "F07_REPORT":         Decimal("100"),       # REPORT 走 row_cache（BS-002=100）
    "F08_PREV":           Decimal("80000"),     # 取上年 → D2
    "F09_AUX":            Decimal("0"),          # 跨模块未支持 → 0 + warning
    # F10：AST 默认（P0 技术债修复，_PARSE_MODE parallel→ast）后，嵌套 PREV(TB(...)) 由
    # 递归下降正确求值 = 上年 1002 期末余额 80000。旧 parallel 模式下 regex 不匹配嵌套
    # （PREV 参数是 TB(...) 而非引号字符串），diff 回退 regex → 整体算术求值 → 0（旧基线）。
    # AST 路径更正确（设计 §3 AST 替换 regex 的核心动机即嵌套支持）。
    "F10_NESTED_PREV_TB": Decimal("80000"),      # AST 默认：嵌套 PREV(TB('1002'))=上年值 80000
    "F11_IF":             Decimal("100000"),     # IF(100000>0,100000,0)
    "F12_ABS":            Decimal("30000"),      # ABS(-30000)
    "F13_ROUND":          Decimal("33333.33"),   # ROUND(100000/3,2)
    "F14_MAX":            Decimal("100000"),
    "F15_MIN":            Decimal("50000"),
    "F16_ARITH":          Decimal("700"),
}

# report_engine.evaluate_formula → Decimal（注入内存 resolver）
RE_BASELINE: dict[str, Decimal] = {
    "F01_TB":             Decimal("100000"),
    "F02_TB_ADD":         Decimal("150000"),
    "F03_TB_CONTRA":      Decimal("530000"),
    "F04_SUM_TB":         Decimal("35000"),     # 不含 14999（整串字典序）→ D1
    "F05_ROW":            Decimal("1000000"),
    "F06_SUM_ROW":        Decimal("600"),
    "F07_REPORT":         Decimal("100"),
    "F08_PREV":           Decimal("0"),          # 报表语境强制 0 → D2
    "F09_AUX":            Decimal("0"),
    "F10_NESTED_PREV_TB": Decimal("0"),
    "F11_IF":             Decimal("100000"),
    "F12_ABS":            Decimal("30000"),
    "F13_ROUND":          Decimal("33333.33"),
    "F14_MAX":            Decimal("100000"),
    "F15_MIN":            Decimal("50000"),
    "F16_ARITH":          Decimal("700"),
}

# formula_parser.evaluate_formula → (value: float | None, error: str | None)
# 无 engine（无 DB）：数据函数委托 L1 内核 formula_engine.execute（Task 11 收口）。
# F05/F06/F07（ROW/SUM_ROW/REPORT）只用 row_values（ctx.row_cache），不需 DB → 经内核 AST
# 路径正确求值。AST 默认（P0 技术债修复，_PARSE_MODE parallel→ast）后，内核委托重建的
# 函数字符串（含逗号后空格 'a', 'b'）由递归下降正确解析；旧 parallel 模式下 regex token
# 正则不匹配带空格变体 → diff 回退 regex → 0（旧基线）。
# 其余数据函数（TB/SUM_TB/PREV）无 DB 注入 → ctx.tb_data 为空 → 0。
# None 表示「该引擎无法对此公式产出数值」（解析错误 / 比较运算符未词法化）。
FP_BASELINE: dict[str, float | None] = {
    "F01_TB":             0.0,    # 委托内核但 ctx.tb_data 空 → 0
    "F02_TB_ADD":         0.0,
    "F03_TB_CONTRA":      0.0,
    "F04_SUM_TB":         0.0,
    "F05_ROW":            1000000.0,   # ROW 走 row_values，不需 DB
    "F06_SUM_ROW":        600.0,  # AST 默认：SUM_ROW 走 row_cache 正确求和（BS-002+003+004=600）
    "F07_REPORT":         100.0,  # AST 默认：REPORT 走 row_cache（BS-002=100）
    "F08_PREV":           0.0,
    "F09_AUX":            0.0,
    "F10_NESTED_PREV_TB": 0.0,
    "F11_IF":             None,   # '>' 比较运算符未词法化 → 解析报错
    "F12_ABS":            0.0,    # ABS 委托内核但 ctx 空 → 0
    "F13_ROUND":          0.0,
    "F14_MAX":            0.0,
    "F15_MIN":            0.0,
    "F16_ARITH":          700.0,  # 纯算术内核一致
}


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 1：冻结快照守门 —— 每套引擎当前输出 == 基线（任一漂移即失败）
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrozenBaselineFormulaEngine:
    """① formula_engine.execute 当前输出冻结基线（需求 2.1）。"""

    @pytest.mark.parametrize("fid,formula,desc", REPRESENTATIVE_FORMULAS,
                             ids=[f[0] for f in REPRESENTATIVE_FORMULAS])
    def test_matches_baseline(self, fid, formula, desc):
        actual = eval_formula_engine(formula)
        expected = FE_BASELINE[fid]
        assert actual == expected, (
            f"[formula_engine 漂移] {fid} ({desc})\n"
            f"  公式: {formula}\n"
            f"  基线: {expected}\n"
            f"  当前: {actual}\n"
            f"  ⟹ 收敛改变了 formula_engine 输出，须人工复核目标语义。"
        )


class TestFrozenBaselineReportEngine:
    """② report_engine.evaluate_formula 当前输出冻结基线（需求 2.1）。"""

    @pytest.mark.parametrize("fid,formula,desc", REPRESENTATIVE_FORMULAS,
                             ids=[f[0] for f in REPRESENTATIVE_FORMULAS])
    def test_matches_baseline(self, fid, formula, desc):
        actual = eval_report_engine(formula)
        expected = RE_BASELINE[fid]
        assert actual == expected, (
            f"[report_engine 漂移] {fid} ({desc})\n"
            f"  公式: {formula}\n"
            f"  基线: {expected}\n"
            f"  当前: {actual}\n"
            f"  ⟹ 收敛改变了 report_engine 输出，须人工复核目标语义。"
        )


class TestFrozenBaselineFormulaParser:
    """③ formula_parser.evaluate_formula（无 DB）当前输出冻结基线（需求 2.1）。"""

    @pytest.mark.parametrize("fid,formula,desc", REPRESENTATIVE_FORMULAS,
                             ids=[f[0] for f in REPRESENTATIVE_FORMULAS])
    def test_matches_baseline(self, fid, formula, desc):
        value, error = eval_formula_parser(formula)
        expected = FP_BASELINE[fid]
        if expected is None:
            assert value is None, (
                f"[formula_parser 漂移] {fid} ({desc}) 期望解析失败(None)，实得 {value} (error={error})"
            )
        else:
            assert value == expected, (
                f"[formula_parser 漂移] {fid} ({desc})\n"
                f"  公式: {formula}\n  基线: {expected}\n  当前: {value} (error={error})\n"
                f"  ⟹ 收敛改变了 formula_parser 输出，须人工复核。"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 2：语义分歧显式标注 —— 不静默通过（需求 2.2）
#   显式记录 formula_engine vs report_engine 在同一公式 + 同一数据下的【已知分歧】。
#   这两条是收敛时必须人工拍板目标语义的项。若未来两引擎对某分歧公式
#   变得一致（或新增分歧），本测试失败，提醒维护者更新 KNOWN_DIVERGENCES。
# ═══════════════════════════════════════════════════════════════════════════════

# fid -> (formula_engine 值, report_engine 值, 分歧根因)
KNOWN_DIVERGENCES: dict[str, tuple[Decimal, Decimal, str]] = {
    "F04_SUM_TB": (
        Decimal("42777"), Decimal("35000"),
        "SUM_TB 区间匹配：formula_engine 前缀截断(含14999) vs report_engine 整串字典序(不含14999)",
    ),
    "F08_PREV": (
        Decimal("80000"), Decimal("0"),
        "PREV 取数：formula_engine 取上年 prior_tb_data vs report_engine 报表语境强制 0",
    ),
    "F10_NESTED_PREV_TB": (
        Decimal("80000"), Decimal("0"),
        "PREV 取数（嵌套形态，同 D2 根因）：AST 默认（_PARSE_MODE parallel→ast）后嵌套 "
        "PREV(TB(...)) 由递归下降正确求值取上年 80000 vs report_engine 报表语境强制 PREV→0。"
        "旧 parallel 模式下 regex 不识别嵌套 → 两引擎都 0（伪收敛），AST 修复后暴露真实分歧。",
    ),
}


class TestSemanticDivergencesExplicit:
    """显式标注 formula_engine ↔ report_engine 语义分歧（需求 2.2 不静默通过）。"""

    @pytest.mark.parametrize("fid", list(KNOWN_DIVERGENCES.keys()))
    def test_known_divergence_still_holds(self, fid):
        fe_expected, re_expected, root_cause = KNOWN_DIVERGENCES[fid]
        formula = next(f for (i, f, _d) in REPRESENTATIVE_FORMULAS if i == fid)

        fe_actual = eval_formula_engine(formula)
        re_actual = eval_report_engine(formula)

        # 1) 两引擎当前值仍与冻结基线一致
        assert fe_actual == fe_expected, f"{fid}: formula_engine 漂移 {fe_expected}→{fe_actual}"
        assert re_actual == re_expected, f"{fid}: report_engine 漂移 {re_expected}→{re_actual}"

        # 2) 分歧仍然存在（显式标注，不静默通过）。若两者变一致 → 失败提醒人工确认目标语义已收敛。
        assert fe_actual != re_actual, (
            f"[分歧消失] {fid}: formula_engine 与 report_engine 现已一致 (={fe_actual})。\n"
            f"  原分歧根因: {root_cause}\n"
            f"  ⟹ 若这是收敛后的预期目标语义，请人工确认并从 KNOWN_DIVERGENCES 移除该项。"
        )

    def test_divergence_count_frozen(self):
        """已知语义分歧总数冻结为 3（新增/消失分歧都会失败，强制人工确认）。

        基线 2（F04_SUM_TB 区间匹配 + F08_PREV 取数）→ 3：P0 技术债修复将 _PARSE_MODE
        默认由 parallel 切到 ast 后，嵌套 PREV(TB(...))（F10）由 AST 正确取上年值，
        暴露出与 report_engine（报表语境强制 PREV→0）的真实分歧（D2 的嵌套形态）。
        旧 parallel 模式下该公式两引擎都因 regex 不识别嵌套而返 0（伪收敛）。
        """
        assert len(KNOWN_DIVERGENCES) == 3, (
            f"已知语义分歧数变化（现 {len(KNOWN_DIVERGENCES)}，基线 3）。"
            f"新增分歧须在 KNOWN_DIVERGENCES 登记并人工确认目标语义。"
        )


class TestConvergenceWhereExpected:
    """非分歧公式：formula_engine 与 report_engine 应逐位一致（收敛目标守门）。"""

    @pytest.mark.parametrize("fid,formula,desc", REPRESENTATIVE_FORMULAS,
                             ids=[f[0] for f in REPRESENTATIVE_FORMULAS])
    def test_convergent_formulas_agree(self, fid, formula, desc):
        if fid in KNOWN_DIVERGENCES:
            pytest.skip(f"{fid} 是已知分歧项，由 TestSemanticDivergencesExplicit 守门")
        fe_val = eval_formula_engine(formula)
        re_val = eval_report_engine(formula)
        assert fe_val == re_val, (
            f"[意外分歧] {fid} ({desc}) formula_engine={fe_val} != report_engine={re_val}\n"
            f"  公式: {formula}\n  ⟹ 之前一致的公式现出现分歧，须人工复核。"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 3：纯算术内核 4 套一致（关联属性 Q4 解析往返的算术部分）
#   含 cell_formula_evaluator（底稿 Excel 语法域）—— 它对纯算术 '100+200*3' 也应 == 700。
# ═══════════════════════════════════════════════════════════════════════════════

class TestArithmeticCoreConvergence:
    """4 套引擎的安全算术求值内核对纯算术表达式应逐位一致。"""

    ARITH_CASES = [
        ("100+200*3", Decimal("700")),
        ("(1+2)*3", Decimal("9")),
        ("100-50", Decimal("50")),
        ("100/4", Decimal("25")),
        ("100/0", Decimal("0")),   # 4 套统一约定除零 → 0
    ]

    @pytest.mark.parametrize("expr,expected", ARITH_CASES)
    def test_formula_engine_arith(self, expr, expected):
        assert safe_eval_expr(expr) == expected

    @pytest.mark.parametrize("expr,expected", ARITH_CASES)
    def test_report_engine_arith(self, expr, expected):
        assert re_safe_eval(expr) == expected

    @pytest.mark.parametrize("expr,expected", ARITH_CASES)
    def test_cell_formula_evaluator_arith(self, expr, expected):
        # cell_formula_evaluator 返回 float（Excel 语法域，非 Decimal）
        result = fu_safe_eval(expr)
        assert Decimal(str(result)) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 测试 4：cell_formula_evaluator 语法域隔离佐证（底稿 Excel 公式，非报表 DSL）
#   记录 cell_formula_evaluator 对报表 DSL token 的「不识别」行为，固化语法域边界（需求 5.3）。
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormulaUnifiedDomainIsolation:
    """cell_formula_evaluator 处理的是底稿 Excel 单元格语法，与报表 DSL 是不同语法域。"""

    def test_report_dsl_tb_not_a_unified_crossref(self):
        """报表 DSL 的 TB('1002','期末余额')（带引号）不是 cell_formula_evaluator 的 TB(1001,审定数) 跨表引用。"""
        parsed = fu_parse("TB('1002','期末余额')")
        # cell_formula_evaluator 的 _TB_RE 期望 TB(无引号参数) → 带引号的报表 DSL 不匹配为干净的 TB 跨表引用
        # 固化：报表 DSL 语法对 cell_formula_evaluator 而言不是其原生 TB 语义
        assert parsed["raw"] == "TB('1002','期末余额')"

    def test_excel_cell_is_unified_native(self):
        """底稿 Excel 单元格语法 =B2+B3 是 cell_formula_evaluator 的原生语法域。"""
        parsed = fu_parse("=B2+B3")
        addrs = {r["addr"] for r in parsed["references"]}
        assert addrs == {"B2", "B3"}
        assert parsed["type"] == "simple"

    def test_excel_arithmetic_via_cells(self):
        """=B2+B3 经 sheet_cells 求值（Excel 语法域），佐证它与报表 DSL 取数路径完全不同。"""
        cells = {
            "1:1": {"value": 50000},   # B2 → row=1,col=1
            "2:1": {"value": 1200000}, # B3 → row=2,col=1
        }
        res = _run(fu_execute("=B2+B3", db=None, project_id=None, year=2024, sheet_cells=cells))
        assert res["value"] == 1250000.0
        assert res["error"] is None
