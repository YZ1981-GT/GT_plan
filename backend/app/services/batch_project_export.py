"""批量建项模板导出：普通项目复制模板与当前合并企业树。"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_types import (
    accounting_standard as _accounting_standard,
    project_year as _project_year,
)


def _project_export_row(
    project: Project, *, action: str = "create", base_hash: str | None = None,
) -> list[Any]:
    project_type = getattr(project.project_type, "value", project.project_type) or ""
    return [
        project.client_name,
        project.company_code or "",
        project.short_name or "",
        project.audit_year or "",
        workbook_io.PROJECT_TYPE_REVERSE.get(str(project_type), ""),
        workbook_io.ACCOUNTING_STANDARD_REVERSE.get(_accounting_standard(project), ""),
        workbook_io.REPORT_SCOPE_REVERSE.get(project.report_scope or "standalone", "单户"),
        project.parent_company_code or "",
        project.ultimate_company_code or "",
        workbook_io.RELATION_REVERSE.get(project.relation_to_parent or "", ""),
        workbook_io.ACTION_REVERSE.get(action, "新建"),
        str(project.id) if action == "update" else "",
        workbook_io.group_fields_hash(project) if action == "update" and base_hash is None
        else (base_hash or ""),
    ]


async def export_projects(
    project_ids: list[UUID], db: AsyncSession, *, mode: str = "project",
) -> BytesIO:
    unique_ids = list(dict.fromkeys(project_ids))
    if not unique_ids:
        raise HTTPException(status_code=422, detail="请至少选择一个项目")
    projects = list((await db.execute(sa.select(Project).where(
        Project.id.in_(unique_ids), Project.is_deleted == sa.false(),
    ))).scalars().all())
    by_id = {project.id: project for project in projects}
    if set(by_id) != set(unique_ids):
        raise HTTPException(status_code=404, detail="所选项目不存在或已删除")
    rows = [_project_export_row(by_id[project_id]) for project_id in unique_ids]
    return workbook_io.export_workbook(rows, mode=mode)


async def export_group_tree(root_project_id: UUID, db: AsyncSession) -> tuple[BytesIO, list[UUID]]:
    root = await db.get(Project, root_project_id)
    if root is None or root.is_deleted:
        raise HTTPException(status_code=404, detail="合并项目不存在")
    if (root.report_scope or "standalone") != "consolidated":
        raise HTTPException(status_code=400, detail="只有合并项目可以导出当前集团树")
    from app.services.consol_tree_service import build_tree, iter_nodes
    tree = await build_tree(db, root_project_id)
    if tree is None:
        raise HTTPException(status_code=409, detail="当前企业树尚未生成")
    all_tree_ids = list(dict.fromkeys(
        node.project_id for node in iter_nodes(tree) if node.project_id is not None
    ))
    projects = list((await db.execute(sa.select(Project).where(
        Project.id.in_(all_tree_ids), Project.is_deleted == sa.false(),
    ))).scalars().all())
    by_id = {project.id: project for project in projects}
    if set(by_id) != set(all_tree_ids):
        raise HTTPException(status_code=409, detail="企业树中的项目已变化，请刷新后重试")

    entity_order: list[tuple[str, int | None]] = []
    candidates: dict[tuple[str, int | None], list[Project]] = defaultdict(list)
    for project_id in all_tree_ids:
        project = by_id[project_id]
        entity_key = ((project.company_code or "").strip(), _project_year(project))
        if entity_key not in candidates:
            entity_order.append(entity_key)
        candidates[entity_key].append(project)
    selected: list[Project] = []
    for entity_key in entity_order:
        choices = candidates[entity_key]
        choices.sort(key=lambda item: (
            (item.report_scope or "standalone") != "standalone", str(item.id)
        ))
        selected.append(choices[0])
    rows = [
        _project_export_row(
            project, action="update",
            base_hash=workbook_io.entity_group_fields_hash(candidates[entity_key]),
        )
        for project, entity_key in zip(selected, entity_order)
    ]
    return workbook_io.export_workbook(
        rows, mode="consolidation", root_project_id=str(root_project_id)
    ), all_tree_ids


__all__ = ["export_group_tree", "export_projects"]
