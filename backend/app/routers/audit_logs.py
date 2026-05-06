"""审计日志路由 — 哈希链校验端点

Refinement Round 1 — 需求 9：GET /api/audit-logs/verify-chain

逐条重算 entry_hash 比对，第一条断链停下返回。

R1 Bug Fix 2: 增加权限校验。admin 直接放行；其他角色必须传 project_id
且在该项目具备 review/sign_off 能力（signing_partner/qc/eqcr/manager/partner）。
未登录返回 401；普通 auditor/readonly 或项目外用户返回 403
FORBIDDEN_AUDIT_CHAIN。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs")

# 创世哈希
GENESIS_HASH = "0" * 64

# 允许访问审计哈希链的项目角色（除 admin 外）
_ALLOWED_PROJECT_ROLES: frozenset[str] = frozenset(
    {"partner", "signing_partner", "qc", "eqcr", "manager"}
)


def _compute_entry_hash(
    ts: str,
    user_id: str,
    action_type: str,
    object_id: str | None,
    payload_json: str,
    prev_hash: str,
) -> str:
    """重算 entry_hash。"""
    raw = f"{ts}|{user_id or ''}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/verify-chain")
async def verify_chain(
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

    校验逻辑：
    - 逐条重算 entry_hash 比对，第一条断链停下返回
    - 全部通过返回 {valid: true, entries_checked: N}
    """
    from app.models.audit_log_models import AuditLogEntry
    from app.core.config import settings

    # --- 权限校验 ---
    user_role = current_user.role.value if current_user.role else ""
    if user_role != "admin":
        # 非 admin 必须传 project_id
        if not project_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FORBIDDEN_AUDIT_CHAIN",
                    "message": "非管理员查询审计哈希链必须指定 project_id",
                },
            )

        # 项目内角色检查
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

    # 构建查询
    stmt = select(AuditLogEntry).order_by(asc(AuditLogEntry.ts), asc(AuditLogEntry.id))

    # 按 project_id 过滤（通过 payload->>'project_id'）
    if project_id:
        if settings.DATABASE_URL.startswith("postgresql"):
            stmt = stmt.where(AuditLogEntry.payload["project_id"].astext == project_id)
        else:
            from sqlalchemy import literal_column
            stmt = stmt.where(
                literal_column("json_extract(payload, '$.project_id')") == project_id
            )

    # 时间范围过滤
    if from_time:
        try:
            from_dt = datetime.fromisoformat(from_time)
            stmt = stmt.where(AuditLogEntry.ts >= from_dt)
        except ValueError:
            pass

    if to_time:
        try:
            to_dt = datetime.fromisoformat(to_time)
            stmt = stmt.where(AuditLogEntry.ts <= to_dt)
        except ValueError:
            pass

    result = await db.execute(stmt)
    entries = result.scalars().all()

    if not entries:
        return {"valid": True, "entries_checked": 0}

    # 逐条校验哈希链
    expected_prev_hash = GENESIS_HASH
    entries_checked = 0

    for entry in entries:
        entries_checked += 1

        # 验证 prev_hash 是否与预期一致
        if entry.prev_hash != expected_prev_hash:
            # 第一条的 prev_hash 可能是 GENESIS 或上一条的 hash
            # 如果是链的第一条且 prev_hash 是 GENESIS，跳过此检查
            if entries_checked == 1:
                expected_prev_hash = entry.prev_hash
            else:
                return {
                    "valid": False,
                    "broken_at_entry_id": str(entry.id),
                    "broken_at_index": entries_checked,
                    "expected_prev_hash": expected_prev_hash,
                    "actual_prev_hash": entry.prev_hash,
                    "message": f"哈希链在第 {entries_checked} 条断裂：prev_hash 不匹配",
                }

        # 重算 entry_hash
        payload_json = json.dumps(
            entry.payload or {}, sort_keys=True, ensure_ascii=False, default=str
        )
        object_id_str = str(entry.object_id) if entry.object_id else ""
        user_id_str = str(entry.user_id) if entry.user_id else ""

        computed_hash = _compute_entry_hash(
            entry.ts.isoformat() if entry.ts else "",
            user_id_str,
            entry.action_type or "",
            object_id_str,
            payload_json,
            entry.prev_hash,
        )

        if computed_hash != entry.entry_hash:
            return {
                "valid": False,
                "broken_at_entry_id": str(entry.id),
                "broken_at_index": entries_checked,
                "expected_hash": computed_hash,
                "actual_hash": entry.entry_hash,
                "message": f"哈希链在第 {entries_checked} 条断裂：entry_hash 被篡改",
            }

        # 下一条的 expected_prev_hash 应该是当前条的 entry_hash
        expected_prev_hash = entry.entry_hash

    return {"valid": True, "entries_checked": entries_checked}
