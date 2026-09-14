"""Evidence Governance 路由共享小工具（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R7, R8, R10, R11, R13
Design: §6.1 通用约定, §7.2 稳定失败类别

本模块只提供 **无业务逻辑** 的横切小工具，供 AI/Citation/Review/Archive/LegalHold
五个 thin router 复用，避免各文件重复实现 UUID 解析、用户角色解析、时间格式化：

- ``parse_uuid``：路径/参数 UUID 解析，非法即抛脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``
  （边界先于业务；与 ocr_governance_router._parse_uuid 同一语义）。
- ``get_user_role``：系统角色优先 admin/partner，其余查 ``project_users`` 项目角色，
  与 evidence_ref_router / ocr_governance_router 的 ``_get_user_role`` 完全一致。
- ``isoformat_or_none``：可空时间安全 isoformat。

不复制任何治理业务规则；scope/capability/幂等/事务仍由 ProjectYearScopeGuard、
CapabilityGuard 与 EvidenceGovernanceFacade 负责。
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


def parse_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    """解析 UUID；非法则抛脱敏错误（边界先于业务，design §7.2）。"""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            f"invalid {field_name}",
        )


async def get_user_role(db: AsyncSession, user: Any, project_id: uuid.UUID) -> str:
    """获取用户在项目中的角色（与 evidence_ref/ocr 治理 router 同一实现）。

    系统 admin/partner 直接返回；否则查 ``project_users`` 项目分配角色；再回退系统角色。
    """
    if hasattr(user, "role"):
        role = user.role
        role_val = role.value if hasattr(role, "value") else role
        if role_val in ("admin", "partner"):
            return role_val

    row = (
        await db.execute(
            sa.text(
                "SELECT role FROM project_users "
                "WHERE project_id = :pid AND user_id = :uid "
                "AND is_deleted = false LIMIT 1"
            ),
            {"pid": str(project_id), "uid": str(user.id)},
        )
    ).mappings().first()
    if row:
        return row["role"]

    if hasattr(user, "role"):
        role = user.role
        return role.value if hasattr(role, "value") else role
    return "readonly"


def isoformat_or_none(dt: Any) -> str | None:
    """可空时间安全 isoformat。"""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)
