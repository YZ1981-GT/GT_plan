"""合并范围服务"""

from uuid import UUID

from sqlalchemy import and_

from app.models.consolidation_models import ConsolScope
from app.models.consolidation_schemas import (
    ConsolScopeBatchUpdate,
    ConsolScopeCreate,
    ConsolScopeResponse,
    ConsolScopeUpdate,
    ConsolScopeSummary,
)


def get_scope_list(db, project_id: UUID, year: int) -> list[ConsolScope]:
    return (
        db.query(ConsolScope)
        .filter(
            ConsolScope.project_id == project_id,
            ConsolScope.year == year,
            ConsolScope.is_deleted.is_(False),
        )
        .all()
    )


def get_scope_item(db, scope_id: UUID, project_id: UUID) -> ConsolScope | None:
    return (
        db.query(ConsolScope)
        .filter(ConsolScope.id == scope_id, ConsolScope.project_id == project_id)
        .first()
    )


def create_scope_item(db, project_id: UUID, data: ConsolScopeCreate) -> ConsolScope:
    existing = (
        db.query(ConsolScope)
        .filter(
            ConsolScope.project_id == project_id,
            ConsolScope.year == data.year,
            ConsolScope.company_code == data.company_code,
            ConsolScope.is_deleted.is_(False),
        )
        .first()
    )
    if existing:
        raise ValueError(f"合并范围项已存在: {data.year}/{data.company_code}")

    scope = ConsolScope(project_id=project_id, **data.model_dump())
    db.add(scope)
    db.commit()
    db.refresh(scope)
    return scope


def update_scope_item(
    db, scope_id: UUID, project_id: UUID, data: ConsolScopeUpdate
) -> ConsolScope | None:
    scope = get_scope_item(db, scope_id, project_id)
    if not scope:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(scope, key, value)
    db.commit()
    db.refresh(scope)
    return scope


def delete_scope_item(db, scope_id: UUID, project_id: UUID) -> bool:
    scope = get_scope_item(db, scope_id, project_id)
    if not scope:
        return False
    scope.soft_delete()
    db.commit()
    return True


def batch_update_scope(
    db, project_id: UUID, data: ConsolScopeBatchUpdate
) -> list[ConsolScope]:
    """批量更新合并范围"""
    results: list[ConsolScope] = []
    for item in data.scope_items:
        existing = (
            db.query(ConsolScope)
            .filter(
                ConsolScope.project_id == project_id,
                ConsolScope.year == item.year,
                ConsolScope.company_code == item.company_code,
                ConsolScope.is_deleted.is_(False),
            )
            .first()
        )
        if existing:
            for key, value in item.model_dump(exclude_unset=True).items():
                setattr(existing, key, value)
            results.append(existing)
        else:
            scope = ConsolScope(project_id=project_id, **item.model_dump())
            db.add(scope)
            results.append(scope)

    db.commit()
    for r in results:
        db.refresh(r)
    return results


def get_scope_summary(db, project_id: UUID, year: int) -> ConsolScopeSummary:
    items = get_scope_list(db, project_id, year)
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
