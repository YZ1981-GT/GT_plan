"""公式引擎类型分派层（Formula Management Library · engine）。

本模块是**编排薄层**，不新建求值内核：所有求值统一委托后端唯一 L1 内核
``app.services.formula_engine.execute``（Req 25.1/25.2），所有引用地址解析
统一走 ACNR ``full_resolve``（Req 11，经 ``resolve_ref`` 封装，fail-open）。

三类型公式分派语义（design §Components 2 / Data Models §5）：

- ``auto_calc``     求值 → 回填目标单元 → 记 ``last_computed_at``；
                    求值失败保留目标单元原值、**不写时间戳**（Req 5.5）。
- ``logic_check``   求条件 → 不通过时向 Issue_List 追加一条问题项；条件**无法
                    求值**时追加「公式无法求值」项（**不静默跳过**，Req 6.6）；
                    **绝不修改任何数据单元值**（Req 6.3）。
- ``reasonability`` 求条件 → 成立时向 Hint_List 追加一条提醒项；条件无法求值时
                    记 WARNING 日志并跳过该提示、**不中断**其余公式（Req 7.5）；
                    **绝不修改任何数据单元值**（Req 7.3）。

约束：禁止在公式引用中拼接 ``wp_code+sheet+cell`` 裸字符串（Req 11.5），
引用一律以 ``addr_id`` / ``formula_ref`` 形式经 ``resolve_ref`` 解析。

Batch Runtime 入口（Task 12，Req 1,2,5,11｜P1,P6,P14）：

- ``execute_batch`` 接收预加载 ``BatchFormulaContext`` 与公式定义列表，不逐 ref
  resolve，直接以 addr_id→value 映射驱动求值。
- auto_calc 产出 ``MutationIntent``（不直接写值），由上层确认 computed time。
- logic_check / reasonability 只产 issue/hint，不产 mutation。
- 返回 ``BatchExecutionResult`` 包含 intents、issues、hints、errors。

Requirements: 1.1, 1.2, 2.1, 5.1, 5.2, 5.4, 5.5, 6.1, 6.2, 6.6, 7.1, 7.2, 7.5,
              11.1, 11.2, 11.3, 11.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# 单一求值内核（Req 25）：本模块只做类型分派，不新增并行求值实现。
from app.services.formula_engine import FormulaContext, execute as kernel_execute

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 输入模型：FormulaRecord（跨底稿/报表/附注统一视图，design Data Models）
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FormulaRecord:
    """归一化的公式定义输入（与 ORM/DB 解耦，便于单测与跨域复用）。

    - ``target_cell``：auto_calc 的回填目标；logic_check / reasonability 的承载单元。
    - ``expression``：auto_calc 计算式 / logic_check 条件 / reasonability 触发条件。
    - ``refs``：规范化引用列表，每项为 ``{"addr_id": ...}`` 或 ``{"formula_ref": ...}``，
      亦兼容裸 ``formula_ref`` 字符串；**禁止**裸 ``wp_code+sheet+cell`` 拼接串。
    - ``addr_id``：本公式承载单元的 canonical addr_id（供 Issue/Hint 溯源）。
    """

    id: str
    formula_type: str  # auto_calc | logic_check | reasonability
    target_cell: str
    expression: str
    issue_description: Optional[str] = None
    hint_text: Optional[str] = None
    refs: list[Any] = field(default_factory=list)
    addr_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 结果结构：IssueItem / HintItem / FormulaExecResult（design Data Models §5）
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class IssueItem:
    """logic_check 产出的问题项（不修改任何数据值）。"""

    formula_id: str
    addr_id: Optional[str]
    description: str
    left_value: Optional[Decimal] = None
    right_value: Optional[Decimal] = None


@dataclass
class HintItem:
    """reasonability 产出的提醒项（不修改任何数据值）。"""

    formula_id: str
    addr_id: Optional[str]
    hint_text: str


@dataclass
class FormulaExecResult:
    """三类型公式执行结果。

    - ``updated_cells`` / ``values``：仅 auto_calc 成功回填时非空。
    - ``issues``：logic_check 产出。
    - ``hints``：reasonability 产出。
    - ``errors``：auto_calc 求值失败等描述性错误（不阻断批次其余执行）。
    - ``last_computed_at``：成功执行时刻；求值失败时保持 ``None``（不写时间戳）。
    """

    formula_id: str
    formula_type: str
    updated_cells: list[str] = field(default_factory=list)
    values: dict[str, Decimal] = field(default_factory=dict)
    issues: list[IssueItem] = field(default_factory=list)
    hints: list[HintItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    last_computed_at: Optional[datetime] = None


# 数据回填回调：auto_calc 成功后可选地把值写入领域存储（底稿/报表单元）。
ApplyValue = Callable[[str, Decimal], Any]


# ─────────────────────────────────────────────────────────────────────────────
# 引用解析封装（Req 11，Task 2.1 契约）：统一走 ACNR full_resolve，fail-open。
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResolveRefResult:
    """``resolve_ref`` 统一返回契约（封装 ACNR ``ResolveResult``）。

    - ``found``：ACNR 是否命中该引用。
    - ``addr_id``：命中时为 canonical addr_id（引用身份，Req 11.2）；未命中时回显入参。
    - ``fail_open``：True 表示 ACNR 基础设施异常已 fail-open 回退（Req 11.3）。
    """

    found: bool
    addr_id: Optional[str] = None
    formula_ref: Optional[str] = None
    semantic_label: Optional[str] = None
    fail_open: bool = False
    error: Optional[str] = None


async def resolve_ref(
    *,
    formula_ref: str | None = None,
    addr_id: str | None = None,
    project_id: str | None = None,
    db: AsyncSession | None = None,
) -> ResolveRefResult:
    """封装 ACNR ``full_resolve``（Req 11）。

    - ``found=true``  → 以返回的 canonical ``addr_id`` 作为引用身份（Req 11.2）。
    - 基础设施异常 → 记 WARNING 结构化日志 + **fail-open** 回退（Req 11.3），返回
      ``found=False`` 且 ``fail_open=True`` 的降级结果，**绝不因解析器故障阻断
      公式执行**。

    禁止拼接 ``wp_code+sheet+cell`` 裸字符串（Req 11.5）；调用方以 ``addr_id`` /
    ``formula_ref`` 传入。

    Requirements: 11.1, 11.2, 11.3, 11.5
    """
    # 延迟导入避免与 resolver 潜在的循环依赖，并便于测试打桩。
    from app.services.acnr.resolver import full_resolve

    try:
        rr = await full_resolve(
            formula_ref=formula_ref,
            addr_id=addr_id,
            project_id=project_id,
            db=db,
        )
        return ResolveRefResult(
            found=bool(rr.found),
            # found → canonical addr_id 作引用身份；miss → 回显入参供溯源。
            addr_id=(rr.addr_id if rr.found else addr_id),
            formula_ref=(rr.formula_ref or formula_ref),
            semantic_label=rr.semantic_label,
            fail_open=False,
            error=rr.error,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open：resolver 故障不阻断执行
        logger.warning(
            "resolve_ref fail-open：ACNR full_resolve 异常，回退降级不阻断 "
            "(formula_ref=%s addr_id=%s project_id=%s): %s",
            formula_ref,
            addr_id,
            project_id,
            exc,
        )
        return ResolveRefResult(
            found=False,
            addr_id=addr_id,
            formula_ref=formula_ref,
            fail_open=True,
            error="acnr_unavailable_fallback",
        )


def _normalize_ref(ref: Any) -> tuple[str | None, str | None]:
    """把一条引用归一化为 ``(formula_ref, addr_id)``。

    支持三种形态：``{"formula_ref": ...}`` / ``{"addr_id": ...}`` / 裸字符串
    （按 formula_ref 处理）。
    """
    if isinstance(ref, dict):
        return ref.get("formula_ref"), ref.get("addr_id")
    if isinstance(ref, str):
        return ref, None
    return None, None


async def _resolve_formula_refs(
    formula: FormulaRecord,
    *,
    project_id: str | None,
    db: AsyncSession | None,
) -> list[Any]:
    """对 ``formula.refs`` 逐条经 ``resolve_ref`` 解析（Req 11.1）。

    解析结果仅用于建立 canonical 引用身份 / 记录，不改变求值上下文
    （求值数据由 ``FormulaContext`` 预载）。fail-open 由 ``resolve_ref`` 保证。
    """
    resolved: list[Any] = []
    for ref in formula.refs or []:
        formula_ref, addr_id = _normalize_ref(ref)
        if formula_ref is None and addr_id is None:
            continue
        resolved.append(
            await resolve_ref(
                formula_ref=formula_ref,
                addr_id=addr_id,
                project_id=project_id,
                db=db,
            )
        )
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# 类型分派主入口
# ─────────────────────────────────────────────────────────────────────────────
async def execute_formula(
    db: AsyncSession | None,
    *,
    formula: FormulaRecord,
    ctx: FormulaContext,
    project_id: str | None = None,
    apply_value: ApplyValue | None = None,
    resolve_refs: bool = True,
) -> FormulaExecResult:
    """按 ``formula_type`` 分派执行一条公式（design §Components 2）。

    - auto_calc     → 求值回填目标单元 + 记 ``last_computed_at``（失败保留原值不写时间戳）
    - logic_check   → 条件不通过追加 Issue_List（无法求值追加「公式无法求值」项，不静默跳过）
    - reasonability → 触发追加 Hint_List（无法求值记 WARNING 跳过、不中断）

    logic_check / reasonability 分支**绝不修改任何数据单元值**。引用解析统一走
    ``resolve_ref()``。

    Args:
        db: DB 会话（供 resolve_ref 的 ACNR 解析使用，可为 None）。
        formula: 归一化公式定义。
        ctx: 求值上下文（各域数据由 L2 编排层预载）。
        project_id: 项目 id（供引用解析 overlay / wp_id 附加）。
        apply_value: 可选回填回调；auto_calc 成功时以 ``(target_cell, value)`` 调用，
            由领域层写入实际存储（底稿/报表单元）。
        resolve_refs: 是否对 ``formula.refs`` 逐条经 ACNR 解析（默认 True）。

    Returns:
        FormulaExecResult。

    Requirements: 5.1, 5.2, 5.4, 5.5, 6.1, 6.2, 6.6, 7.1, 7.2, 7.5, 11.1, 11.2
    """
    # 引用一律经 ACNR full_resolve 解析（Req 11.1）；fail-open 不阻断执行。
    if resolve_refs:
        await _resolve_formula_refs(formula, project_id=project_id, db=db)

    ftype = (formula.formula_type or "auto_calc").strip()

    if ftype == "auto_calc":
        return _exec_auto_calc(formula, ctx, apply_value)
    if ftype == "logic_check":
        return _exec_logic_check(formula, ctx)
    if ftype == "reasonability":
        return _exec_reasonability(formula, ctx)

    # 未知类型：不改值、返回描述性错误。
    result = FormulaExecResult(formula_id=formula.id, formula_type=ftype)
    result.errors.append(f"未知公式类型: {ftype}")
    logger.warning("execute_formula 收到未知 formula_type=%s (id=%s)", ftype, formula.id)
    return result


def _exec_auto_calc(
    formula: FormulaRecord,
    ctx: FormulaContext,
    apply_value: ApplyValue | None,
) -> FormulaExecResult:
    """auto_calc：求值 → 回填目标单元 + 记 last_computed_at（Req 5.2/5.4）。

    求值失败（表达式非法/除零/类型错误）→ 返回描述性错误、**保留目标单元原值
    不变、不写 last_computed_at**（Req 5.5）。
    """
    result = FormulaExecResult(formula_id=formula.id, formula_type="auto_calc")

    # 四表库叶子源只读防御（Req 12.2）：绝不把 auto_calc 结果回填到四表库单元。
    # 定义/保存层已由 guard_four_table_leaf_readonly 拒绝；此处为执行期兜底，
    # 以非抛出方式记描述性错误并跳过回填，保留批次隔离（单条失败不阻断其余）。
    from app.services.formula_management.four_table_source import is_four_table_target

    if is_four_table_target(formula.target_cell):
        result.errors.append(
            f"四表库叶子源只读：拒绝 auto_calc 回填到四表库单元 {formula.target_cell!r}"
        )
        logger.warning(
            "auto_calc 目标为四表库单元，跳过回填 (id=%s cell=%s)",
            formula.id,
            formula.target_cell,
        )
        return result

    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        # 求值失败：保留原值，不回填、不写时间戳。
        result.errors.extend(fr.errors or [f"公式求值失败: {formula.expression}"])
        logger.warning(
            "auto_calc 求值失败，保留目标单元原值 (id=%s cell=%s): %s",
            formula.id,
            formula.target_cell,
            fr.errors,
        )
        return result

    value = fr.value
    result.values[formula.target_cell] = value
    result.updated_cells.append(formula.target_cell)
    # 回填到上下文，供后续公式经 ROW()/引用取到本次计算值。
    ctx.row_cache[formula.target_cell] = value
    if apply_value is not None:
        apply_value(formula.target_cell, value)
    result.last_computed_at = datetime.now(timezone.utc)
    return result


def _exec_logic_check(formula: FormulaRecord, ctx: FormulaContext) -> FormulaExecResult:
    """logic_check：条件不通过 → 追加 Issue_List；无法求值 → 追加「公式无法求值」项。

    **绝不修改任何数据单元值**（Req 6.3）。条件表达式求值为真（!=0）视为通过。
    无法求值时**不静默跳过**，追加标注「公式无法求值」的问题项（Req 6.6）。
    """
    result = FormulaExecResult(formula_id=formula.id, formula_type="logic_check")
    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        detail = f"（{'; '.join(fr.errors)}）" if fr.errors else ""
        base = formula.issue_description or formula.expression
        result.issues.append(
            IssueItem(
                formula_id=formula.id,
                addr_id=formula.addr_id,
                description=f"公式无法求值：{base}{detail}",
            )
        )
        return result

    passed = fr.value != Decimal("0")
    if not passed:
        result.issues.append(
            IssueItem(
                formula_id=formula.id,
                addr_id=formula.addr_id,
                description=formula.issue_description
                or f"逻辑判断不通过：{formula.expression}",
            )
        )
    result.last_computed_at = datetime.now(timezone.utc)
    return result


def _exec_reasonability(formula: FormulaRecord, ctx: FormulaContext) -> FormulaExecResult:
    """reasonability：触发条件成立 → 追加 Hint_List；无法求值 → 记 WARNING 跳过不中断。

    **绝不修改任何数据单元值**（Req 7.3）。触发条件求值为真（!=0）时追加提醒项。
    无法求值时记 WARNING 日志并跳过该提示、不中断其余公式执行（Req 7.5）。
    """
    result = FormulaExecResult(formula_id=formula.id, formula_type="reasonability")
    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        logger.warning(
            "reasonability 公式无法求值，跳过该提示（不中断）(id=%s expr=%s): %s",
            formula.id,
            formula.expression,
            fr.errors,
        )
        return result

    triggered = fr.value != Decimal("0")
    if triggered:
        result.hints.append(
            HintItem(
                formula_id=formula.id,
                addr_id=formula.addr_id,
                hint_text=formula.hint_text or f"合理性提示：{formula.expression}",
            )
        )
    result.last_computed_at = datetime.now(timezone.utc)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Batch Runtime 入口（Task 12，Req 1,2,5,11｜P1,P6,P14）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BatchFormulaContext:
    """预加载值，由 FormulaValueLoader 填充后传入 execute_batch。

    不再由 engine 逐 ref resolve——所有值已按 addr_id 批量预载。
    """

    values: dict[str, Any]  # addr_id → resolved value (Decimal/str/None)
    missing: set[str] = field(default_factory=set)  # addr_id that could not be resolved
    ambiguous: set[str] = field(default_factory=set)  # addr_id with multiple matches


@dataclass(frozen=True)
class CanonicalFormulaTarget:
    """公式目标身份（batch runtime 内部使用，与 contracts.py 同构）。"""

    domain: Literal["workpaper", "adjudication", "report", "note"]
    project_id: UUID
    year: int
    addr_id: str
    locator: dict[str, str] = field(default_factory=dict)
    wp_id: UUID | None = None


@dataclass
class BatchFormulaDefinition:
    """batch execute 输入的公式定义。"""

    id: str
    formula_type: str  # auto_calc | logic_check | reasonability
    expression: str
    target: CanonicalFormulaTarget | None = None  # auto_calc 写入目标
    ref_addr_ids: list[str] = field(default_factory=list)  # 引用的 addr_id 列表
    issue_description: str | None = None
    hint_text: str | None = None
    addr_id: str | None = None  # 本公式承载单元的 canonical addr_id


@dataclass
class MutationIntent:
    """auto_calc 求值结果——写入意图，NOT YET APPLIED。

    上层 coordinator 成功调用 adapter.apply_many 后才确认 computed time。
    """

    target: CanonicalFormulaTarget
    computed_value: Any
    formula_id: str
    formula_type: str  # auto_calc | logic_check | reasonability


@dataclass
class BatchExecutionResult:
    """batch formula execution 完整返回。"""

    intents: list[MutationIntent] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    hints: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _topological_sort_formulas(
    formulas: list[BatchFormulaDefinition],
) -> list[BatchFormulaDefinition]:
    """按引用依赖拓扑排序：被依赖的公式先执行（Kahn 算法）。

    - 构建依赖图：如果公式 A 的 target addr_id 出现在公式 B 的 ref_addr_ids → B 依赖 A
    - 循环依赖的公式保留相对原序（不抛错，degrade gracefully）
    - 无 target（logic_check/reasonability）的公式排在末尾（不产值，不影响其他）
    """
    if len(formulas) <= 1:
        return formulas

    # 构建 target_addr_id → formula index 映射
    target_to_idx: dict[str, int] = {}
    for i, f in enumerate(formulas):
        if f.target and hasattr(f.target, "addr_id") and f.target.addr_id:
            target_to_idx[f.target.addr_id] = i
        elif f.addr_id:
            target_to_idx[f.addr_id] = i

    # 构建邻接表 + 入度
    n = len(formulas)
    adj: list[list[int]] = [[] for _ in range(n)]
    in_degree = [0] * n

    for i, f in enumerate(formulas):
        for ref_id in f.ref_addr_ids:
            dep_idx = target_to_idx.get(ref_id)
            if dep_idx is not None and dep_idx != i:
                adj[dep_idx].append(i)
                in_degree[i] += 1

    # Kahn's BFS
    from collections import deque
    queue: deque[int] = deque()
    for i in range(n):
        if in_degree[i] == 0:
            queue.append(i)

    sorted_indices: list[int] = []
    while queue:
        node = queue.popleft()
        sorted_indices.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 循环依赖的节点（未被排入）保留原始相对顺序追加到末尾
    if len(sorted_indices) < n:
        visited = set(sorted_indices)
        for i in range(n):
            if i not in visited:
                sorted_indices.append(i)

    return [formulas[i] for i in sorted_indices]


def execute_batch(
    *,
    formulas: list[BatchFormulaDefinition],
    context: BatchFormulaContext,
) -> BatchExecutionResult:
    """Batch runtime 单一入口（Task 12，Req 1,2,5,11｜P1,P6,P14）。

    接收预加载 BatchFormulaContext 与公式定义列表。不逐 ref resolve（已由
    FormulaValueLoader 预载）。auto_calc 产出 MutationIntent，不直接写值，
    不写 last_computed_at——由上层 coordinator 成功 domain apply 后确认。

    - auto_calc：求值成功 → MutationIntent（intent to write）
    - logic_check：条件不通过 → issue；不产 mutation
    - reasonability：条件成立 → hint；不产 mutation
    - 引用在 missing/ambiguous 中 → 记 error，跳过该公式

    Args:
        formulas: 公式定义列表，含 canonical target 与 ref addr_ids。
        context: 预加载上下文（addr_id → value 映射）。

    Returns:
        BatchExecutionResult（intents, issues, hints, errors）。
    """
    result = BatchExecutionResult()

    # #2 拓扑排序：按引用依赖图排列执行顺序（被依赖者先执行），避免取值 miss。
    # 循环依赖的公式保留原序（degrade gracefully）。
    formulas = _topological_sort_formulas(formulas)

    # 构建 L1 内核 FormulaContext（从预载 addr_id→value 映射填充 row_cache）
    kernel_ctx = FormulaContext(row_cache={})
    for addr_id, value in context.values.items():
        if value is not None:
            try:
                kernel_ctx.row_cache[addr_id] = Decimal(str(value))
            except Exception:
                kernel_ctx.row_cache[addr_id] = Decimal("0")

    for formula in formulas:
        # 检查引用 addr_id 是否在 missing 或 ambiguous 中
        bad_refs = []
        for ref_id in formula.ref_addr_ids:
            if ref_id in context.missing:
                bad_refs.append(f"missing:{ref_id}")
            elif ref_id in context.ambiguous:
                bad_refs.append(f"ambiguous:{ref_id}")

        if bad_refs:
            result.errors.append({
                "formula_id": formula.id,
                "formula_type": formula.formula_type,
                "reason": "unresolved_refs",
                "refs": bad_refs,
            })
            continue

        ftype = (formula.formula_type or "auto_calc").strip()

        if ftype == "auto_calc":
            _batch_exec_auto_calc(formula, kernel_ctx, result)
        elif ftype == "logic_check":
            _batch_exec_logic_check(formula, kernel_ctx, result)
        elif ftype == "reasonability":
            _batch_exec_reasonability(formula, kernel_ctx, result)
        else:
            result.errors.append({
                "formula_id": formula.id,
                "formula_type": ftype,
                "reason": "unknown_formula_type",
            })

    return result


def _batch_exec_auto_calc(
    formula: BatchFormulaDefinition,
    ctx: FormulaContext,
    result: BatchExecutionResult,
) -> None:
    """auto_calc batch：求值 → 产出 MutationIntent（不直接写值、不写 computed time）。"""
    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        result.errors.append({
            "formula_id": formula.id,
            "formula_type": "auto_calc",
            "reason": "evaluation_failed",
            "details": fr.errors or [f"公式求值失败: {formula.expression}"],
        })
        return

    value = fr.value

    # 回填到 row_cache 供后续公式使用本次计算值
    if formula.addr_id:
        ctx.row_cache[formula.addr_id] = value
    if formula.target and formula.target.addr_id:
        ctx.row_cache[formula.target.addr_id] = value

    if formula.target is None:
        result.errors.append({
            "formula_id": formula.id,
            "formula_type": "auto_calc",
            "reason": "no_target",
            "details": ["auto_calc 缺少 target，无法生成 MutationIntent"],
        })
        return

    result.intents.append(MutationIntent(
        target=formula.target,
        computed_value=value,
        formula_id=formula.id,
        formula_type="auto_calc",
    ))


def _batch_exec_logic_check(
    formula: BatchFormulaDefinition,
    ctx: FormulaContext,
    result: BatchExecutionResult,
) -> None:
    """logic_check batch：条件不通过 → issue；无法求值 → issue。不产 mutation。"""
    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        detail = f"（{'; '.join(fr.errors)}）" if fr.errors else ""
        base = formula.issue_description or formula.expression
        result.issues.append({
            "formula_id": formula.id,
            "addr_id": formula.addr_id,
            "description": f"公式无法求值：{base}{detail}",
            "passed": False,
        })
        return

    passed = fr.value != Decimal("0")
    if not passed:
        result.issues.append({
            "formula_id": formula.id,
            "addr_id": formula.addr_id,
            "description": formula.issue_description
            or f"逻辑判断不通过：{formula.expression}",
            "passed": False,
        })


def _batch_exec_reasonability(
    formula: BatchFormulaDefinition,
    ctx: FormulaContext,
    result: BatchExecutionResult,
) -> None:
    """reasonability batch：条件成立 → hint；无法求值 → 跳过不中断。不产 mutation。"""
    fr = kernel_execute(formula.expression, ctx)

    if not fr.ok:
        logger.warning(
            "batch reasonability 无法求值，跳过 (id=%s expr=%s): %s",
            formula.id,
            formula.expression,
            fr.errors,
        )
        return

    triggered = fr.value != Decimal("0")
    if triggered:
        result.hints.append({
            "formula_id": formula.id,
            "addr_id": formula.addr_id,
            "hint_text": formula.hint_text or f"合理性提示：{formula.expression}",
        })
