"""Overlay Repository — CRUD for acnr_project_overlay (PG-backed).

Provides persistence layer for L2 ProjectOverlay data.
Memory cache (`overlay.py`) delegates write/read to this repository.

Requirements: Req-4 (Overlay 持久化与归属校验)
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acnr_overlay_model import AcnrProjectOverlay

logger = logging.getLogger(__name__)


class OverlayRevisionConflict(Exception):
    """Overlay CAS 乐观并发冲突：expected_revision 与当前 revision 不匹配（R8.2）。"""

    def __init__(self, project_id: str, addr_id: str, expected_revision: int) -> None:
        self.project_id = project_id
        self.addr_id = addr_id
        self.expected_revision = expected_revision
        super().__init__(
            f"Overlay revision conflict: project={project_id} addr_id={addr_id} "
            f"expected_revision={expected_revision} (current revision differs or row missing)"
        )


def _coerce_expires_at(value: Any) -> date | None:
    """expires_at 允许 date / ISO 字符串 / None → 归一为 date | None。"""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


# ─── CRUD ────────────────────────────────────────────────────────────────────


async def create_overlay(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID | None,
    parent_wp_code: str,
    sheet_code: str,
    overlay_type: str,
    payload: dict[str, Any],
) -> AcnrProjectOverlay:
    """Insert a new overlay row into PG."""
    row = AcnrProjectOverlay(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_id=wp_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        overlay_type=overlay_type,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "overlay_repo.create: project=%s wp_code=%s/%s type=%s",
        project_id, parent_wp_code, sheet_code, overlay_type,
    )
    return row


async def upsert_overlay(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID | None,
    parent_wp_code: str,
    sheet_code: str,
    overlay_type: str,
    payload: dict[str, Any],
    reason: str | None = None,
    owner: str | None = None,
    expires_at: Any = None,
    expected_revision: int | None = None,
) -> AcnrProjectOverlay:
    """原子 upsert（R6）+ 可选 CAS（R8）+ 治理字段（R7）。

    - expected_revision is None → `INSERT ... ON CONFLICT (uq_overlay_identity) DO UPDATE`
      单语句原子（并发不产生重复行）；命中冲突 revision+1。
    - expected_revision 提供 → CAS：仅当当前 revision == expected 才 UPDATE；rowcount==0
      抛 OverlayRevisionConflict（不覆盖对方修改，DB 不变）。
    """
    exp = _coerce_expires_at(expires_at)

    # ─── CAS 分支（R8）：条件更新，rowcount==0 → 冲突 ────────────────────
    if expected_revision is not None:
        upd = (
            sa.update(AcnrProjectOverlay)
            .where(
                AcnrProjectOverlay.project_id == project_id,
                AcnrProjectOverlay.parent_wp_code == parent_wp_code,
                AcnrProjectOverlay.sheet_code == sheet_code,
                AcnrProjectOverlay.overlay_type == overlay_type,
                AcnrProjectOverlay.revision == expected_revision,
            )
            .values(
                payload={**payload},
                wp_id=wp_id,
                reason=reason,
                owner=owner,
                expires_at=exp,
                revision=AcnrProjectOverlay.revision + 1,
                updated_at=sa.func.now(),
            )
        )
        res = await session.execute(upd)
        if res.rowcount == 0:
            raise OverlayRevisionConflict(
                str(project_id), f"{parent_wp_code}/{sheet_code}", expected_revision
            )
        await session.flush()
        row = await _get_by_identity(
            session, project_id, parent_wp_code, sheet_code, overlay_type
        )
        # Core UPDATE 绕过 ORM unit-of-work → 刷新身份映射避免返回陈旧 revision
        if row is not None:
            await session.refresh(row)
        logger.info(
            "overlay_repo.upsert(CAS): project=%s %s/%s type=%s exp_rev=%d",
            project_id, parent_wp_code, sheet_code, overlay_type, expected_revision,
        )
        return row  # type: ignore[return-value]

    # ─── 非 CAS 分支（R6）：ON CONFLICT 原子 upsert ─────────────────────
    ins = pg_insert(AcnrProjectOverlay).values(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_id=wp_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        overlay_type=overlay_type,
        payload={**payload},
        reason=reason,
        owner=owner,
        expires_at=exp,
        revision=1,
    )
    stmt = ins.on_conflict_do_update(
        constraint="uq_overlay_identity",
        set_={
            "payload": ins.excluded.payload,
            "wp_id": ins.excluded.wp_id,
            "reason": ins.excluded.reason,
            "owner": ins.excluded.owner,
            "expires_at": ins.excluded.expires_at,
            "revision": AcnrProjectOverlay.revision + 1,
            "updated_at": sa.func.now(),
        },
    ).returning(AcnrProjectOverlay.id)
    res = await session.execute(stmt)
    oid = res.scalar_one()
    await session.flush()
    row = await get_overlay_by_id(session, oid)
    # ON CONFLICT DO UPDATE 经 Core → 刷新避免身份映射中的陈旧 revision（冲突更新场景）
    if row is not None:
        await session.refresh(row)
    logger.info(
        "overlay_repo.upsert(atomic): project=%s %s/%s type=%s",
        project_id, parent_wp_code, sheet_code, overlay_type,
    )
    return row  # type: ignore[return-value]


async def _get_by_identity(
    session: AsyncSession,
    project_id: uuid.UUID,
    parent_wp_code: str,
    sheet_code: str,
    overlay_type: str,
) -> AcnrProjectOverlay | None:
    """按 Overlay_Unique_Key 取行。"""
    stmt = sa.select(AcnrProjectOverlay).where(
        AcnrProjectOverlay.project_id == project_id,
        AcnrProjectOverlay.parent_wp_code == parent_wp_code,
        AcnrProjectOverlay.sheet_code == sheet_code,
        AcnrProjectOverlay.overlay_type == overlay_type,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_overlays_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> list[AcnrProjectOverlay]:
    """Load all overlay rows for a project (read-through cache source)."""
    stmt = (
        sa.select(AcnrProjectOverlay)
        .where(AcnrProjectOverlay.project_id == project_id)
        .order_by(AcnrProjectOverlay.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_overlay_by_id(
    session: AsyncSession,
    overlay_id: uuid.UUID,
) -> AcnrProjectOverlay | None:
    """Get single overlay by PK."""
    stmt = sa.select(AcnrProjectOverlay).where(AcnrProjectOverlay.id == overlay_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_overlay(
    session: AsyncSession,
    overlay_id: uuid.UUID,
) -> bool:
    """Delete single overlay by PK. Returns True if deleted."""
    stmt = (
        sa.delete(AcnrProjectOverlay)
        .where(AcnrProjectOverlay.id == overlay_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0


async def delete_overlay_by_identity(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    parent_wp_code: str,
    sheet_code: str,
    overlay_type: str,
) -> bool:
    """按 Overlay_Unique_Key 删除单行。Returns True if deleted."""
    stmt = sa.delete(AcnrProjectOverlay).where(
        AcnrProjectOverlay.project_id == project_id,
        AcnrProjectOverlay.parent_wp_code == parent_wp_code,
        AcnrProjectOverlay.sheet_code == sheet_code,
        AcnrProjectOverlay.overlay_type == overlay_type,
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0


async def delete_overlays_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> int:
    """Delete all overlays for a project. Returns count deleted."""
    stmt = (
        sa.delete(AcnrProjectOverlay)
        .where(AcnrProjectOverlay.project_id == project_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount
