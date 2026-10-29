"""S2 ADR-CCN-06: 门禁逐项确认留痕 — service 层

service 只 flush 不 commit，由 router 统一 commit。

提供:
- compute_result_fingerprint(): 确定性指纹计算
- list_acknowledgements(): 列出有效确认
- acknowledge(): 新建确认（自动撤销旧同键确认）
- revoke(): 撤销确认
"""
import hashlib
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gate_acknowledgement_models import GateAcknowledgement
from app.services.audit_log_helper import append_audit_log, AuditLogPayload


# ── 指纹计算 ──────────────────────────────────────────────────


def compute_result_fingerprint(
    check_name: str,
    branch_id: str,
    status: str,
    key_numbers: dict[str, float | None],
) -> str:
    """sha256(check_name|branch_id|status|sorted key=value pairs)

    key_numbers 来自 gate hit 的 location 字典（含 left/right/diff 等），
    数据变了指纹就变。
    """
    parts = [check_name, branch_id, status]
    for k in sorted(key_numbers):
        v = key_numbers[k]
        parts.append(f"{k}={v}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── 列表 ──────────────────────────────────────────────────────


async def list_acknowledgements(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
) -> list[dict]:
    """查询指定项目 + 年度的全部确认记录（含已撤销），按时间倒序。"""
    stmt = (
        sa.select(GateAcknowledgement)
        .where(
            GateAcknowledgement.project_id == project_id,
            GateAcknowledgement.year == year,
        )
        .order_by(sa.desc(GateAcknowledgement.created_at))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "year": r.year,
            "check_name": r.check_name,
            "branch_id": r.branch_id,
            "status": r.status,
            "result_fingerprint": r.result_fingerprint,
            "reason": r.reason,
            "acknowledged_by": str(r.acknowledged_by),
            "acknowledged_role": r.acknowledged_role,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
            "revoked_by": str(r.revoked_by) if r.revoked_by else None,
        }
        for r in rows
    ]


# ── 确认 ──────────────────────────────────────────────────────


async def acknowledge(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    check_name: str,
    branch_id: str,
    status: str,
    result_fingerprint: str,
    reason: str,
    user_id: uuid.UUID,
    user_role: str,
) -> dict:
    """新建确认。自动撤销同 (project_id, year, check_name) 的旧有效确认。

    校验:
    - reason 去空白后 ≥ 10 字符

    Raises:
        ValueError: 原因不足 10 字
    """
    if len(reason.strip()) < 10:
        raise ValueError("确认原因至少需要 10 个字符")

    now = datetime.now(timezone.utc)

    # 撤销旧的同键确认
    old_stmt = (
        sa.select(GateAcknowledgement)
        .where(
            GateAcknowledgement.project_id == project_id,
            GateAcknowledgement.year == year,
            GateAcknowledgement.check_name == check_name,
            GateAcknowledgement.revoked_at.is_(None),
        )
    )
    old_result = await db.execute(old_stmt)
    for old_ack in old_result.scalars().all():
        old_ack.revoked_at = now
        old_ack.revoked_by = user_id

    # 新建确认
    ack = GateAcknowledgement(
        project_id=project_id,
        year=year,
        check_name=check_name,
        branch_id=branch_id,
        status=status,
        result_fingerprint=result_fingerprint,
        reason=reason,
        acknowledged_by=user_id,
        acknowledged_role=user_role,
        created_at=now,
    )
    db.add(ack)
    await db.flush()

    # 审计日志
    await append_audit_log(db, AuditLogPayload(
        user_id=user_id,
        project_id=project_id,
        action="gate_acknowledgement_create",
        resource_type="gate_acknowledgement",
        resource_id=str(ack.id),
        details={
            "event_type": "gate_acknowledgement",
            "check_name": check_name,
            "branch_id": branch_id,
            "status": status,
            "result_fingerprint": result_fingerprint,
            "reason": reason,
            "acknowledged_role": user_role,
        },
    ))

    return {
        "id": str(ack.id),
        "project_id": str(ack.project_id),
        "year": ack.year,
        "check_name": ack.check_name,
        "branch_id": ack.branch_id,
        "status": ack.status,
        "result_fingerprint": ack.result_fingerprint,
        "reason": ack.reason,
        "acknowledged_by": str(ack.acknowledged_by),
        "acknowledged_role": ack.acknowledged_role,
        "created_at": ack.created_at.isoformat() if ack.created_at else None,
    }


# ── 撤销 ──────────────────────────────────────────────────────


async def revoke(
    db: AsyncSession,
    ack_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """撤销指定确认。"""
    stmt = sa.select(GateAcknowledgement).where(GateAcknowledgement.id == ack_id)
    result = await db.execute(stmt)
    ack = result.scalar_one_or_none()
    if not ack:
        raise ValueError(f"确认记录不存在: {ack_id}")

    now = datetime.now(timezone.utc)
    ack.revoked_at = now
    ack.revoked_by = user_id
    await db.flush()

    # 审计日志
    await append_audit_log(db, AuditLogPayload(
        user_id=user_id,
        project_id=ack.project_id,
        action="gate_acknowledgement_revoke",
        resource_type="gate_acknowledgement",
        resource_id=str(ack.id),
        details={
            "event_type": "gate_acknowledgement",
            "check_name": ack.check_name,
            "revoked_at": now.isoformat(),
        },
    ))

    return {
        "id": str(ack.id),
        "revoked_at": now.isoformat(),
        "revoked_by": str(user_id),
    }
