"""GuidanceExemptionRecord 服务（Task 6 / G0.5）

职责：
    * 豁免必须独立 scope（project/entry/wp/sheet）
    * approver ≠ owner（capability 复验）
    * expires_at 必填，到期自动失效（不视为 complete）
    * revoke 留痕（revoked_at）

🔴 判据：
    * M-EX-OWNER：删 `_assert_owner_approver_split()` → owner==approver 通过 → 红
    * M-EX-EXPIRE：删 `_assert_expiry_required()` → 无 expires_at 通过 → 红
    * M-EX-SCOPE：删 `_assert_scope_bound()` → 空 scope 通过 → 红

不在本模块：
    * completion 计算 —— 见 `guidance_completion_guard`
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guidance_publication_models import GuidanceExemptionRecord
from app.services.guidance_publication_service import (
    GuidanceForbiddenError,
    GuidancePublicError,
)

__all__ = [
    "ExemptionPublicError",
    "create_exemption",
    "revoke_exemption",
    "is_scope_covered",
    "_assert_owner_approver_split",
    "_assert_expiry_required",
    "_assert_scope_bound",
]

_VALID_SCOPE_TYPES = frozenset({"project", "entry", "wp", "sheet"})
_SCOPE_RANK = {"project": 0, "entry": 1, "wp": 2, "sheet": 3}


class ExemptionPublicError(GuidancePublicError):
    """exemption 域公开错误。"""


async def create_exemption(
    session: AsyncSession,
    *,
    scope_type: str,
    project_id: uuid.UUID | None = None,
    entry_id: str | None = None,
    wp_code: str | None = None,
    sheet_key: str | None = None,
    entry_ids_json: list,
    reason: str,
    owner_user_id: uuid.UUID,
    approver_user_id: uuid.UUID,
    expires_at: datetime,
    source_digest: str | None = None,
) -> GuidanceExemptionRecord:
    """创建豁免记录。scope 三元组、approver≠owner、expires_at 必填。"""
    _assert_scope_bound(
        scope_type=scope_type, project_id=project_id, entry_id=entry_id,
        wp_code=wp_code, sheet_key=sheet_key, entry_ids_json=entry_ids_json,
    )
    _assert_owner_approver_split(owner_user_id, approver_user_id)
    _assert_expiry_required(expires_at)
    if not reason or not str(reason).strip():
        raise ExemptionPublicError("exemption 必须提供非空 reason")

    rec = GuidanceExemptionRecord(
        scope_type=scope_type,
        project_id=project_id,
        entry_id=entry_id,
        wp_code=wp_code,
        sheet_key=sheet_key,
        entry_ids_json=entry_ids_json,
        reason=reason,
        owner_user_id=owner_user_id,
        approver_user_id=approver_user_id,
        expires_at=expires_at,
        source_digest=source_digest,
    )
    session.add(rec)
    await session.flush()
    return rec


async def revoke_exemption(
    session: AsyncSession,
    record: GuidanceExemptionRecord,
    *,
    actor_user_id: uuid.UUID,
    reason: str,
) -> GuidanceExemptionRecord:
    """撤销豁免（保留留痕，revoked_at 非空）。"""
    if record.is_revoked:
        raise ExemptionPublicError(f"exemption {record.id} 已撤销")
    if not reason or not str(reason).strip():
        raise ExemptionPublicError("revoke 必须提供非空 reason")
    record.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return record


def is_scope_covered(
    record: GuidanceExemptionRecord,
    *,
    project_id: uuid.UUID | None,
    entry_id: str | None = None,
    wp_code: str | None = None,
    sheet_key: str | None = None,
) -> bool:
    """判定给定 subject 是否被此 exemption 覆盖（且当前有效）。"""
    if not record.is_valid:
        return False
    if record.scope_type == "project":
        return record.project_id == project_id
    if record.scope_type == "entry":
        return record.project_id == project_id and record.entry_id == entry_id
    if record.scope_type == "wp":
        return (
            record.project_id == project_id
            and record.wp_code == wp_code
        )
    if record.scope_type == "sheet":
        return (
            record.project_id == project_id
            and record.wp_code == wp_code
            and record.sheet_key == sheet_key
        )
    return False


# ---------------------------------------------------------------------------
# 铁律断言
# ---------------------------------------------------------------------------


def _assert_scope_bound(
    *,
    scope_type: str,
    project_id: uuid.UUID | None,
    entry_id: str | None,
    wp_code: str | None,
    sheet_key: str | None,
    entry_ids_json: list,
) -> None:
    """scope 必须明确声明 + 对应字段非空。"""
    if scope_type not in _VALID_SCOPE_TYPES:
        raise ExemptionPublicError(f"scope_type '{scope_type}' 非法；允许 {sorted(_VALID_SCOPE_TYPES)}")
    if project_id is None:
        raise ExemptionPublicError("exemption 必须绑定 project_id")
    if scope_type == "entry" and not entry_id:
        raise ExemptionPublicError("scope_type=entry 要求非空 entry_id")
    if scope_type == "wp" and not wp_code:
        raise ExemptionPublicError("scope_type=wp 要求非空 wp_code")
    if scope_type == "sheet":
        if not wp_code:
            raise ExemptionPublicError("scope_type=sheet 要求非空 wp_code")
        if not sheet_key:
            raise ExemptionPublicError("scope_type=sheet 要求非空 sheet_key")


def _assert_owner_approver_split(owner_user_id: uuid.UUID, approver_user_id: uuid.UUID) -> None:
    """approver ≠ owner —— 服务端复验。"""
    if owner_user_id == approver_user_id:
        raise GuidanceForbiddenError("exemption 的 owner 与 approver 必须分离")


def _assert_expiry_required(expires_at: datetime) -> None:
    """expires_at 必填且必须是未来时间。"""
    if expires_at is None:
        raise ExemptionPublicError("exemption 必须提供 expires_at（永久豁免拒绝）")
    now = datetime.now(expires_at.tzinfo)
    if expires_at <= now:
        raise ExemptionPublicError("exemption 的 expires_at 必须是未来时间")
