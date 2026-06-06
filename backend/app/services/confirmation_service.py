"""函证管理服务

能力域 D — global-refinement-v5-closure：
CRUD + 状态机 transition_status。
service 只 flush 不 commit（项目铁律，router 统一 commit）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.confirmation_models import Confirmation


# ─── 状态机合法转换表 ───────────────────────────────────────────────────────
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"sent"},
    "sent": {"returned"},
    "returned": {"matched", "discrepancy"},
    "matched": set(),
    "discrepancy": set(),
}

# 中文状态名映射（用于错误提示）
_STATUS_CN: dict[str, str] = {
    "pending": "待发函",
    "sent": "已发函",
    "returned": "已回函",
    "matched": "相符",
    "discrepancy": "差异",
}


def _to_dict(record: Confirmation) -> dict:
    """将 ORM 实例转为 dict 输出"""
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "confirm_type": record.confirm_type,
        "counterparty": record.counterparty,
        "status": record.status,
        "wp_id": str(record.wp_id) if record.wp_id else None,
        "account_code": record.account_code,
        "book_amount": float(record.book_amount) if record.book_amount is not None else None,
        "confirmed_amount": float(record.confirmed_amount) if record.confirmed_amount is not None else None,
        "diff_amount": float(record.diff_amount) if record.diff_amount is not None else None,
        "diff_note": record.diff_note,
        "created_by": str(record.created_by) if record.created_by else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


async def create_confirmation(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: dict,
) -> dict:
    """创建函证记录

    必填: confirm_type, counterparty
    可选: wp_id, account_code, book_amount, confirmed_amount, diff_amount, diff_note, created_by
    """
    now = datetime.now(timezone.utc)
    record = Confirmation(
        id=uuid.uuid4(),
        project_id=project_id,
        confirm_type=data.get("confirm_type") or "",
        counterparty=data.get("counterparty") or "",
        status="pending",
        wp_id=(data.get("wp_id") or None),
        account_code=(data.get("account_code") or None),
        book_amount=(data.get("book_amount") if data.get("book_amount") is not None else None),
        confirmed_amount=(data.get("confirmed_amount") if data.get("confirmed_amount") is not None else None),
        diff_amount=(data.get("diff_amount") if data.get("diff_amount") is not None else None),
        diff_note=(data.get("diff_note") or None),
        created_by=(data.get("created_by") or None),
    )
    db.add(record)
    await db.flush()
    # refresh to get server defaults (created_at, updated_at)
    await db.refresh(record)
    return _to_dict(record)


async def list_confirmations(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> list[dict]:
    """列出项目下所有函证"""
    stmt = (
        select(Confirmation)
        .where(Confirmation.project_id == project_id)
        .order_by(Confirmation.created_at.desc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [_to_dict(r) for r in records]


async def get_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> dict:
    """获取单条函证详情（含关联+差异）

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")
    return _to_dict(record)


async def update_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
    data: dict,
) -> dict:
    """更新函证记录

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    # 可更新字段
    updatable_fields = [
        "confirm_type", "counterparty", "wp_id", "account_code",
        "book_amount", "confirmed_amount", "diff_amount", "diff_note",
    ]
    for field in updatable_fields:
        if field in data:
            value = data[field]
            # 对可选字段用 (value or None) 兜底
            if field in ("wp_id", "account_code", "diff_note"):
                value = (value or None)
            setattr(record, field, value)

    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(record)
    return _to_dict(record)


async def delete_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> dict:
    """删除函证记录

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    await db.delete(record)
    await db.flush()
    return {"deleted": True, "id": str(confirmation_id)}


async def transition_status(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
    target_status: str,
) -> dict:
    """函证状态机推进

    仅允许合法转换（_ALLOWED_TRANSITIONS），非法转换抛中文 ValueError。

    Raises:
        ValueError: 函证记录不存在 / 非法状态转换
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    current = record.status
    allowed = _ALLOWED_TRANSITIONS.get(current, set())

    if target_status not in allowed:
        current_cn = _STATUS_CN.get(current, current)
        target_cn = _STATUS_CN.get(target_status, target_status)
        raise ValueError(f"不能从『{current_cn}』直接转为『{target_cn}』")

    record.status = target_status
    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(record)
    return _to_dict(record)
