"""审计日志路由 — 哈希链校验端点

Refinement Round 1 — 需求 9：GET /api/audit-logs/verify-chain

ADR-ALC-05: 委托 audit_chain.verify 按链接关系校验。
鉴权逻辑不变（R1 Bug Fix 2）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs")

# 允许访问审计哈希链的项目角色（除 admin 外）
_ALLOWED_PROJECT_ROLES: frozenset[str] = frozenset(
    {"partner", "signing_partner", "qc", "eqcr", "manager"}
)


@router.get("/verify-chain")
async def verify_chain_endpoint(
    project_id: Optional[str] = Query(None, description="项目 ID，按 project_id 过滤链"),
    from_time: Optional[str] = Query(None, alias="from", description="起始时间 ISO 格式"),
    to_time: Optional[str] = Query(None, alias="to", description="结束时间 ISO 格式"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验审计日志哈希链完整性。

    权限（R1 Bug Fix 2）：
    - admin：直接放行（可查任意项目或全局链）
    - 其他角色：必须传 project_id 且在该项目具备审阅/签字能力
      （partner/signing_partner/qc/eqcr/manager），否则 403 FORBIDDEN_AUDIT_CHAIN。
    - 未登录：401（由 get_current_user 依赖返回）
    """
    # --- 权限校验（不变） ---
    user_role = current_user.role.value if current_user.role else ""
    if user_role != "admin":
        if not project_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FORBIDDEN_AUDIT_CHAIN",
                    "message": "非管理员查询审计哈希链必须指定 project_id",
                },
            )

        try:
            pid_uuid = UUID(project_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail={"error_code": "INVALID_PROJECT_ID", "message": "project_id 不是合法 UUID"},
            )

        from app.services.role_context_service import RoleContextService

        ctx = await RoleContextService(db).get_project_role(current_user.id, pid_uuid)
        effective_role = (ctx or {}).get("role") or ""
        if effective_role not in _ALLOWED_PROJECT_ROLES:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FORBIDDEN_AUDIT_CHAIN",
                    "message": "当前用户无权查询该项目的审计哈希链",
                    "required_roles": sorted(_ALLOWED_PROJECT_ROLES),
                },
            )

    # --- 委托 verify.py ---
    from app.services.audit_chain.verify import verify_chain

    vr = await verify_chain(db, project_id=project_id, from_time=from_time, to_time=to_time)

    # 构建响应：保留旧字段 + 新字段
    resp: dict = {
        "valid": vr.valid,
        "entries_checked": vr.entries_checked,
        "broken_at_entry_id": vr.broken_at_entry_id,
        "message": vr.message,
        "problems": vr.problems,
        "legacy_verified": vr.legacy_verified,
        "legacy_unverifiable": vr.legacy_unverifiable,
        "anchor": vr.anchor,
    }

    # broken_at_index 兼容：无法精确还原旧序号，用 None 表示
    if vr.broken_at_entry_id:
        resp["broken_at_index"] = None
    return resp
