"""批量项目创建者成员初始化与自动合并根创建。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_types import (
    accounting_standard as _accounting_standard,
    role_value as _role_value,
)


async def assign_new_project_creator(
    db: AsyncSession,
    project: Project,
    actor: Any | None,
    staff_id: UUID | None,
    *,
    persist_assignment: bool = True,
) -> None:
    if actor is None:
        return
    project.created_by = actor.id
    project.updated_by = actor.id
    actor_role = _role_value(actor)
    if actor_role == "partner":
        if persist_assignment:
            from app.services.assignment_service import AssignmentService

            await AssignmentService(db).initialize_project_partners(
                [project.id], user_id=actor.id, assigned_by=actor.id,
                require_pending=False,
            )
        return
    if actor_role != "manager":
        return
    project.manager_id = actor.id
    if not persist_assignment:
        return
    from app.services.assignment_service import AssignmentService

    if staff_id is None:
        # 未绑定人员档案：只加项目成员（经理、编辑），不写团队委派（R7）。
        await AssignmentService(db).initialize_creator_members(
            [project.id], user_id=actor.id, assigned_by=actor.id,
            role_key="manager", require_pending=False,
        )
        return
    await AssignmentService(db).save_assignments(
        project.id,
        [{"staff_id": staff_id, "role": "manager", "assigned_cycles": None}],
        assigned_by=actor.id,
    )


async def ensure_consolidated_root(
    db: AsyncSession,
    *,
    ultimate_code: str,
    audit_year: int,
    group_rows: list[workbook_io.ParsedRow],
    created_by_key: dict[tuple[str, int, str], Project],
    actor: Any | None,
    staff_id: UUID | None,
    existing_projects: list[Project] | None = None,
    defer_flush: bool = False,
    persist_manager_assignment: bool = True,
) -> tuple[Project, bool]:
    key = (ultimate_code, audit_year, "consolidated")
    if key in created_by_key:
        return created_by_key[key], False
    candidates = existing_projects
    if candidates is None:
        candidates = list((await db.execute(sa.select(Project).where(
            Project.company_code == ultimate_code,
            Project.audit_year == audit_year,
            Project.is_deleted == sa.false(),
        ))).scalars().all())
    existing = next(
        (project for project in candidates if (project.report_scope or "standalone") == "consolidated"),
        None,
    )
    if existing is not None:
        return existing, False

    own_row = next((row for row in group_rows if row.company_code == ultimate_code), None)
    existing_standalone = next(
        (project for project in candidates if (project.report_scope or "standalone") == "standalone"),
        None,
    )
    source = own_row or (group_rows[0] if group_rows else None)
    display_name = (
        (own_row.client_name if own_row else "")
        or (existing_standalone.client_name if existing_standalone else "")
        or f"{ultimate_code}（自动创建合并项目）"
    )
    standard = (
        source.accounting_standard if source and source.accounting_standard
        else _accounting_standard(existing_standalone) if existing_standalone else "enterprise"
    )
    project_type = source.project_type if source and source.project_type else "annual"
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    data = BasicInfoSchema(
        client_name=display_name, audit_year=audit_year,
        project_type=project_type, accounting_standard=standard,
        company_code=ultimate_code, short_name=display_name[:100],
        report_scope="consolidated", ultimate_company_code=ultimate_code,
        ultimate_company_name=display_name,
        manager_id=actor.id if actor is not None and _role_value(actor) == "manager" else None,
    )
    project = await create_project(
        data, db, auto_commit=False, propagate_group=False, sync_links=False,
        uniqueness_checked=True, group_fields_prepared=True,
        defer_flush=defer_flush,
    )
    await assign_new_project_creator(
        db, project, actor, staff_id,
        persist_assignment=persist_manager_assignment,
    )
    created_by_key[key] = project
    return project, True


__all__ = ["assign_new_project_creator", "ensure_consolidated_root"]
