"""Overlay Repository — CRUD for acnr_project_overlay (PG-backed).

Provides persistence layer for L2 ProjectOverlay data.
Memory cache (`overlay.py`) delegates write/read to this repository.

Requirements: Req-4 (Overlay 持久化与归属校验)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acnr_overlay_model import AcnrProjectOverlay

logger = logging.getLogger(__name__)


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
) -> AcnrProjectOverlay:
    """Upsert: if exists update payload+updated_at, else insert."""
    stmt = (
        sa.select(AcnrProjectOverlay)
        .where(
            AcnrProjectOverlay.project_id == project_id,
            AcnrProjectOverlay.parent_wp_code == parent_wp_code,
            AcnrProjectOverlay.sheet_code == sheet_code,
            AcnrProjectOverlay.overlay_type == overlay_type,
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.payload = {**payload}  # 新对象触发 ORM 脏标记
        existing.wp_id = wp_id
        existing.updated_at = datetime.now(tz=None)  # noqa: DTZ005 — server-default handles TZ
        await session.flush()
        logger.info(
            "overlay_repo.upsert(update): project=%s %s/%s type=%s",
            project_id, parent_wp_code, sheet_code, overlay_type,
        )
        return existing

    return await create_overlay(
        session,
        project_id=project_id,
        wp_id=wp_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        overlay_type=overlay_type,
        payload=payload,
    )


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
