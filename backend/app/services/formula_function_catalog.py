"""公式函数目录——全平台函数表的唯一来源（S1 ADR-FGR-01）。

每个函数一条 ``FunctionSpec``，登记它属于哪些求值器引擎、参数个数范围、
语法说明与分类。后端三处（``formula_arity`` / ``_REGISTRY`` / ``formula_grammar``）
与前端（``formulaFunctionCatalog.ts``，由生成器产出）都从这里派生。

引擎分三套：
- ``l1``：L1 内核（报表 / 试算表明细 / 表间审核 / 中央执行 / 底稿公式 / 推送共用）
- ``note``：附注执行器（``note_formula_generator``，正则解析，含 PRIOR / AGING / REGION）
- ``cell``：底稿单元格求值器（``cell_formula_evaluator``，Excel 式坐标 + AST）

运算符按引擎分别登记。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class FunctionSpec:
    """一个公式函数的规格。"""

    name: str
    """函数名（大写，如 ``TB`` / ``PRIOR``）。"""

    arity_min: int
    """最少参数个数。"""

    arity_max: int | None
    """最多参数个数；``None`` 表示不限（如 ``MAX``、``MIN``）。"""

    engines: frozenset[str]
    """该函数在哪些引擎下可用：``{"l1", "note", "cell"}`` 的子集。"""

    category: str
    """分类：取数 / 引用 / 数学 / 逻辑 / 底稿取数 / 附注取数。"""

    syntax: str
    """语法示例（中文，显示在前端提示里）。"""

    description: str = ""
    """功能说明。"""


@dataclass(frozen=True)
class OperatorSpec:
    """一个运算符的规格。"""

    symbol: str
    engines: frozenset[str]


# ── 引擎常量 ────────────────────────────────────────────────────────────────

L1 = "l1"
NOTE = "note"
CELL = "cell"
ALL_ENGINES = frozenset({L1, NOTE, CELL})
L1_ONLY = frozenset({L1})
NOTE_ONLY = frozenset({NOTE})
CELL_ONLY = frozenset({CELL})
L1_NOTE = frozenset({L1, NOTE})
L1_CELL = frozenset({L1, CELL})
NOTE_CELL = frozenset({NOTE, CELL})


# ── 函数目录 ────────────────────────────────────────────────────────────────

FUNCTIONS: tuple[FunctionSpec, ...] = (
    # ── 取数 ──
    FunctionSpec(
        name="TB", arity_min=1, arity_max=2, engines=L1_NOTE,
        category="取数",
        syntax="TB('科目编码'[,'列名'])",
        description="取科目余额",
    ),
    FunctionSpec(
        name="SUM_TB", arity_min=1, arity_max=2, engines=L1_ONLY,
        category="取数",
        syntax="SUM_TB('起始~结束'[,'列名'])",
        description="范围科目求和",
    ),
    FunctionSpec(
        name="PREV", arity_min=2, arity_max=3, engines=L1_ONLY,
        category="取数",
        syntax="PREV('科目','列名') / PREV('底稿','表','字段')",
        description="上年同期值",
    ),
    FunctionSpec(
        name="AUX", arity_min=2, arity_max=4, engines=L1_ONLY,
        category="取数",
        syntax="AUX('科目','维度'[,'辅助项'],'列名')",
        description="辅助核算取值",
    ),
    FunctionSpec(
        name="NOTE", arity_min=2, arity_max=3, engines=L1_NOTE,
        category="取数",
        syntax="NOTE('章节','行'[,'列'])",
        description="附注数据取值",
    ),
    FunctionSpec(
        name="WP", arity_min=2, arity_max=3, engines=L1_NOTE,
        category="取数",
        syntax="WP('底稿编码','列名|单元格') / WP('底稿','表','锚点')",
        description="底稿数据取值",
    ),
    FunctionSpec(
        name="ADJ", arity_min=1, arity_max=2, engines=L1_ONLY,
        category="取数",
        syntax="ADJ('科目编码'[,'aje_net|rje_net'])",
        description="调整额实时汇总（净额）",
    ),

    # ── 引用 ──
    FunctionSpec(
        name="ROW", arity_min=1, arity_max=1, engines=L1_ONLY,
        category="引用",
        syntax="ROW('行次编码')",
        description="引用其他行次",
    ),
    FunctionSpec(
        name="SUM_ROW", arity_min=2, arity_max=2, engines=L1_ONLY,
        category="引用",
        syntax="SUM_ROW('起始','结束')",
        description="范围行次求和",
    ),
    FunctionSpec(
        name="REPORT", arity_min=1, arity_max=2, engines=L1_NOTE,
        category="引用",
        syntax="REPORT('行次编码'[,'期间'])",
        description="跨报表引用",
    ),

    # ── 数学 / 逻辑 ──
    FunctionSpec(
        name="ABS", arity_min=1, arity_max=1, engines=ALL_ENGINES,
        category="数学",
        syntax="ABS(值)",
        description="绝对值",
    ),
    FunctionSpec(
        name="ROUND", arity_min=1, arity_max=2, engines=ALL_ENGINES,
        category="数学",
        syntax="ROUND(值[,位数])",
        description="四舍五入",
    ),
    FunctionSpec(
        name="MAX", arity_min=2, arity_max=None, engines=ALL_ENGINES,
        category="数学",
        syntax="MAX(值1, 值2[, ...])",
        description="最大值",
    ),
    FunctionSpec(
        name="MIN", arity_min=2, arity_max=None, engines=ALL_ENGINES,
        category="数学",
        syntax="MIN(值1, 值2[, ...])",
        description="最小值",
    ),
    FunctionSpec(
        name="IF", arity_min=3, arity_max=3, engines=ALL_ENGINES,
        category="逻辑",
        syntax="IF(条件, 真值, 假值)",
        description="条件判断",
    ),

    # ── 底稿预填函数（L1 handler 从 ctx 取值）──
    FunctionSpec(
        name="LEDGER", arity_min=2, arity_max=3, engines=L1_ONLY,
        category="底稿取数",
        syntax="LEDGER('科目','方向'[,'范围'])",
        description="序时账取数",
    ),
    FunctionSpec(
        name="LEDGER_DETAIL", arity_min=1, arity_max=3, engines=L1_ONLY,
        category="底稿取数",
        syntax="LEDGER_DETAIL('科目'[,'期间'][,'金额条件'])",
        description="序时账明细筛选",
    ),
    FunctionSpec(
        name="TB_AUX", arity_min=3, arity_max=3, engines=L1_ONLY,
        category="底稿取数",
        syntax="TB_AUX('科目','维度','列名')",
        description="辅助维度汇总",
    ),
    FunctionSpec(
        name="COUNT_LEDGER", arity_min=1, arity_max=2, engines=L1_ONLY,
        category="底稿取数",
        syntax="COUNT_LEDGER('科目'[,'范围'])",
        description="序时账笔数统计",
    ),
    FunctionSpec(
        name="PLACEHOLDER", arity_min=0, arity_max=1, engines=L1_ONLY,
        category="底稿取数",
        syntax="PLACEHOLDER()",
        description="预留占位",
    ),

    # ── 附注执行器专属函数 ──
    FunctionSpec(
        name="PRIOR", arity_min=2, arity_max=3, engines=NOTE_ONLY,
        category="附注取数",
        syntax="PRIOR('科目|章节','期末|期初') / PRIOR('章节','行','期末|期初')",
        description="上年附注取数（附注域专属，L1 请用 PREV）",
    ),
    FunctionSpec(
        name="AGING", arity_min=2, arity_max=2, engines=NOTE_ONLY,
        category="附注取数",
        syntax="AGING('科目','桶名')",
        description="账龄分桶取数",
    ),
    FunctionSpec(
        name="REGION", arity_min=2, arity_max=3, engines=NOTE_ONLY,
        category="附注取数",
        syntax="REGION('区域名','列'[,agg='sum'])",
        description="表内动态区域取数",
    ),
    FunctionSpec(
        name="SUM", arity_min=2, arity_max=2, engines=NOTE_ONLY,
        category="附注取数",
        syntax="SUM(起始行:结束行, 列)",
        description="表内行范围求和（附注域）",
    ),
    FunctionSpec(
        name="cell", arity_min=2, arity_max=2, engines=NOTE_ONLY,
        category="附注取数",
        syntax="cell(行, 列)",
        description="表内单元格引用（附注域）",
    ),
)


# ── 运算符目录 ──────────────────────────────────────────────────────────────

OPERATORS: tuple[OperatorSpec, ...] = (
    OperatorSpec("+", ALL_ENGINES),
    OperatorSpec("-", ALL_ENGINES),
    OperatorSpec("*", ALL_ENGINES),
    OperatorSpec("/", ALL_ENGINES),
    # % 不在任何后端引擎中支持（L1 词法不认、附注/单元格不解析）
    # 前端 S1 批 1 任务 2 删除
    OperatorSpec("=", L1_ONLY),
    OperatorSpec("<", L1_ONLY),
    OperatorSpec(">", L1_ONLY),
    OperatorSpec(">=", L1_ONLY),
    OperatorSpec("<=", L1_ONLY),
    OperatorSpec("!=", L1_ONLY),
)


# ── 查询 API ───────────────────────────────────────────────────────────────

_BY_NAME: dict[str, FunctionSpec] = {f.name: f for f in FUNCTIONS}


def get(name: str) -> FunctionSpec | None:
    """按名字查函数规格；未登记返回 ``None``。"""
    return _BY_NAME.get(name)


def functions_for_engine(engine: str) -> list[FunctionSpec]:
    """返回指定引擎下可用的全部函数（按名字排序）。"""
    return sorted(
        (f for f in FUNCTIONS if engine in f.engines),
        key=lambda f: f.name,
    )


def function_names_for_engine(engine: str) -> frozenset[str]:
    """返回指定引擎下可用的函数名集合。"""
    return frozenset(f.name for f in FUNCTIONS if engine in f.engines)


def operators_for_engine(engine: str) -> list[str]:
    """返回指定引擎下可用的运算符列表。"""
    return [o.symbol for o in OPERATORS if engine in o.engines]


def arity_dict(engine: str | None = None) -> dict[str, tuple[int, int | None]]:
    """返回 ``{函数名: (最少参数, 最多参数)}`` 字典。

    ``engine=None`` 返回全部函数；指定引擎只返回该引擎的函数。
    """
    return {
        f.name: (f.arity_min, f.arity_max)
        for f in FUNCTIONS
        if engine is None or engine in f.engines
    }


# ── L1 引擎名单（与 formula_arity.BUILTIN_FUNCTION_NAMES 同义）────────────

L1_FUNCTION_NAMES: frozenset[str] = function_names_for_engine(L1)
"""L1 内核的全部函数名（与 ``formula_arity.BUILTIN_FUNCTION_NAMES`` 同一集合）。"""
