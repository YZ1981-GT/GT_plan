"""批量建项计划的库存与权限依赖快照。

预校验记录所有会影响创建、自动合并根和集团关系更新的企业实体；apply 在年度锁和成员锁
之后按同一口径 ``FOR UPDATE`` 重读并逐值比较。确认后出现/消失一个项目，或集团字段变化，
都会使计划 stale，不会静默采用新库存。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.batch_project_types import accounting_standard, project_year

EntityKey = tuple[str, int]


def entity_key(company_code: Any, audit_year: Any) -> EntityKey | None:
    """规范化企业实体键；缺代码或年度时不形成库存依赖。"""
    code = str(company_code or "").strip().upper()
    if not code or audit_year is None or audit_year == "":
        return None
    try:
        year = int(audit_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("库存依赖的审计年度无效") from exc
    return code, year


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _project_snapshot(project: Project) -> dict[str, Any]:
    """只冻结计划实际消费的项目字段，避免无关字段修改造成假 stale。"""
    return {
        "id": str(project.id),
        "report_scope": _clean(project.report_scope) or "standalone",
        "client_name": project.client_name or "",
        "short_name": project.short_name or "",
        "project_type": _value(project.project_type),
        "accounting_standard": accounting_standard(project),
        "parent_company_code": _clean(project.parent_company_code),
        "parent_company_name": _clean(project.parent_company_name),
        "ultimate_company_code": _clean(project.ultimate_company_code),
        "ultimate_company_name": _clean(project.ultimate_company_name),
        "relation_to_parent": _clean(project.relation_to_parent),
        "consol_level": int(project.consol_level or 1),
    }


def _tree_nodes(trees: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    stack = [node for tree in trees for node in (tree.get("children") or [])]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.get("children") or [])


def _relevant_keys(rows: Iterable[Any], tree_preview: Iterable[dict[str, Any]]) -> set[EntityKey]:
    keys: set[EntityKey] = set()
    for row in rows:
        if str(getattr(row, "action", "create")) == "skip":
            continue
        year = getattr(row, "audit_year", None)
        for code in (
            getattr(row, "company_code", None),
            getattr(row, "parent_company_code", None),
            getattr(row, "ultimate_company_code", None),
        ):
            key = entity_key(code, year)
            if key is not None:
                keys.add(key)
    for node in _tree_nodes(tree_preview):
        key = entity_key(node.get("companyCode"), node.get("year"))
        if key is not None:
            keys.add(key)
    return keys


def build_plan_dependencies(
    rows: Iterable[Any],
    *,
    visible_projects: Iterable[Project],
    visible_by_code_year: Mapping[tuple[str, Any], list[Project]],
    tree_preview: list[dict[str, Any]],
    template_root_project_id: UUID | None,
) -> dict[str, Any]:
    """构建持久计划的私有库存、读取和编辑依赖（JSON 可序列化）。"""
    row_list = list(rows)
    project_list = list(visible_projects)
    keys = _relevant_keys(row_list, tree_preview)
    # 参数是预校验已经按可见性建立的单次索引；只取相关键，不能把同年度无关项目
    # 全塞入基线，否则另一客户建项会让本计划误 stale。
    by_key: dict[EntityKey, list[Project]] = defaultdict(list)
    for raw_key, projects in visible_by_code_year.items():
        key = entity_key(raw_key[0], raw_key[1])
        if key in keys:
            by_key[key].extend(projects)
    # 防调用方索引遗漏：以 visible_projects 复核补齐。
    for project in project_list:
        key = entity_key(project.company_code, project_year(project))
        if key in keys and all(item.id != project.id for item in by_key[key]):
            by_key[key].append(project)

    read_ids = {
        str(project.id)
        for key in keys
        for project in by_key.get(key, [])
    }
    edit_ids: set[str] = set()
    for row in row_list:
        if str(getattr(row, "action", "")) != "update":
            continue
        key = entity_key(getattr(row, "company_code", None), getattr(row, "audit_year", None))
        if key is not None:
            edit_ids.update(str(project.id) for project in by_key.get(key, []))
        project_id = getattr(row, "project_id", None)
        if project_id is not None:
            edit_ids.add(str(project_id))
    if template_root_project_id is not None:
        root_id = str(template_root_project_id)
        read_ids.add(root_id)
        edit_ids.add(root_id)

    entities = [
        {
            "company_code": code,
            "audit_year": year,
            "projects": sorted(
                (_project_snapshot(project) for project in by_key.get((code, year), [])),
                key=lambda item: (item["report_scope"], item["id"]),
            ),
        }
        for code, year in sorted(keys)
    ]
    return {
        "version": 1,
        "template_root_project_id": str(template_root_project_id) if template_root_project_id else None,
        "inventory_entities": entities,
        "read_project_ids": sorted(read_ids),
        "edit_project_ids": sorted(edit_ids),
    }


def _dependency_keys(dependencies: dict[str, Any]) -> set[EntityKey]:
    raw = dependencies.get("inventory_entities")
    if not isinstance(raw, list):
        raise HTTPException(status_code=409, detail="预校验计划库存基线无效")
    keys: set[EntityKey] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="预校验计划库存基线无效")
        key = entity_key(item.get("company_code"), item.get("audit_year"))
        if key is None or key in keys or not isinstance(item.get("projects"), list):
            raise HTTPException(status_code=409, detail="预校验计划库存基线无效")
        keys.add(key)
    return keys


async def load_dependency_inventory(
    db: AsyncSession,
    dependencies: dict[str, Any],
    *,
    for_update: bool,
) -> tuple[list[Project], set[EntityKey]]:
    """按持久依赖键一次重读活动库存；写路径用 ``FOR UPDATE``。"""
    if not isinstance(dependencies, dict) or dependencies.get("version") != 1:
        raise HTTPException(status_code=409, detail="预校验计划库存基线无效")
    keys = _dependency_keys(dependencies)
    if not keys:
        return [], set()
    predicates = [
        sa.and_(Project.company_code == code, Project.audit_year == year)
        for code, year in sorted(keys)
    ]
    stmt = sa.select(Project).where(
        Project.is_deleted == sa.false(),
        sa.or_(*predicates),
    ).order_by(Project.company_code, Project.audit_year, Project.report_scope, Project.id)
    if for_update:
        stmt = stmt.with_for_update()
    projects = list((await db.execute(stmt)).scalars().all())
    return projects, keys


def inventory_baseline_matches(
    dependencies: dict[str, Any],
    current_inventory: Iterable[Project],
    inventory_keys: Iterable[EntityKey],
) -> bool:
    """按同一序列化口径逐实体比较，任何出现、消失或相关字段变化都判 stale。"""
    try:
        expected_keys = _dependency_keys(dependencies)
    except (HTTPException, TypeError, ValueError):
        return False
    if set(inventory_keys) != expected_keys:
        return False
    raw_entities = dependencies.get("inventory_entities")
    assert isinstance(raw_entities, list)
    expected: dict[EntityKey, list[dict[str, Any]]] = {}
    for item in raw_entities:
        key = entity_key(item.get("company_code"), item.get("audit_year"))
        if key is None:
            return False
        projects = item.get("projects")
        if not isinstance(projects, list):
            return False
        expected[key] = sorted(projects, key=lambda value: (value.get("report_scope", ""), value.get("id", "")))

    actual: dict[EntityKey, list[dict[str, Any]]] = {key: [] for key in expected_keys}
    for project in current_inventory:
        key = entity_key(project.company_code, project_year(project))
        if key not in actual:
            return False
        actual[key].append(_project_snapshot(project))
    for key in actual:
        actual[key].sort(key=lambda value: (value["report_scope"], value["id"]))
    return actual == expected


__all__ = [
    "build_plan_dependencies",
    "entity_key",
    "inventory_baseline_matches",
    "load_dependency_inventory",
]
