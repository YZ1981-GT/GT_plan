"""函数支持矩阵单一真源（spec formula-manager-closure · Task 4.2 / 需求 8）。

一张「函数 × 执行器 → 支持 / 不支持」矩阵，禁「UI 能点、点了静默返 0」。

四个执行器维度（design §5 步骤 4、§1 报告第三/五/九节；现状均由源码 grep 实证，
**非凭命名推测**，memory 铁律⑭）：

- ``wp_evaluator`` = 当前可保存并由 ``evaluate_wp_formula_expression`` 求值的工作底稿公式路径。
  该路径只真实实现 TB/SUM_TB/WP（另含字面量、四则运算与已解析 sheet 引用）；L1
  ``_REGISTRY`` 注册不等于请求上下文已注入，故 ROW/SUM_ROW/REPORT/NOTE/PREV/AUX/ADJ
  在本执行器均 fail-closed 判不支持。通用 ``/api/formula`` 按 ``central_batch`` 能力校验。

- ``report_path`` = ``app.services.report_engine.evaluate_formula_result``。
  现状实证：TB/SUM_TB/ROW/SUM_ROW/REPORT 经 resolver 预载求值（report_engine.py
  ~L860-918）；WP/NOTE 不再硬置 0 改为预载（~L879-918）；**PREV 与 AUX 被硬替换成
  字面 "0"**（``_PREV_PATTERN``/``_AUX_PATTERN`` finditer → replace("0")，~L872-877）
  —— 这就是需求 8「report 路径当前强制 PREV/AUX=0」的静默 0。ADJ 仅当调用方注入
  ``adj_data`` 才非 0（否则 ctx.adj_data 为空 → 返 0），故对「中央执行器自身」判不支持，
  真正注入在 ``central_batch`` 维度。

- ``note_executor`` = ``app.services.note_formula_generator``（``execute_note_formulas`` +
  ``_resolve_single_cross_ref``）。现状实证：支持 TB/REPORT/NOTE/WP + 本地 PRIOR/AGING +
  表内 cell/SUM（note_formula_generator.py ~L925-1051 的分支）；**不解析 SUM_TB/ROW/
  SUM_ROW/PREV/AUX/ADJ**（附注用 PRIOR 取上年、AGING 取账龄，不是 PREV/AUX）。

- ``central_batch`` = 中央公式管理执行批（ADJ 实时注入）。现状实证：``FormulaContext``
  有 ``adj_data`` 字段、``_handle_adj`` 消费它（formula_engine.py ~L906-938）；只要调用方
  传 ``adj_map`` 即真支持 ADJ 实时汇总。本维度把 ADJ 标为支持，表达「中央 batch 应当
  注入 ADJ 实时数据而非静默返 0」（需求 8.4）。

矩阵是**单一真源**：后端此处为权威，前端 ``functionSupportMatrix.ts`` 据同一张 golden
对照（``tests/fixtures/function_support_matrix.json`` 由本模块 ``build_matrix_payload()``
重算生成），两侧对拍 ⇒ 前端渲染 == 后端真相（与 stable_key 归一对拍同一模式）。
"""

from __future__ import annotations

from enum import Enum


class Executor(str, Enum):
    """四个执行器维度（design §5 步骤 4）。"""

    WP_EVALUATOR = "wp_evaluator"
    REPORT_PATH = "report_path"
    NOTE_EXECUTOR = "note_executor"
    CENTRAL_BATCH = "central_batch"


#: UI 工具栏当前提供/可提供的取数函数（FormulaBar.vue 的取数按钮全集 + 报告点名的
#: PREV/AUX/ADJ）。顺序即 UI 展示建议顺序。禁写死进判据外的别处——以此为准。
FUNCTIONS: tuple[str, ...] = (
    "TB",
    "SUM_TB",
    "ROW",
    "SUM_ROW",
    "REPORT",
    "NOTE",
    "WP",
    "PREV",
    "AUX",
    "ADJ",
)


