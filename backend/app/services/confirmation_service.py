"""函证管理服务

能力域 D — global-refinement-v5-closure：
CRUD + 状态机 transition_status。
service 只 flush 不 commit（项目铁律，router 统一 commit）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import re

from sqlalchemy import select, delete as sa_delete, text as sa_text
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


# ─── 回函结果应用 + 下游 stale 传播事件（P0 恢复）────────────────────────────
#
# 历史上 workpaper-d-sales-cycle 任务 2.11 / workpaper-f-purchase-inventory 任务 2.20
# 要求"函证回函 → emit EventType.CONFIRMATION_RECEIVED → 沿 cross_wp_references
# 中 source_wp={D0,F0,G0} 的条目向下游（D2/F2/G7…）传播 stale"。该函数一度缺失
# （3 个回调测试 ImportError 红）。此处按测试契约重建并通用化。


async def apply_confirmation_result(
    *,
    project_id: uuid.UUID,
    year: int,
    confirmation_id: uuid.UUID,
    reply_status: str = "",
    reply_amount: float | None = None,
    wp_code: str = "D0",
    db: AsyncSession | None = None,
) -> dict:
    """应用函证回函结果并发布 CONFIRMATION_RECEIVED 事件（下游 stale 传播入口）。

    通用化支持各循环函证底稿：默认 ``wp_code="D0"`` 向下兼容销售循环，亦支持
    ``F0``（采购/存货）、``G0``（投资）等——``extra.wp_code`` 供 stale_engine
    按 ``cross_wp_references`` 的 ``source_wp`` 路由把下游底稿（D2/F2/G7…）标 stale。

    - ``db`` 为 None 时只发事件（供纯事件场景/测试）；提供时尽力回写函证记录
      （confirmed_amount / diff / 终态 status），失败不阻断事件发布。
    - 事件经 ``event_bus.publish_immediate`` 立即派发（不 debounce）。

    Returns: ``{applied, wp_code, confirmation_id, reply_status, reply_amount}``。
    """
    from app.services.event_bus import event_bus
    from app.models.audit_platform_schemas import EventPayload, EventType

    # 1) 尽力回写函证记录（仅当传入 db 且记录存在）
    if db is not None:
        try:
            stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
            record = (await db.execute(stmt)).scalar_one_or_none()
            if record is not None:
                if reply_amount is not None:
                    record.confirmed_amount = reply_amount
                    if record.book_amount is not None:
                        record.diff_amount = float(record.book_amount) - float(reply_amount)
                status = (reply_status or "").lower()
                if "disc" in status or "diff" in status or "不符" in reply_status:
                    record.status = "discrepancy"
                elif "match" in status or "相符" in reply_status:
                    record.status = "matched"
                elif status in ("returned", "已回函"):
                    record.status = "returned"
                record.updated_at = datetime.now(timezone.utc)
                await db.flush()
        except Exception:  # noqa: BLE001 — 回写失败不阻断事件发布
            pass

    # 2) 发布 CONFIRMATION_RECEIVED（下游 stale 传播真源）
    payload = EventPayload(
        event_type=EventType.CONFIRMATION_RECEIVED,
        project_id=project_id,
        year=year,
        extra={
            "wp_code": wp_code,
            "confirmation_id": str(confirmation_id),
            "reply_status": reply_status,
            "reply_amount": reply_amount,
        },
    )
    await event_bus.publish_immediate(payload)

    return {
        "applied": True,
        "wp_code": wp_code,
        "confirmation_id": str(confirmation_id),
        "reply_status": reply_status,
        "reply_amount": reply_amount,
    }


# ─── 源底稿循环码 / 年度反查（G1：Hub 手动回函 stale 兜底）────────────────────
#
# 函证中心台账（ConfirmationHub）手动推进 transition 时通常不带 wp_code——
# 若函证记录关联了 wp_id（源函证底稿，如 D0/F0/G0…），可经 working_paper→wp_index
# 反查出 wp_code，并从 projects.audit_year 取年度，作为 CONFIRMATION_RECEIVED
# 下游 stale 传播的兜底路由源。无 wp_id 时返回 (None, None)，调用方据此不臆测源底稿。


def _normalize_source_wp_code(wp_code: str | None) -> str | None:
    """把 sheet 级函证底稿编码归一为循环级源码（D0-1 → D0）。

    stale 传播图以循环级 wp_code（D0/F0/G0…）为键，故剥离尾部 ``-N`` sheet 后缀，
    与前端 ``syncHubFromSummary`` 的 ``wpCode.split('-')[0]`` 口径一致。
    """
    if not wp_code:
        return None
    return re.sub(r"-\d+$", "", wp_code.strip()) or None


async def derive_source_wp_code_and_year(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> tuple[str | None, int | None]:
    """从函证记录的 wp_id 反查 (源循环 wp_code, 审计年度)。

    - 记录不存在 / 无 wp_id → ``(None, None)``（调用方不触发 stale）。
    - 反查失败不抛异常（尽力而为），返回已取到的部分。
    """
    stmt = select(Confirmation.wp_id, Confirmation.project_id).where(
        Confirmation.id == confirmation_id
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None, None
    wp_id, project_id = row[0], row[1]

    # 无关联底稿 → 不臆测源循环码；year 仅在有 wp_code（会传播 stale）时才需要，
    # 故此处直接短路，避免多余的 projects 查询。
    if wp_id is None:
        return None, None

    wc_row = (
        await db.execute(
            sa_text(
                "SELECT wi.wp_code "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "WHERE wp.id = :wp_id AND wp.is_deleted = false "
                "LIMIT 1"
            ),
            {"wp_id": str(wp_id)},
        )
    ).first()
    wp_code = _normalize_source_wp_code(wc_row[0]) if wc_row is not None else None
    if not wp_code:
        return None, None

    year: int | None = None
    if project_id is not None:
        yr_row = (
            await db.execute(
                sa_text("SELECT audit_year FROM projects WHERE id = :pid LIMIT 1"),
                {"pid": str(project_id)},
            )
        ).first()
        if yr_row is not None and yr_row[0] is not None:
            year = int(yr_row[0])

    return wp_code, year
