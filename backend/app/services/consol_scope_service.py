"""合并范围服务 — 异步 ORM"""

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
    return scope


async def delete_scope_item(db: AsyncSession, scope_id: UUID, project_id: UUID) -> bool:
    scope = await get_scope_item(db, scope_id, project_id)
    if not scope:
        return False
    scope.soft_delete()
    await db.commit()
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
