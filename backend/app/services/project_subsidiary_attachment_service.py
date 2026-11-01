"""把既有单体项目安全纳入合并项目的事务编排。

先做只读身份快照以确定年度锁域，再取年度 advisory lock；锁内重读父/子身份做 CAS、
冻结成员关系、校项目 edit 权限，最后写三码并校验整年度最终图无环。只 flush，由路由提交。

spec: batch-project-authorization-and-lock-hardening R4.4
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.batch_project_types import project_year, role_value


def _identity(row: Any) -> tuple[Any, ...]:
    return (
        row.audit_year,
        str(row.company_code or "").strip(),
        row.report_scope or "standalone",
        bool(row.is_deleted),
    )


def _tree_flags(forest: dict[str, Any]) -> set[str]:
    flags: set[str] = set()
    stack = [
        node
        for tree in forest.get("trees", [])
        for node in (tree.get("children") or [])
    ] + list(forest.get("independents") or [])
    while stack:
        node = stack.pop()
        flags.update(node.get("flags") or [])
        if node.get("isCycleBreak"):
            flags.add("cycle_break")
        stack.extend(node.get("children") or [])
    return flags


async def _load_projects(
    db: AsyncSession,
    ids: Iterable[UUID],
    *,
    lock: bool,
) -> dict[UUID, Project]:
    unique = sorted(set(ids), key=str)
    if not unique:
        return {}
    stmt = sa.select(Project).where(Project.id.in_(unique))
    if lock:
        stmt = stmt.with_for_update()
    return {row.id: row for row in (await db.execute(stmt)).scalars().all()}


async def attach_subsidiaries(
    db: AsyncSession,
    *,
    parent_project_id: UUID,
    child_project_ids: Iterable[UUID],
    actor: Any,
) -> tuple[list[Project], int | None]:
    """纳入下级项目；返回实际处理的请求子项目与审计年度。"""
    requested = [UUID(str(value)) for value in dict.fromkeys(child_project_ids)]
    probe_ids = [parent_project_id, *requested]
    before = await _load_projects(db, probe_ids, lock=False)
    parent_probe = before.get(parent_project_id)
    if parent_probe is None or parent_probe.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    from app.services.group_topology_lock import lock_topology_years

    await lock_topology_years(db, [project_year(row) for row in before.values()])
    locked = await _load_projects(db, probe_ids, lock=True)
    parent = locked.get(parent_project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if _identity(parent) != _identity(parent_probe):
        raise HTTPException(status_code=409, detail="合并项目身份已变化，请刷新后重试")
    for project_id, snapshot in before.items():
        current = locked.get(project_id)
        if current is None or _identity(current) != _identity(snapshot):
            raise HTTPException(status_code=409, detail="下级项目身份已变化，请刷新后重试")
    if (parent.report_scope or "standalone") != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    parent_code = str(parent.company_code or "").strip()
    if not parent_code:
        raise HTTPException(status_code=400, detail="本合并项目未填企业代码，无法按三码纳入下级企业")
    year = project_year(parent)
    ultimate_code = str(parent.ultimate_company_code or "").strip() or parent_code
    ultimate_name = parent.ultimate_company_name or parent.client_name

    eligible: list[Project] = []
    seen_codes: set[str] = set()
    for project_id in requested:
        if project_id == parent_project_id:
            continue
        child = locked.get(project_id)
        if child is None or child.is_deleted:
            continue
        code = str(child.company_code or "").strip()
        if (
            (child.report_scope or "standalone") == "consolidated"
            or not code
            or code == parent_code
            or project_year(child) != year
            or code in seen_codes
        ):
            continue
        seen_codes.add(code)
        eligible.append(child)

    # propagate_to_counterpart 会同写同企业另一报表口径；先把它们也锁住并纳入权限检查。
    counterpart_rows: list[Project] = []
    if seen_codes:
        stmt = sa.select(Project).where(
            Project.company_code.in_(sorted(seen_codes)),
            Project.audit_year == year,
            Project.is_deleted == sa.false(),
        ).with_for_update()
        counterpart_rows = list((await db.execute(stmt)).scalars().all())
    permission_ids = {parent.id, *(row.id for row in eligible), *(row.id for row in counterpart_rows)}
    actor_role = role_value(actor)
    if actor_role not in {"admin", "partner"}:
        from app.deps import assert_project_permission
        from app.services.project_creation_grant_service import lock_actor_and_project_memberships

        await lock_actor_and_project_memberships(db, actor, permission_ids)
        for project_id in sorted(permission_ids, key=str):
            await assert_project_permission(db, actor, project_id, "edit")

    from app.services.group_links import apply_group_values, propagate_to_counterpart
    from app.services.group_relation import resolve_relation

    attached: list[Project] = []
    for child in eligible:
        apply_group_values(child, {
            "parent_company_name": parent.client_name,
            "parent_company_code": parent_code,
            "relation_to_parent": resolve_relation(
                child.relation_to_parent, parent_code, child.client_name, child.company_code
            ),
            "ultimate_company_name": ultimate_name,
            "ultimate_company_code": ultimate_code,
        })
        await propagate_to_counterpart(db, child)
        child.consol_level = int(parent.consol_level or 1) + 1
        child.updated_by = getattr(actor, "id", None)
        attached.append(child)

    if not attached:
        return [], year

    await db.flush()
    from app.services.group_forest import build_forest

    final_projects = list((await db.execute(sa.select(Project).where(
        Project.audit_year == year,
        Project.is_deleted == sa.false(),
    ))).scalars().all())
    flags = _tree_flags(build_forest(final_projects, year=year))
    if "cycle_break" in flags:
        raise HTTPException(status_code=409, detail="纳入下级企业后会形成循环引用，已取消操作")
    if "relation_conflict" in flags:
        raise HTTPException(status_code=409, detail="纳入后单户与合并项目集团关系不一致，已取消操作")

    from app.services.group_links import sync_group_links

    await sync_group_links(db, year)
    return attached, year


__all__ = ["attach_subsidiaries"]
