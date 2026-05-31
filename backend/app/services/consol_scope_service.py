"""合并范围服务 — 异步 ORM"""

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolScope
from app.models.consolidation_schemas import (
    ConsolScopeBatchUpdate,
    ConsolScopeCreate,
    ConsolScopeResponse,
    ConsolScopeUpdate,
    ConsolScopeSummary,
)

logger = logging.getLogger(__name__)


def _emit_scope_changed(project_id: UUID, year: int | None) -> None:
    """合并范围增删改后广播 CONSOL_SCOPE_CHANGED（需求 5.2 / ADR-CONSOL-303）。

    走 event_bus.broadcast_raw（同步、轻量）推 SSE，前端 ConsolidationIndex 监听后
    自动刷新企业树（失效/重建树缓存）。无 event_bus / 无 event loop 时静默回退到 logger，
    不阻断业务（EH4：事件丢失由前端"刷新树"按钮兜底）。
    """
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            "consol.scope_changed",
            {"project_id": str(project_id), "year": year},
        )
    except Exception as exc:  # pragma: no cover - 兜底，不阻断业务
        logger.debug("broadcast consol.scope_changed failed (non-blocking): %s", exc)


async def get_scope_list(db: AsyncSession, project_id: UUID, year: int) -> list[ConsolScope]:
    result = await db.execute(
        sa.select(ConsolScope).where(
            ConsolScope.project_id == project_id,
            ConsolScope.year == year,
            ConsolScope.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def get_scope_item(db: AsyncSession, scope_id: UUID, project_id: UUID) -> ConsolScope | None:
    result = await db.execute(
        sa.select(ConsolScope).where(
            ConsolScope.id == scope_id,
            ConsolScope.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_scope_item(db: AsyncSession, project_id: UUID, data: ConsolScopeCreate) -> ConsolScope:
    result = await db.execute(
        sa.select(ConsolScope).where(
            ConsolScope.project_id == project_id,
            ConsolScope.year == data.year,
            ConsolScope.company_code == data.company_code,
            ConsolScope.is_deleted.is_(False),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError(f"合并范围项已存在: {data.year}/{data.company_code}")

    scope = ConsolScope(project_id=project_id, **data.model_dump())
    db.add(scope)
    await db.commit()
    await db.refresh(scope)
    _emit_scope_changed(project_id, getattr(data, "year", None))
    return scope


async def update_scope_item(
    db: AsyncSession, scope_id: UUID, project_id: UUID, data: ConsolScopeUpdate
) -> ConsolScope | None:
    scope = await get_scope_item(db, scope_id, project_id)
    if not scope:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(scope, key, value)
    await db.commit()
    await db.refresh(scope)
    _emit_scope_changed(project_id, scope.year)
    return scope


async def delete_scope_item(db: AsyncSession, scope_id: UUID, project_id: UUID) -> bool:
    scope = await get_scope_item(db, scope_id, project_id)
    if not scope:
        return False
    scope_year = scope.year
    scope.soft_delete()
    await db.commit()
    _emit_scope_changed(project_id, scope_year)
    return True


async def batch_update_scope(
    db: AsyncSession, project_id: UUID, data: ConsolScopeBatchUpdate
) -> list[ConsolScope]:
    """批量更新合并范围"""
    results: list[ConsolScope] = []
    for item in data.scope_items:
        result = await db.execute(
            sa.select(ConsolScope).where(
                ConsolScope.project_id == project_id,
                ConsolScope.year == item.year,
                ConsolScope.company_code == item.company_code,
                ConsolScope.is_deleted.is_(False),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in item.model_dump(exclude_unset=True).items():
                setattr(existing, key, value)
            results.append(existing)
        else:
            scope = ConsolScope(project_id=project_id, **item.model_dump())
            db.add(scope)
            results.append(scope)

    await db.commit()
    for r in results:
        await db.refresh(r)
    _emit_scope_changed(project_id, data.scope_items[0].year if data.scope_items else None)
    return results


async def get_scope_summary(db: AsyncSession, project_id: UUID, year: int) -> ConsolScopeSummary:
    items = await get_scope_list(db, project_id, year)
    included = sum(1 for i in items if i.is_included)
    scope_changes = sum(
        1 for i in items if i.scope_change_type and i.scope_change_type.value != "none"
    )
    return ConsolScopeSummary(
        total_companies=len(items),
        included_companies=included,
        excluded_companies=len(items) - included,
        scope_changes=scope_changes,
    )
