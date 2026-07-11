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

Requirements: 5.1, 5.2, 5.4, 5.5, 6.1, 6.2, 6.6, 7.1, 7.2, 7.5,
              11.1, 11.2, 11.3, 11.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

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
