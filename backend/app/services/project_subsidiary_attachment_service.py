"""把已有单体项目安全纳入合并项目的事务内编排。"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.project_audit_year import resolve_project_audit_year


def _topology_identity(project: Project) -> tuple[int | None, str, str, bool]:
    return (
        resolve_project_audit_year(project),
        (project.company_code or "").strip(),
        project.report_scope or "standalone",
        bool(project.is_deleted),
    )


async def attach_subsidiaries(
    db: AsyncSession,
    *,
    parent_project_id: UUID,
    child_project_ids: Iterable[UUID],
    actor: Any,
) -> tuple[list[Project], int | None]:
    """锁定并改写三码，校验最终图；只 flush，由路由统一 commit。"""
    parent = await db.get(Project, parent_project_id)
    if parent is None or parent.is_deleted:
        raise HTTPException(status_code=404, detail="项目不存在")
    if parent.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="仅合并项目可配置合并范围")

    parent_identity = _topology_identity(parent)
    parent_code = parent_identity[1]
    if not parent_code:
        raise HTTPException(status_code=400, detail="本合并项目未填企业代码，无法按三码纳入下级企业")
    requested_ids = list(dict.fromkeys(child_project_ids))
    initial_children = list((await db.execute(
        sa.select(Project).where(Project.id.in_(requested_ids))
    )).scalars().all()) if requested_ids else []
    child_identities = {child.id: _topology_identity(child) for child in initial_children}
    year = parent_identity[0]

    from app.services.group_topology_lock import lock_topology_years

    await lock_topology_years(
        db, [year, *(identity[0] for identity in child_identities.values())]
    )
    await db.refresh(parent)
    if _topology_identity(parent) != parent_identity:
        raise HTTPException(status_code=409, detail="合并项目基本信息已变化，请刷新后重试")
    for child in initial_children:
        await db.refresh(child)
        if _topology_identity(child) != child_identities[child.id]:
            raise HTTPException(status_code=409, detail="待纳入项目基本信息已变化，请刷新后重试")

    from app.deps import assert_project_permission
    from app.services.project_creation_grant_service import (
        ProjectCreationGrantStale,
        lock_actor_and_project_memberships,
    )

    try:
        await lock_actor_and_project_memberships(
            db, actor, [parent_project_id, *child_identities],
        )
    except ProjectCreationGrantStale as exc:
        raise HTTPException(status_code=409, detail="当前用户状态已变化，请重新登录后重试") from exc
    role = getattr(getattr(actor, "role", None), "value", getattr(actor, "role", None))
    if role == "admin":
        # 管理员可整理任意同年度单体项目。
        writable_ids = set(child_identities)
    elif role == "partner":
        # 合伙人只能整理自己名下的项目（本合并项目与各下级都须在其可见集内）。
        from app.services.partner_visibility_service import partner_visible_project_ids

        partner_pids = await partner_visible_project_ids(actor, db)
        if parent_project_id not in partner_pids:
            raise HTTPException(status_code=403, detail="权限不足")
        writable_ids = set(child_identities) & partner_pids
    else:
        # 其他角色既要能维护本合并范围，也要对每个下级有编制权限；只读成员不能改三码。
        await assert_project_permission(db, actor, parent_project_id, "edit")
        writable_ids = set()
        for child in initial_children:
            try:
                await assert_project_permission(db, actor, child.id, "edit")
            except HTTPException:
                continue
            writable_ids.add(child.id)
    parent_code = (parent.company_code or "").strip()
    ultimate_code = (parent.ultimate_company_code or "").strip() or parent_code
    ultimate_name = parent.ultimate_company_name or parent.client_name
    children_by_id = {child.id: child for child in initial_children}

    from app.services.group_links import apply_group_values, propagate_to_counterpart
    from app.services.group_relation import resolve_relation

    attached: list[Project] = []
    for child_id in requested_ids:
        if child_id == parent_project_id or child_id not in writable_ids:
            continue
        child = children_by_id.get(child_id)
        if child is None or child.is_deleted or child.report_scope == "consolidated":
            continue
        if (child.company_code or "").strip() == parent_code:
            continue
        if resolve_project_audit_year(child) != year:
            continue
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
        child.consol_level = (parent.consol_level or 1) + 1
        attached.append(child)

    if attached:
        await _assert_final_graph_has_no_cycle(db, year)
        from app.services.group_links import sync_group_links

        await sync_group_links(db, year)
    return attached, year


async def _assert_final_graph_has_no_cycle(
    db: AsyncSession,
    year: int | None,
) -> None:
    await db.flush()
    from app.services.consol_group_tree import load_year_records
    from app.services.group_forest import build_forest

    forest = build_forest(await load_year_records(db, year), year=year)
    stack = [
        node
        for tree in forest.get("trees", [])
        for node in (tree.get("children") or [])
    ]
    while stack:
        node = stack.pop()
        if node.get("isCycleBreak") or "cycle_break" in (node.get("flags") or []):
            raise HTTPException(
                status_code=409,
                detail="纳入下级企业后会形成循环引用，已取消本次操作",
            )
        stack.extend(node.get("children") or [])


__all__ = ["attach_subsidiaries"]
