"""三类型公式的运行态定性登记（单一真源）。

spec: formula-management-runtime-closure Task 11（Requirements 6.3, 6.4, 6.6）

三类型 = ``auto_calc``（自动运算）/ ``logic_check``（逻辑判断）/
``reasonability``（合理性提示）。2026-08-06 全链只读实证结论：

| 类型 | 执行入口 | 外部调用方 | 落库 | 实测 |
|---|---|---|---|---|
| auto_calc | `_exec_auto_calc` / `_batch_exec_auto_calc` | `coordinator.execute_batch`（依赖 `wp_formula`，实测 0 行）| mutation plan → adapter | 空转 |
| logic_check | `execute_report_cross_checks` | `formula_logic_check.py` 的 GET 端点 | `cross_check_results`（Task 10 已接线）| 可达 |
| reasonability | `_exec_reasonability` / `_batch_exec_reasonability` | 同 auto_calc | `hints` → 面板 hint_text（Task 2 已展示）| 空转 |

🔴 **「空转」不等于「死代码」**：`auto_calc` / `reasonability` 的执行入口**有**
非测试调用方（`coordinator.execute_batch`），只是上游 `wp_formula` 为 0 行导致
`_load_formulas` early-return。故处置是「保留 + 让空结果可见」（Task 11 已给
`generate_mutation_plan` 加 `kind='no_formulas'` 的 `scope_failures`），
**不是删函数**。

守卫 `test_formula_type_runtime_status.py` 按本模块断言：
三类型齐备 · 每条执行入口都有生产调用方 · 实测状态非空且带日期 ·
用替身数据验证执行链可达（不因真实库为空而跳过 / R6.5）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 三类型取值域（与 `wp_formula.formula_type` 一致；前端中文标签真源在
#: `formulaEngineInventory.FORMULA_TYPE_LABEL`，本模块不重复标签表）。
FORMULA_TYPES: tuple[str, ...] = ("auto_calc", "logic_check", "reasonability")


@dataclass(frozen=True)
class TypeRuntimeStatus:
    """一个公式类型的运行态登记。"""

    formula_type: str
    #: 单条执行入口（engine 内部）
    exec_entry: str
    #: 批量执行入口（engine 内部）
    batch_entry: str
    #: `backend/app/**` 非测试调用方（空元组即孤儿 → 守卫打红）
    production_callers: tuple[str, ...]
    #: 产出落到哪里（表名或去向）
    output_sink: str
    #: 实测状态，必须含实测日期
    measured: str


FORMULA_TYPE_RUNTIME_STATUS: tuple[TypeRuntimeStatus, ...] = (
    TypeRuntimeStatus(
        formula_type="auto_calc",
        exec_entry="app/services/formula_management/engine.py::_exec_auto_calc",
        batch_entry="app/services/formula_management/engine.py::_batch_exec_auto_calc",
        production_callers=(
            "app/services/formula_management/engine.py::execute_formula",
            "app/services/formula_management/engine.py::execute_batch",
            "app/services/formula_runtime/coordinator.py"
            "::FormulaRuntimeCoordinator.generate_mutation_plan",
        ),
        output_sink="MutationIntent → FormulaMutation（adapter prepare_many）→ 领域存储",
        measured=(
            "2026-08-06 实测空转：唯一外部路径 coordinator.execute_batch 依赖 "
            "wp_formula（全库 0 行）⇒ _load_formulas early-return。"
            "2026-08-07 Task 11 已让该 early-return 产出 kind='no_formulas' "
            "的 scope_failures，空转对用户可见"
        ),
    ),
    TypeRuntimeStatus(
        formula_type="logic_check",
        exec_entry="app/services/formula_management/engine.py::_exec_logic_check",
        batch_entry="app/services/formula_management/engine.py::_batch_exec_logic_check",
        production_callers=(
            "app/services/formula_management/logic_check.py::run_cross_checks",
            "app/services/formula_management/logic_check.py"
            "::execute_report_cross_checks",
            "app/routers/formula_logic_check.py::run_report_cross_check "
            "(GET /api/projects/{project_id}/formula/report-cross-check)",
        ),
        output_sink="cross_check_results 表（Task 10 接线）+ 响应体 Issue_List",
        measured=(
            "2026-08-06 实证调用链连通（router → execute_report_cross_checks → "
            "run_cross_checks → build_cross_check_formulas），唯一缺口是结果不落库；"
            "2026-08-07 Task 10 已补 persist_cross_check_results（fail-open + upsert）"
        ),
    ),
    TypeRuntimeStatus(
        formula_type="reasonability",
        exec_entry="app/services/formula_management/engine.py::_exec_reasonability",
        batch_entry=(
            "app/services/formula_management/engine.py::_batch_exec_reasonability"
        ),
        production_callers=(
            "app/services/formula_management/engine.py::execute_formula",
            "app/services/formula_management/engine.py::execute_batch",
            "app/services/formula_runtime/coordinator.py"
            "::FormulaRuntimeCoordinator.generate_mutation_plan",
        ),
        output_sink=(
            "HintItem.hint_text → MutationPlanResult.hints；"
            "持久化后经 wp_formula.hint_text 由 FormulaStatusPanel 展示（Task 2）"
        ),
        measured=(
            "2026-08-06 实测空转（成因同 auto_calc）；产出字段 hint_text 在底稿面板"
            "改造前完全不展示（命中 0），2026-08-07 Task 2 已补展示"
        ),
    ),
)


def status_of(formula_type: str) -> TypeRuntimeStatus | None:
    """按类型取登记条目；未登记返回 ``None``。"""
    for entry in FORMULA_TYPE_RUNTIME_STATUS:
        if entry.formula_type == formula_type:
            return entry
    return None


def registered_types() -> tuple[str, ...]:
    """已登记类型（守卫用它与 ``FORMULA_TYPES`` 做集合精确相等断言）。"""
    return tuple(e.formula_type for e in FORMULA_TYPE_RUNTIME_STATUS)
