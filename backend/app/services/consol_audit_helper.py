"""合并操作审计留痕 helper — Phase 0 P1（CAS 1131 合规红线）

为合并关键写操作（lock/unlock/抵销审批/recalc/scope 变更）统一留痕，
复用 V007 哈希链 append_audit_log。

action 值域：
- consol.lock / consol.unlock / consol.elimination.approve / consol.recalc / consol.scope.change

resource_type 值域：
- project / elimination_entry / consol_trial / consol_scope

留痕与主操作同事务：留痕失败回滚主操作（合规优先，关联 E9）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_log_helper import append_audit_log


async def log_consol_action(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before: dict | None,
    after: dict | None,
) -> UUID:
    """写合并操作审计日志（操作人+时间+前后值），进哈希链。

    参数:
        db: 异步数据库会话（必须与主操作同一事务）
        user_id: 操作人 ID
        project_id: 合并母项目 ID
        action: 操作类型（consol.lock / consol.unlock / consol.elimination.approve / consol.recalc / consol.scope.change）
        resource_type: 资源类型（project / elimination_entry / consol_trial / consol_scope）
        resource_id: 资源 ID（可选）
        before: 操作前状态快照
        after: 操作后状态快照

    返回:
        新创建的审计日志条目 UUID

    异常:
        留痕失败不静默吞——异常向上传播，由调用方事务回滚（合规优先）。
    """
    details: dict[str, Any] = {
        "event_type": "consol_lifecycle",
        "sub_action": action,
        "before": before,
        "after": after,
    }

    entry_id = await append_audit_log(db, {
        "user_id": user_id,
        "project_id": project_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
    })

    return entry_id
