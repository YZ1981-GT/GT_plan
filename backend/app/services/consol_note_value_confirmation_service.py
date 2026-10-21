"""合并附注值确认服务——确认/查询/签发闸门。

spec: consol-note-mapping-reuse-and-reference-push Phase 5 Task 17~19

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_template_models import (
    ConsolNoteValueConfirmation,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 确认
# ═══════════════════════════════════════════════════════════════════════════════


async def confirm_entity_value(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    entity_node_key: str = "_self",
    confirmed_by: UUID,
    value_hash: str,
) -> dict[str, Any]:
    """确认某企业某章节的当前值。UPSERT 确认记录。

    Args:
        entity_node_key: 子企业的 node_key，'_self' 表示本项目自身。
        value_hash: 当前值指纹（由调用方计算传入）。
    """
    if len(value_hash) != 64:
        raise ValueError("value_hash 必须是 64 位十六进制字符串")

    now = datetime.now(timezone.utc)

    existing = (await db.execute(
        sa.select(ConsolNoteValueConfirmation).where(
            ConsolNoteValueConfirmation.project_id == project_id,
            ConsolNoteValueConfirmation.section_id == section_id,
            ConsolNoteValueConfirmation.entity_node_key == entity_node_key,
        )
    )).scalar_one_or_none()

    if existing is not None:
        existing.confirmed_value_hash = value_hash
        existing.confirmed_by = confirmed_by
        existing.confirmed_at = now
        existing.status = "confirmed"
    else:
        existing = ConsolNoteValueConfirmation(
            project_id=project_id,
            section_id=section_id,
            entity_node_key=entity_node_key,
            confirmed_value_hash=value_hash,
            confirmed_by=confirmed_by,
            confirmed_at=now,
            status="confirmed",
        )
        db.add(existing)

    await db.flush()
    return {
        "action": "confirmed",
        "project_id": str(project_id),
        "section_id": section_id,
        "entity_node_key": entity_node_key,
        "confirmed_value_hash": value_hash,
        "confirmed_at": now.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 查询确认状态
# ═══════════════════════════════════════════════════════════════════════════════


async def get_confirmation_status(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str | None = None,
) -> list[dict[str, Any]]:
    """查询确认状态汇总。返回每个 section × entity 的状态。"""
    q = sa.select(ConsolNoteValueConfirmation).where(
        ConsolNoteValueConfirmation.project_id == project_id,
    )
    if section_id:
        q = q.where(ConsolNoteValueConfirmation.section_id == section_id)
    q = q.order_by(
        ConsolNoteValueConfirmation.section_id,
        ConsolNoteValueConfirmation.entity_node_key,
    )

    result = await db.execute(q)
    return [
        {
            "id": str(c.id),
            "section_id": c.section_id,
            "entity_node_key": c.entity_node_key,
            "confirmed_value_hash": c.confirmed_value_hash,
            "confirmed_by": str(c.confirmed_by) if c.confirmed_by else None,
            "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None,
            "status": c.status,
        }
        for c in result.scalars().all()
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 签发前闸门
# ═══════════════════════════════════════════════════════════════════════════════


async def check_all_confirmed(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
) -> dict[str, Any]:
    """签发前闸门检查。

    检查所有映射章节的所有子企业数据是否都已确认且未过期。
    fail-closed：有任何未确认或过期→blocking。

    Returns:
        {passed: bool, blocking_items: [...], confirmed_count, total_count}
    """
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding

    # 查所有映射绑定（confirmed 或 stale 的）
    bindings = (await db.execute(
        sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.project_id == consol_project_id,
            ConsolNoteMappingBinding.status.in_(["confirmed", "stale"]),
        )
    )).scalars().all()

    if not bindings:
        return {
            "passed": True,
            "blocking_items": [],
            "confirmed_count": 0,
            "total_count": 0,
            "message": "无映射绑定，无需确认",
        }

    # 查所有确认记录
    confirmations = (await db.execute(
        sa.select(ConsolNoteValueConfirmation).where(
            ConsolNoteValueConfirmation.project_id == consol_project_id,
        )
    )).scalars().all()

    confirm_index: dict[tuple[str, str], ConsolNoteValueConfirmation] = {}
    for c in confirmations:
        confirm_index[(c.section_id, c.entity_node_key)] = c

    blocking_items: list[dict[str, Any]] = []
    confirmed_count = 0
    total_count = len(bindings)

    for b in bindings:
        key = (b.section_id, b.entity_node_key)
        c = confirm_index.get(key)
        if c is None:
            blocking_items.append({
                "section_id": b.section_id,
                "entity_node_key": b.entity_node_key,
                "reason": "未确认",
            })
        elif c.status == "outdated":
            blocking_items.append({
                "section_id": b.section_id,
                "entity_node_key": b.entity_node_key,
                "reason": "已过期（子企业数据已变更）",
            })
        else:
            confirmed_count += 1

    return {
        "passed": len(blocking_items) == 0,
        "blocking_items": blocking_items,
        "confirmed_count": confirmed_count,
        "total_count": total_count,
        "message": "全部确认" if not blocking_items else f"{len(blocking_items)} 项未确认或已过期",
    }
