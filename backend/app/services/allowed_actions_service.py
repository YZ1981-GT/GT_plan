"""可解释状态机服务 — V3 收官增强 Req 10.1

根据实例状态 + 用户角色计算 allowed/denied 操作列表。

依赖：
- backend/app/services/state_machines/*.py（5 类状态机定义）
- backend/app/models/v3_refinement_models.py:AiContentLog, CrossModuleConflict

Validates: Requirements 10.1, AC 10.1~10.3
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import AiContentLog, CrossModuleConflict
from app.services.state_machines.base import StateMachine, Transition
from app.services.state_machines.workpaper_sm import WORKPAPER_SM
from app.services.state_machines.adjustment_sm import ADJUSTMENT_SM
from app.services.state_machines.misstatement_sm import MISSTATEMENT_SM
from app.services.state_machines.report_sm import REPORT_SM
from app.services.state_machines.disclosure_sm import DISCLOSURE_SM

logger = logging.getLogger(__name__)

ModuleType = Literal["workpaper", "adjustment", "misstatement", "report", "disclosure"]

# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------


class ActionDescriptor(TypedDict):
    action: str
    label_zh: str
    allowed: bool
    reason_code: str | None
    reason_zh: str | None


class AllowedActionsResult(TypedDict):
    current_status: str
    current_status_zh: str
    allowed: list[ActionDescriptor]
    denied: list[ActionDescriptor]
    transitions: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# 状态机注册表
# ---------------------------------------------------------------------------

_STATE_MACHINES: dict[str, StateMachine] = {
    "workpaper": WORKPAPER_SM,
    "adjustment": ADJUSTMENT_SM,
    "misstatement": MISSTATEMENT_SM,
    "report": REPORT_SM,
    "disclosure": DISCLOSURE_SM,
}

# ---------------------------------------------------------------------------
# Guard 原因码 → 中文描述
# ---------------------------------------------------------------------------

_REASON_MAP: dict[str, tuple[str, str]] = {
    "ROLE_INSUFFICIENT": ("ROLE_INSUFFICIENT", "当前角色无权执行此操作"),
    "STATE_INVALID": ("STATE_INVALID", "当前状态不允许此操作"),
    "PROJECT_ARCHIVED": ("PROJECT_ARCHIVED", "项目已归档，禁止操作"),
    "AI_PENDING": ("AI_PENDING", "存在未确认的 AI 生成内容"),
    "CONFLICT_UNRESOLVED": ("CONFLICT_UNRESOLVED", "存在未调解的跨模块冲突"),
}


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


async def compute_allowed_actions(
    db: AsyncSession,
    *,
    module: ModuleType,
    instance_id: UUID,
    current_status: str,
    user_role: str,
    project_id: UUID,
    is_archived: bool = False,
) -> AllowedActionsResult:
    """根据状态 + 角色计算允许/禁止的操作列表。

    Parameters
    ----------
    db : AsyncSession
    module : 业务模块类型
    instance_id : 实例 ID
    current_status : 当前状态
    user_role : 用户角色
    project_id : 项目 ID
    is_archived : 项目是否已归档

    Returns
    -------
    AllowedActionsResult
    """
    sm = _STATE_MACHINES.get(module)
    if not sm:
        return AllowedActionsResult(
            current_status=current_status,
            current_status_zh=current_status,
            allowed=[],
            denied=[],
            transitions=[],
        )

    # 预查询 guard 条件
    guard_results = await _evaluate_guards(db, project_id, instance_id, module, is_archived)

    # 获取从当前状态出发的所有转移
    available_transitions = sm.get_transitions_from(current_status)

    descriptors: list[ActionDescriptor] = []
    for t in available_transitions:
        allowed, reason_code, reason_zh = _check_transition(t, user_role, guard_results)
        descriptors.append(ActionDescriptor(
            action=t.action,
            label_zh=sm.action_labels_zh.get(t.action, t.action),
            allowed=allowed,
            reason_code=reason_code,
            reason_zh=reason_zh,
        ))

    return AllowedActionsResult(
        current_status=current_status,
        current_status_zh=sm.status_labels_zh.get(current_status, current_status),
        allowed=[d for d in descriptors if d["allowed"]],
        denied=[d for d in descriptors if not d["allowed"]],
        transitions=sm.to_mermaid_nodes(),
    )


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _check_transition(
    transition: Transition,
    user_role: str,
    guard_results: dict[str, bool],
) -> tuple[bool, str | None, str | None]:
    """检查单条转移是否允许。

    Returns: (allowed, reason_code, reason_zh)
    """
    # 1. 角色检查
    if transition.role_required and user_role not in transition.role_required:
        code, msg = _REASON_MAP["ROLE_INSUFFICIENT"]
        return False, code, msg

    # 2. Guard 检查
    for guard_name in transition.guards:
        if not guard_results.get(guard_name, True):
            # 映射 guard_name → reason
            if guard_name == "no_pending_ai_content":
                code, msg = _REASON_MAP["AI_PENDING"]
            elif guard_name == "no_unresolved_conflict":
                code, msg = _REASON_MAP["CONFLICT_UNRESOLVED"]
            elif guard_name == "not_archived":
                code, msg = _REASON_MAP["PROJECT_ARCHIVED"]
            else:
                code, msg = "GUARD_FAILED", f"守卫条件 {guard_name} 未满足"
            return False, code, msg

    return True, None, None


async def _evaluate_guards(
    db: AsyncSession,
    project_id: UUID,
    instance_id: UUID,
    module: str,
    is_archived: bool,
) -> dict[str, bool]:
    """预查询所有 guard 条件，返回 {guard_name: is_satisfied}。"""
    results: dict[str, bool] = {}

    # not_archived
    results["not_archived"] = not is_archived

    # no_pending_ai_content
    try:
        target_prefix = f"{module}:{instance_id}"
        ai_stmt = (
            select(func.count())
            .select_from(AiContentLog)
            .where(
                AiContentLog.project_id == project_id,
                AiContentLog.target_cell.ilike(f"{target_prefix}%"),
                AiContentLog.confirm_action == "pending",
            )
        )
        ai_result = await db.execute(ai_stmt)
        pending_ai = ai_result.scalar() or 0
        results["no_pending_ai_content"] = pending_ai == 0
    except Exception as exc:
        logger.warning("[ALLOWED_ACTIONS] 查询 AI pending 失败: %s", exc)
        results["no_pending_ai_content"] = True  # 降级放行

    # no_unresolved_conflict
    try:
        conflict_stmt = (
            select(func.count())
            .select_from(CrossModuleConflict)
            .where(
                CrossModuleConflict.project_id == project_id,
                CrossModuleConflict.target_module == module,
                CrossModuleConflict.status == "pending",
            )
        )
        conflict_result = await db.execute(conflict_stmt)
        unresolved = conflict_result.scalar() or 0
        results["no_unresolved_conflict"] = unresolved == 0
    except Exception as exc:
        logger.warning("[ALLOWED_ACTIONS] 查询冲突失败: %s", exc)
        results["no_unresolved_conflict"] = True  # 降级放行

    return results
