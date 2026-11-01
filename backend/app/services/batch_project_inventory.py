"""批量建项计划的库存、预览与权限依赖快照。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_types import project_year as _project_year


def entity_key(code: object, year: int | None) -> tuple[str, int] | None:
    clean_code = str(code or "").strip()
    return (clean_code, year) if clean_code and year is not None else None


def dependency_entity_keys(rows: list[workbook_io.ParsedRow]) -> set[tuple[str, int]]:
    """返回会影响计划预览、建项或自动根选择的库存企业集合。"""
    keys: set[tuple[str, int]] = set()
    for row in rows:
        if row.action == "skip" or row.audit_year is None:
            continue
        for code in (row.company_code, row.parent_company_code, row.ultimate_company_code):
            key = entity_key(code, row.audit_year)
            if key is not None:
                keys.add(key)
    return keys


def _inventory_project(project: Project) -> dict[str, str]:
    return {
        "id": str(project.id),
        "report_scope": project.report_scope or "standalone",
        "parent_company_code": (project.parent_company_code or "").strip(),
        "ultimate_company_code": (project.ultimate_company_code or "").strip(),
        "relation_to_parent": project.relation_to_parent or "",
    }


def inventory_snapshot(
    projects: list[Project], entity_keys: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    """稳定序列化指定企业的所有口径，供计划 CAS 比较。"""
    grouped: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for project in projects:
        key = entity_key(project.company_code, _project_year(project))
        if key in entity_keys:
            grouped[key].append(_inventory_project(project))
    return [
        {
            "company_code": code,
            "audit_year": year,
            "projects": sorted(items, key=lambda item: item["id"]),
        }
        for code, year in sorted(entity_keys)
        for items in [grouped.get((code, year), [])]
    ]


def _preview_project_ids(trees: list[dict]) -> set[str]:
    ids: set[str] = set()
    stack = [node for tree in trees for node in (tree.get("children") or [])]
    for tree in trees:
        root_id = tree.get("rootProjectId")
        if root_id:
            ids.add(str(root_id))
    while stack:
        node = stack.pop()
        for project in node.get("projects") or []:
            project_id = project.get("id") if isinstance(project, dict) else None
            if project_id:
                ids.add(str(project_id))
        stack.extend(node.get("children") or [])
    return ids


def build_plan_dependencies(
    rows: list[workbook_io.ParsedRow],
    *,
    visible_projects: list[Project],
    visible_by_code_year: dict[tuple[str, int | None], list[Project]],
    tree_preview: list[dict],
    template_root_project_id: UUID | None,
) -> dict[str, Any]:
    """构建只存服务端的库存与权限依赖，状态响应绝不回传此对象。"""
    entity_keys = dependency_entity_keys(rows)
    known_ids = {str(project.id) for project in visible_projects}
    read_ids = _preview_project_ids(tree_preview) & known_ids
    edit_ids: set[str] = set()
    for row in rows:
        if row.action not in ("create", "update") or row.audit_year is None:
            continue
        codes = [row.company_code] if row.action == "update" else [
            row.company_code, row.parent_company_code, row.ultimate_company_code,
        ]
        for code in codes:
            key = entity_key(code, row.audit_year)
            if key is None:
                continue
            for project in visible_by_code_year.get(key, []):
                project_id = str(project.id)
                read_ids.add(project_id)
                edit_ids.add(project_id)
    if template_root_project_id is not None:
        root_id = str(template_root_project_id)
        read_ids.add(root_id)
        if any(row.action in ("create", "update") for row in rows):
            edit_ids.add(root_id)
    return {
        "version": 1,
        "template_root_project_id": str(template_root_project_id) if template_root_project_id else None,
        "inventory_entities": inventory_snapshot(visible_projects, entity_keys),
        "read_project_ids": sorted(read_ids),
        "edit_project_ids": sorted(edit_ids),
    }


async def load_dependency_inventory(
    db: AsyncSession,
    dependencies: dict[str, Any],
    *,
    for_update: bool = False,
) -> tuple[list[Project], set[tuple[str, int]]]:
    """按计划中保存的企业集合重读当前库存；调用方已锁全年时仍可重用。"""
    raw_entities = dependencies.get("inventory_entities")
    if not isinstance(raw_entities, list):
        raise HTTPException(status_code=409, detail="预校验计划缺少库存基线，请重新预校验")
    entity_keys: set[tuple[str, int]] = set()
    for item in raw_entities:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="预校验计划库存基线无效，请重新预校验")
        code = item.get("company_code")
        year = item.get("audit_year")
        if not isinstance(year, int):
            raise HTTPException(status_code=409, detail="预校验计划库存基线无效，请重新预校验")
        key = entity_key(code, year)
        if key is None:
            raise HTTPException(status_code=409, detail="预校验计划库存基线无效，请重新预校验")
        entity_keys.add(key)
    if not entity_keys:
        return [], entity_keys
    codes = sorted({code for code, _year in entity_keys})
    years = sorted({year for _code, year in entity_keys})
    stmt = sa.select(Project).where(
        Project.company_code.in_(codes),
        Project.audit_year.in_(years),
        Project.is_deleted == sa.false(),
    )
    if for_update:
        stmt = stmt.with_for_update()
    projects = list((await db.execute(stmt)).scalars().all())
    return projects, entity_keys


def inventory_baseline_matches(
    dependencies: dict[str, Any],
    current_projects: list[Project],
    entity_keys: set[tuple[str, int]],
) -> bool:
    expected = dependencies.get("inventory_entities")
    return isinstance(expected, list) and expected == inventory_snapshot(current_projects, entity_keys)


__all__ = [
    "build_plan_dependencies",
    "entity_key",
    "inventory_baseline_matches",
    "inventory_snapshot",
    "load_dependency_inventory",
]