#: 「函数 × 执行器 → 是否支持」。True=支持（运行产生真实结果）；False=不支持
#: （UI 必须显式禁用/标注，禁静默 0）。每一格的依据见模块 docstring 的逐执行器实证。
_SUPPORT: dict[str, dict[Executor, bool]] = {
    # wp_evaluator = 当前可保存工作底稿公式路径；只承诺真实具备上下文的 TB/SUM_TB/WP。
    "TB":     {Executor.WP_EVALUATOR: True,  Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: True,  Executor.CENTRAL_BATCH: True},
    "SUM_TB": {Executor.WP_EVALUATOR: True,  Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
    "ROW":    {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
    "SUM_ROW":{Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
    "REPORT": {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: True,  Executor.CENTRAL_BATCH: True},
    "NOTE":   {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: True,  Executor.CENTRAL_BATCH: True},
    "WP":     {Executor.WP_EVALUATOR: True,  Executor.REPORT_PATH: True,  Executor.NOTE_EXECUTOR: True,  Executor.CENTRAL_BATCH: True},
    "PREV":   {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: False, Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
    "AUX":    {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: False, Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
    "ADJ":    {Executor.WP_EVALUATOR: False, Executor.REPORT_PATH: False, Executor.NOTE_EXECUTOR: False, Executor.CENTRAL_BATCH: True},
}


#: 每一格「不支持」的人类可读原因（UI 标注用；支持的格无原因）。缺原因即判矩阵不完整。
_UNSUPPORTED_REASON: dict[tuple[str, Executor], str] = {
    ("ROW", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未注入 ROW 行次上下文",
    ("SUM_ROW", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未注入 SUM_ROW 行次上下文",
    ("REPORT", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未注入报表上下文",
    ("NOTE", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未注入附注上下文",
    ("PREV", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未实现 PREV",
    ("AUX", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未实现 AUX",
    ("ADJ", Executor.WP_EVALUATOR): "工作底稿可编辑公式尚未注入实时调整上下文",
    ("SUM_TB", Executor.NOTE_EXECUTOR): "附注执行器不解析 SUM_TB（附注表内用 SUM 行区间）",
    ("ROW", Executor.NOTE_EXECUTOR): "附注执行器不解析 ROW（跨报表行引用用 REPORT）",
    ("SUM_ROW", Executor.NOTE_EXECUTOR): "附注执行器不解析 SUM_ROW",
    ("PREV", Executor.REPORT_PATH): "报表路径对 PREV 恒置 0（上期值走报表 prior 列，非 PREV）",
    ("PREV", Executor.NOTE_EXECUTOR): "附注执行器用 PRIOR 取上年附注，不解析 PREV",
    ("AUX", Executor.REPORT_PATH): "报表路径对 AUX 恒置 0（辅助核算不进报表求值）",
    ("AUX", Executor.NOTE_EXECUTOR): "附注执行器用 AGING 取账龄分桶，不解析 AUX",
    ("ADJ", Executor.REPORT_PATH): "报表路径默认不注入实时调整额（走 central_batch 注入）",
    ("ADJ", Executor.NOTE_EXECUTOR): "附注执行器不解析 ADJ",
}


def is_supported(function: str, executor: Executor | str) -> bool:
    """函数在某执行器是否支持。未知函数/执行器 fail-closed 判不支持。"""
    exe = Executor(executor) if not isinstance(executor, Executor) else executor
    row = _SUPPORT.get(function)
    if row is None:
        return False
    return bool(row.get(exe, False))


def unsupported_reason(function: str, executor: Executor | str) -> str | None:
    """不支持时的原因文案；支持时返 None。"""
    exe = Executor(executor) if not isinstance(executor, Executor) else executor
    if is_supported(function, exe):
        return None
    return _UNSUPPORTED_REASON.get((function, exe), "此执行器不支持该函数")


def build_matrix_payload() -> dict:
    """矩阵的序列化载荷（供 golden 生成 + 前端对拍 + 可选端点返回）。

    结构::

        {
          "schema_version": 1,
          "functions": ["TB", ...],
          "executors": ["wp_evaluator", ...],
          "matrix": {
            "TB": {"wp_evaluator": {"supported": true, "reason": null}, ...},
            ...
          }
        }
    """
    matrix: dict[str, dict[str, dict]] = {}
    for fn in FUNCTIONS:
        matrix[fn] = {}
        for exe in Executor:
            supported = is_supported(fn, exe)
            matrix[fn][exe.value] = {
                "supported": supported,
                "reason": None if supported else unsupported_reason(fn, exe),
            }
    return {
        "schema_version": 1,
        "functions": list(FUNCTIONS),
        "executors": [e.value for e in Executor],
        "matrix": matrix,
    }


class FormulaSupportViolation(ValueError):
    """公式包含当前执行器不支持的函数。"""

    def __init__(self, executor: Executor, issues: list[dict[str, str]]) -> None:
        self.executor = executor
        self.issues = issues
        names = "/".join(issue["function"] for issue in issues)
        super().__init__(f"执行器 {executor.value} 不支持函数：{names}")


def expression_functions(expression: str | None) -> list[str]:
    """按出现顺序提取平台已登记函数名；未知函数由 L1 语法白名单负责拒绝。"""
    import re

    if not expression:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression):
        name = match.group(1).upper()
        if name in _SUPPORT and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def support_issues(expression: str | None, executor: Executor | str) -> list[dict[str, str]]:
    """返回表达式在指定执行器中的不支持函数，供所有生产入口统一 preflight。"""
    exe = Executor(executor) if not isinstance(executor, Executor) else executor
    return [
        {
            "function": name,
            "executor": exe.value,
            "reason": unsupported_reason(name, exe) or "此执行器不支持该函数",
        }
        for name in expression_functions(expression)
        if not is_supported(name, exe)
    ]


def require_expression_support(expression: str | None, executor: Executor | str) -> None:
    """不支持即抛结构化异常；生产路由将其转换为 422，禁止静默 0。"""
    exe = Executor(executor) if not isinstance(executor, Executor) else executor
    issues = support_issues(expression, exe)
    if issues:
        raise FormulaSupportViolation(exe, issues)


def require_function_support(function: str, executor: Executor | str) -> None:
    """校验按类型调用的单一函数 API。"""
    exe = Executor(executor) if not isinstance(executor, Executor) else executor
    name = (function or "").strip().upper()
    if not is_supported(name, exe):
        raise FormulaSupportViolation(
            exe,
            [{
                "function": name or "<empty>",
                "executor": exe.value,
                "reason": unsupported_reason(name, exe) or "此执行器不支持该函数",
            }],
        )
