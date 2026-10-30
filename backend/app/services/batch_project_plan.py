"""批量建项数据库感知预校验与原子执行。

该模块是新生产入口；兼容模块 batch_project_service 仅转发公开符号。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import anyio

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_types import (
    BatchActionSummary,
    BatchAnalysis,
    BatchImportFailure,
    BatchImportResult,
    BatchValidateResponse,
    RowError,
    RowWarning,
    accounting_standard as _accounting_standard,
    project_key as _project_key,
    project_year as _project_year,
    public_error as _public_error,
    role_value as _role_value,
    row_key as _key,
)
from app.services.group_relation import (
    SELF_TOP,
    SELF_ULTIMATE,
    resolve_relation,
    self_reference_kind,
)

logger = logging.getLogger(__name__)


_SELF_REFERENCE_ROW_HINTS = {
    SELF_TOP: "上级企业代码与本企业代码相同，将按「本企业就是上级企业」处理（集团顶层企业，不另建上级节点）",
    SELF_ULTIMATE: "三个代码相同，将按「本企业即为最终控制方（集团总部或母公司）」处理",
}


async def _load_year_projects(
    db: AsyncSession,
    rows: list[workbook_io.ParsedRow],
) -> list[Project]:
    years = sorted({row.audit_year for row in rows if row.audit_year is not None})
    ids = sorted({row.project_id for row in rows if row.project_id is not None}, key=str)
    if not years and not ids:
        return []
    predicates = []
    if years:
        predicates.append(Project.audit_year.in_(years))
    if ids:
        predicates.append(Project.id.in_(ids))
    result = await db.execute(
        sa.select(Project).where(
            Project.is_deleted == sa.false(),
            sa.or_(*predicates),
        )
    )
    return list(result.scalars().all())


async def _visible_projects(
    db: AsyncSession,
    projects: list[Project],
    current_user: Any | None,
) -> tuple[list[Project], set[UUID] | None]:
    if current_user is None or _role_value(current_user) == "admin":
        return projects, None
    from app.deps import readable_project_ids
    readable = await readable_project_ids(db, current_user)
    assert readable is not None
    return [project for project in projects if project.id in readable], readable


def _entity_key(code: object, year: int | None) -> tuple[str, int] | None:
    clean_code = str(code or "").strip()
    return (clean_code, year) if clean_code and year is not None else None


def dependency_entity_keys(rows: list[workbook_io.ParsedRow]) -> set[tuple[str, int]]:
    """返回会影响计划预览、建项或自动根选择的库存企业集合。"""
    keys: set[tuple[str, int]] = set()
    for row in rows:
        if row.action == "skip" or row.audit_year is None:
            continue
        for code in (row.company_code, row.parent_company_code, row.ultimate_company_code):
            key = _entity_key(code, row.audit_year)
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
        key = _entity_key(project.company_code, _project_year(project))
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
            key = _entity_key(code, row.audit_year)
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
        key = _entity_key(code, year)
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


def _node_pairs(nodes: list[dict]) -> set[tuple[str, int | None]]:
    found: set[tuple[str, int | None]] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        found.add(((node.get("companyCode") or "").strip(), node.get("year")))
        stack.extend(node.get("children") or [])
    return found


def _filter_preview(forest: dict, incoming: set[tuple[str, int | None]]) -> list[dict]:
    trees = []
    for tree in forest.get("trees", []):
        if _node_pairs(tree.get("children") or []) & incoming:
            trees.append(tree)
    independents = [
        node for node in forest.get("independents", [])
        if ((node.get("companyCode") or "").strip(), node.get("year")) in incoming
    ]
    if independents:
        trees.append({
            "key": "__independent__", "ultimateCode": None,
            "ultimateName": "独立企业", "rootProjectId": None,
            "year": None, "children": independents,
        })
    return trees


def _annotate_preview_actions(
    trees: list[dict], rows: list[workbook_io.ParsedRow], auto_roots: set[tuple[str, int]],
) -> None:
    actions = {
        (row.company_code, row.audit_year): row.action
        for row in rows if row.action in ("create", "update", "unchanged")
    }
    stack = [node for tree in trees for node in (tree.get("children") or [])]
    while stack:
        node = stack.pop()
        key = ((node.get("companyCode") or "").strip(), node.get("year"))
        if key in auto_roots:
            node["plannedAction"] = "auto_root"
        elif key in actions:
            node["plannedAction"] = actions[key]
        stack.extend(node.get("children") or [])


def _tree_flags(trees: list[dict]) -> set[str]:
    flags: set[str] = set()
    stack = [node for tree in trees for node in (tree.get("children") or [])]
    while stack:
        node = stack.pop()
        flags.update(node.get("flags") or [])
        if node.get("isCycleBreak"):
            flags.add("cycle_break")
        stack.extend(node.get("children") or [])
    return flags


def _failure_rows_for_atomic_block(
    parsed_rows: list[workbook_io.ParsedRow],
    errors: list[RowError],
) -> list[BatchImportFailure]:
    by_row = {item.row_number: list(item.errors) for item in errors if item.row_number > 0}
    return [
        BatchImportFailure(
            row_number=row.row_number,
            errors=by_row.get(row.row_number, ["批次存在校验错误，未执行任何建项"]),
        )
        for row in parsed_rows
        if row.action != "skip"
    ]

def _clone_project(project: Project, *, relationship: workbook_io.ParsedRow | None = None) -> SimpleNamespace:
    parent = relationship.parent_company_code if relationship else (project.parent_company_code or "")
    ultimate = relationship.ultimate_company_code if relationship else (project.ultimate_company_code or "")
    relation = (
        resolve_relation(
            relationship.relation_to_parent, parent,
            project.client_name, project.company_code,
        )
        if relationship else project.relation_to_parent
    )
    return SimpleNamespace(
        id=project.id, company_code=project.company_code,
        parent_company_code=parent or None,
        ultimate_company_code=ultimate or None,
        relation_to_parent=relation,
        client_name=project.client_name, report_scope=project.report_scope,
        status=project.status, audit_period_end=project.audit_period_end,
        audit_period_start=project.audit_period_start, audit_year=_project_year(project),
        wizard_state=project.wizard_state, name=project.name,
        consol_level=project.consol_level,
    )


def _prepare_create_group_fields(
    rows: list[workbook_io.ParsedRow],
    existing_by_entity: dict[tuple[str, int | None], list[Project]],
) -> None:
    """用同批行与一次预取的库存补空字段，替代 create_project 的逐行关系查询。"""
    incoming: dict[tuple[str, int | None], list[workbook_io.ParsedRow]] = defaultdict(list)
    for row in rows:
        if row.action == "create":
            incoming[(row.company_code, row.audit_year)].append(row)
    for row in rows:
        if row.action != "create":
            continue
        peers = [peer for peer in incoming[(row.company_code, row.audit_year)] if peer is not row]
        stored = existing_by_entity.get((row.company_code, row.audit_year), [])
        if not row.parent_company_code:
            row.parent_company_code = next(
                (peer.parent_company_code for peer in peers if peer.parent_company_code),
                next((project.parent_company_code or "" for project in stored if project.parent_company_code), ""),
            )
        if not row.ultimate_company_code:
            row.ultimate_company_code = next(
                (peer.ultimate_company_code for peer in peers if peer.ultimate_company_code),
                next((project.ultimate_company_code or "" for project in stored if project.ultimate_company_code), ""),
            )
        if row.relation_to_parent is None:
            row.relation_to_parent = next(
                (peer.relation_to_parent for peer in peers if peer.relation_to_parent),
                next((project.relation_to_parent for project in stored if project.relation_to_parent), None),
            )
        if not row.ultimate_company_code and row.parent_company_code:
            parent_rows = incoming.get((row.parent_company_code, row.audit_year), [])
            row.ultimate_company_code = next(
                (parent.ultimate_company_code for parent in parent_rows if parent.ultimate_company_code),
                "",
            )
            if not row.ultimate_company_code:
                parent_projects = existing_by_entity.get((row.parent_company_code, row.audit_year), [])
                parent_projects = sorted(
                    parent_projects,
                    key=lambda item: ((item.report_scope or "standalone") != "standalone", str(item.id)),
                )
                row.ultimate_company_code = next(
                    (project.ultimate_company_code or "" for project in parent_projects if project.ultimate_company_code),
                    "",
                )
        if row.parent_company_code:
            parent_rows = incoming.get((row.parent_company_code, row.audit_year), [])
            parent_projects = existing_by_entity.get((row.parent_company_code, row.audit_year), [])
            row.parent_company_name = next(
                (item.client_name for item in parent_rows if item.client_name),
                next((project.client_name or "" for project in parent_projects if project.client_name), ""),
            )
        if row.ultimate_company_code:
            if row.ultimate_company_code == row.company_code:
                row.ultimate_company_name = row.client_name
            else:
                ultimate_rows = incoming.get((row.ultimate_company_code, row.audit_year), [])
                ultimate_projects = existing_by_entity.get((row.ultimate_company_code, row.audit_year), [])
                row.ultimate_company_name = next(
                    (item.client_name for item in ultimate_rows if item.client_name),
                    next((project.client_name or "" for project in ultimate_projects if project.client_name), ""),
                )
        row.relation_to_parent = resolve_relation(
            row.relation_to_parent, row.parent_company_code,
            row.client_name, row.company_code,
        )


async def _validate_template_origin(
    db: AsyncSession,
    *,
    loaded: workbook_io.LoadedWorkbook,
    mode: str,
    current_user: Any | None,
    rows: list[workbook_io.ParsedRow],
) -> tuple[Project | None, set[UUID]]:
    """约束当前集团树导出模板只能回导到同一集团与年度。"""
    if loaded.mode is not None and loaded.mode != mode:
        raise HTTPException(status_code=400, detail="模板场景与当前导入入口不匹配，请下载对应模板")
    root_project_id = loaded.root_project_id
    if root_project_id is None:
        return None, set()
    if mode != "consolidation":
        raise HTTPException(status_code=400, detail="只有合并模块可以使用当前集团树导出模板")
    root = await db.get(Project, root_project_id)
    if root is None or root.is_deleted or (root.report_scope or "standalone") != "consolidated":
        raise HTTPException(status_code=400, detail="模板来源集团已变化，请重新从当前集团树导出")
    from app.services.consol_tree_service import build_tree, iter_nodes
    tree = await build_tree(db, root_project_id)
    if tree is None:
        raise HTTPException(status_code=409, detail="模板来源集团树已变化，请重新从当前集团树导出")
    member_ids = {node.project_id for node in iter_nodes(tree) if node.project_id is not None}
    if current_user is not None:
        from app.deps import assert_project_permission
        try:
            await assert_project_permission(db, current_user, root_project_id, "readonly")
        except HTTPException as exc:
            raise HTTPException(status_code=403, detail="无权使用该集团树模板") from exc
    root_year = _project_year(root)
    root_code = (root.company_code or "").strip()
    for row in rows:
        if row.action == "skip":
            continue
        if row.action == "update" and row.project_id not in member_ids:
            raise HTTPException(status_code=400, detail="更新项目不属于模板来源集团，请重新导出当前树")
        if row.audit_year != root_year or row.ultimate_company_code != root_code:
            raise HTTPException(
                status_code=400,
                detail="当前集团树模板只能维护同一最终控制方和审计年度；新建其他集团请下载空白模板",
            )
    return root, member_ids


async def analyze_batch(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    current_user: Any | None = None,
    mode: str = "project",
) -> BatchAnalysis:
    if mode not in ("project", "consolidation"):
        raise HTTPException(status_code=422, detail="批量建项场景无效")
    loaded = await anyio.to_thread.run_sync(workbook_io.load_data_sheet, file_bytes)
    parsed_rows: list[workbook_io.ParsedRow] = []
    row_errors: dict[int, list[str]] = defaultdict(list)
    warnings: list[RowWarning] = []
    for row_number, raw in enumerate(loaded.rows, start=2):
        parsed, errors = workbook_io.parse_row(raw, row_number=row_number)
        parsed_rows.append(parsed)
        row_errors[row_number].extend(errors)
        kind = self_reference_kind(
            parsed.company_code, parsed.parent_company_code, parsed.ultimate_company_code
        )
        if kind is not None:
            warnings.append(RowWarning(row_number=row_number, messages=[_SELF_REFERENCE_ROW_HINTS[kind]]))
    if not parsed_rows:
        row_errors[0].append("数据 sheet 没有可导入的项目，请填写后重新上传")
    if loaded.legacy:
        warnings.append(RowWarning(row_number=0, messages=["当前文件为旧版模板，建议重新下载新版模板"] ))

    duplicate_rows: dict[tuple[str, int | None, str], list[int]] = defaultdict(list)
    for row in parsed_rows:
        if row.action != "skip" and row.company_code:
            duplicate_rows[_key(row)].append(row.row_number)
    for key, numbers in duplicate_rows.items():
        if len(numbers) < 2:
            continue
        rendered = "、".join(str(number) for number in sorted(numbers))
        for number in numbers:
            row_errors[number].append(
                f"企业代码、审计年度和报表类型重复（涉及 Excel 行 {rendered}）"
            )

    all_projects = await _load_year_projects(db, parsed_rows)
    visible_projects, _ = await _visible_projects(db, all_projects, current_user)
    template_root, _template_member_ids = await _validate_template_origin(
        db, loaded=loaded, mode=mode, current_user=current_user, rows=parsed_rows,
    )
    existing_by_key: dict[tuple[str, int | None, str], list[Project]] = defaultdict(list)
    all_by_code_year: dict[tuple[str, int | None], list[Project]] = defaultdict(list)
    visible_by_code_year: dict[tuple[str, int | None], list[Project]] = defaultdict(list)
    for project in all_projects:
        all_by_code_year[((project.company_code or "").strip(), _project_year(project))].append(project)
    for project in visible_projects:
        existing_by_key[_project_key(project)].append(project)
        visible_by_code_year[((project.company_code or "").strip(), _project_year(project))].append(project)
    _prepare_create_group_fields(parsed_rows, visible_by_code_year)

    projects_by_id = {project.id: project for project in all_projects}
    from app.deps import assert_project_permission
    for row in parsed_rows:
        if row.action == "skip":
            continue
        if row.action == "update":
            if mode != "consolidation":
                row_errors[row.row_number].append("只有合并模块导出的模板可以更新集团关系")
                continue
            target = projects_by_id.get(row.project_id)
            if target is None:
                row_errors[row.row_number].append("要更新的项目不存在或无权访问")
                continue
            entity_projects = all_by_code_year.get(((target.company_code or "").strip(), _project_year(target)), [])
            if current_user is not None:
                try:
                    for item in entity_projects:
                        await assert_project_permission(db, current_user, item.id, "edit")
                except HTTPException:
                    row_errors[row.row_number].append("要更新的项目不存在或无权访问")
                    continue
            if _project_key(target) != _key(row):
                row_errors[row.row_number].append("项目ID与企业代码、年度或报表类型不匹配")
            entity_projects = all_by_code_year.get((row.company_code, row.audit_year), [])
            if not row.base_hash:
                row_errors[row.row_number].append("更新集团关系缺少关系基线摘要，请重新导出当前树")
            elif workbook_io.entity_group_fields_hash(entity_projects) != row.base_hash:
                row_errors[row.row_number].append("集团关系在导出后已变化，请重新导出并编辑")
            immutable_changed = (
                row.client_name != (target.client_name or "")
                or row.short_name != (target.short_name or "")
                or row.project_type != (getattr(target.project_type, "value", target.project_type) or None)
                or row.accounting_standard != _accounting_standard(target)
            )
            if immutable_changed:
                row_errors[row.row_number].append("更新集团关系时不能修改客户名称、简称、项目类型或会计准则")
            entity_current_values = {
                (
                    (item.parent_company_code or "").strip(),
                    (item.ultimate_company_code or "").strip(),
                    item.relation_to_parent or None,
                )
                for item in entity_projects
            }
            wanted_values = (
                row.parent_company_code,
                row.ultimate_company_code,
                resolve_relation(
                    row.relation_to_parent, row.parent_company_code,
                    row.client_name, row.company_code,
                ),
            )
            if not row_errors[row.row_number] and entity_current_values == {wanted_values}:
                row.action = "unchanged"
        else:
            # 非管理员只按当前可读项目做预览与冲突分类；不能把“隐藏但存在”作为 dry-run
            # 的差异化信号。执行阶段会以完整库存基线 fail-closed，并使用统一的陈旧计划错误。
            existing = existing_by_key.get(_key(row), [])
            if existing:
                row_errors[row.row_number].append(
                    "该企业、年度和报表类型当前不能新建；如需维护既有集团关系，请从有权限的合并模块导出当前树"
                )
        # 引用未显示的企业不在预校验中暴露存在性；它会在确认执行时由库存 CAS 统一阻断。

    updates_by_entity = {
        (row.company_code, row.audit_year): row
        for row in parsed_rows
        if row.action in ("update", "unchanged") and not row_errors[row.row_number]
    }
    overlay = [
        _clone_project(
            project,
            relationship=updates_by_entity.get(((project.company_code or "").strip(), _project_year(project))),
        )
        for project in visible_projects
    ]
    valid_rows = [
        row for row in parsed_rows
        if row.action in ("create", "update", "unchanged") and not row_errors[row.row_number]
    ]
    for row in (item for item in valid_rows if item.action == "create"):
        overlay.append(SimpleNamespace(
            id=uuid4(), company_code=row.company_code,
            parent_company_code=row.parent_company_code or None,
            ultimate_company_code=row.ultimate_company_code or None,
            relation_to_parent=resolve_relation(
                row.relation_to_parent, row.parent_company_code,
                row.client_name, row.company_code,
            ),
            client_name=row.client_name, report_scope=row.report_scope,
            status=None, audit_period_end=date(row.audit_year, 12, 31) if row.audit_year else None,
            audit_period_start=None, wizard_state=None, name=row.client_name,
            audit_year=row.audit_year, consol_level=1,
        ))

    root_source_rows = [row for row in valid_rows if row.action in ("create", "update")]
    create_rows = [row for row in valid_rows if row.action == "create"]
    root_keys = {
        (row.ultimate_company_code, row.audit_year)
        for row in root_source_rows if row.ultimate_company_code and row.audit_year
    }
    explicit_roots = {
        (row.company_code, row.audit_year)
        for row in create_rows if row.report_scope == "consolidated"
    }
    existing_roots = {
        ((project.company_code or "").strip(), _project_year(project))
        for project in visible_projects if (project.report_scope or "standalone") == "consolidated"
    }
    auto_root_keys = root_keys - explicit_roots - existing_roots
    for code, year in sorted(auto_root_keys):
        source = next(
            (row for row in root_source_rows if row.company_code == code and row.audit_year == year),
            None,
        )
        label = source.client_name if source else f"{code}（自动创建合并项目）"
        overlay.append(SimpleNamespace(
            id=uuid4(), company_code=code, parent_company_code=None,
            ultimate_company_code=code, relation_to_parent=None,
            client_name=label, report_scope="consolidated", status=None,
            audit_period_end=date(year, 12, 31), audit_period_start=None,
            wizard_state=None, name=label, audit_year=year, consol_level=1,
        ))

    tree_preview: list[dict] = []
    incoming = {(row.company_code, row.audit_year) for row in valid_rows} | auto_root_keys
    if incoming:
        try:
            from app.services import consol_tree_service
            forest = consol_tree_service.build_group_trees_from_projects(overlay)
            tree_preview = _filter_preview(forest, incoming)
            _annotate_preview_actions(tree_preview, valid_rows, auto_root_keys)
            flags = _tree_flags(tree_preview)
            blockers = []
            if "cycle_break" in flags:
                blockers.append("最终企业树存在循环引用，请修正上级企业代码")
            if "duplicate_project" in flags:
                blockers.append("最终企业树存在重复项目，请先处理库存重复数据")
            if "relation_conflict" in flags:
                blockers.append("同一企业的单户与合并项目集团关系不一致")
            if blockers:
                row_errors[0].extend(blockers)
        except Exception:
            logger.exception("批量建项最终树预览失败")
            row_errors[0].append("企业树预览失败，已阻止导入，请稍后重试")

    errors = [
        RowError(row_number=number, errors=messages)
        for number, messages in sorted(row_errors.items()) if messages
    ]
    summary = BatchActionSummary(
        create=sum(row.action == "create" for row in valid_rows),
        update=sum(row.action == "update" for row in valid_rows),
        unchanged=sum(row.action == "unchanged" for row in valid_rows),
        skip=sum(row.action == "skip" for row in parsed_rows),
        error=(
            sum(bool(messages) for number, messages in row_errors.items() if number > 0)
            + int(bool(row_errors.get(0)))
        ),
    )
    summary.auto_root = len(auto_root_keys)
    dependencies = build_plan_dependencies(
        valid_rows,
        visible_projects=visible_projects,
        visible_by_code_year=visible_by_code_year,
        tree_preview=tree_preview,
        template_root_project_id=template_root.id if template_root is not None else None,
    )
    response = BatchValidateResponse(
        valid=not errors, total_rows=len(parsed_rows), tree_preview=tree_preview,
        errors=errors, warnings=warnings, summary=summary,
        file_sha256=loaded.file_sha256, template_version=loaded.template_version,
    )
    return BatchAnalysis(
        loaded_sha256=loaded.file_sha256, template_version=loaded.template_version,
        parsed_rows=parsed_rows, response=response, dependencies=dependencies,
    )


async def validate_batch(
    file_bytes: bytes, db: AsyncSession, *, current_user: Any | None = None,
    mode: str = "project",
) -> BatchValidateResponse:
    return (await analyze_batch(file_bytes, db, current_user=current_user, mode=mode)).response


async def _assign_new_project_manager(
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
    if staff_id is None:
        raise HTTPException(status_code=403, detail="项目授权失败：用户未唯一绑定人员")
    project.manager_id = actor.id
    if not persist_assignment:
        return
    from app.services.assignment_service import AssignmentService
    await AssignmentService(db).save_assignments(
        project.id,
        [{"staff_id": staff_id, "role": "manager", "assigned_cycles": None}],
        assigned_by=actor.id,
    )


async def _ensure_consolidated_root(
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
    await _assign_new_project_manager(
        db, project, actor, staff_id,
        persist_assignment=persist_manager_assignment,
    )
    created_by_key[key] = project
    return project, True


async def parse_and_import(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    current_user: Any | None = None,
    mode: str = "project",
) -> BatchImportResult:
    """兼容导入：格式错误行跳过，数据库写按行 SAVEPOINT；回执与落库严格一致。

    新 UI 使用持久计划的整批原子 apply。本入口保留历史部分成功语义，但不再在某行失败时
    rollback 掉此前成功行后继续报假成功。
    """
    analysis = await analyze_batch(
        file_bytes, db, current_user=current_user, mode=mode
    )
    actionable = [row for row in analysis.parsed_rows if row.action != "skip"]
    if not actionable:
        return BatchImportResult(
            success_count=0, fail_count=0,
            skipped_count=analysis.response.summary.skip,
        )
    if any(error.row_number == 0 for error in analysis.response.errors):
        failures = _failure_rows_for_atomic_block(actionable, analysis.response.errors)
        return BatchImportResult(
            success_count=0, fail_count=len(failures), failures=failures,
            skipped_count=analysis.response.summary.skip,
        )

    errors_by_row = {
        error.row_number: list(error.errors)
        for error in analysis.response.errors if error.row_number > 0
    }
    failures = [
        BatchImportFailure(row_number=row.row_number, errors=errors_by_row[row.row_number])
        for row in actionable if row.row_number in errors_by_row
    ]
    for row in actionable:
        if row.action in ("update", "unchanged") and row.row_number not in errors_by_row:
            failures.append(BatchImportFailure(
                row_number=row.row_number,
                errors=["集团关系更新必须先预校验，再使用“确认执行”完成"],
            ))
    candidates = [
        row for row in actionable
        if row.action == "create" and row.row_number not in errors_by_row
    ]
    if not candidates:
        return BatchImportResult(
            success_count=0, fail_count=len(failures), failures=failures,
            skipped_count=analysis.response.summary.skip,
        )

    # 兼容入口同样不允许按旧的可见性快照把新项目接入隐藏或已变化的集团。
    current_inventory, inventory_keys = await load_dependency_inventory(
        db, analysis.dependencies, for_update=True,
    )
    if not inventory_baseline_matches(analysis.dependencies, current_inventory, inventory_keys):
        reason = "当前项目权限或库存已变化，请重新预校验后确认执行"
        failures.extend(
            BatchImportFailure(row_number=row.row_number, errors=[reason]) for row in candidates
        )
        return BatchImportResult(
            success_count=0, fail_count=len(failures), failures=failures,
            skipped_count=analysis.response.summary.skip,
        )
    if current_user is not None:
        from app.deps import assert_project_permission
        try:
            for raw_id in analysis.dependencies.get("read_project_ids", []):
                await assert_project_permission(db, current_user, UUID(str(raw_id)), "readonly")
            for raw_id in analysis.dependencies.get("edit_project_ids", []):
                await assert_project_permission(db, current_user, UUID(str(raw_id)), "edit")
        except (HTTPException, TypeError, ValueError):
            reason = "当前项目权限或库存已变化，请重新预校验后确认执行"
            failures.extend(
                BatchImportFailure(row_number=row.row_number, errors=[reason]) for row in candidates
            )
            return BatchImportResult(
                success_count=0, fail_count=len(failures), failures=failures,
                skipped_count=analysis.response.summary.skip,
            )

    staff_id: UUID | None = None
    if current_user is not None and _role_value(current_user) == "manager":
        from app.services.procedure_authorization import resolve_user_active_staff_id
        staff_id = await resolve_user_active_staff_id(db, current_user.id)

    created_by_key: dict[tuple[str, int, str], Project] = {}
    created: list[Project] = []
    successful_rows: list[workbook_io.ParsedRow] = []
    roots: list[Project] = []
    try:
        from app.models.audit_platform_schemas import BasicInfoSchema
        from app.services.project_wizard_service import create_project
        for row in candidates:
            assert row.audit_year is not None
            try:
                async with db.begin_nested():
                    data = BasicInfoSchema(
                        client_name=row.client_name, audit_year=row.audit_year,
                        project_type=row.project_type, accounting_standard=row.accounting_standard,
                        company_code=row.company_code, short_name=row.short_name,
                        report_scope=row.report_scope,
                        parent_company_code=row.parent_company_code or None,
                        parent_company_name=row.parent_company_name or None,
                        ultimate_company_code=row.ultimate_company_code or None,
                        ultimate_company_name=row.ultimate_company_name or None,
                        relation_to_parent=row.relation_to_parent,
                        manager_id=(
                            current_user.id if current_user is not None
                            and _role_value(current_user) == "manager" else None
                        ),
                    )
                    project = await create_project(
                        data, db, auto_commit=False, propagate_group=False, sync_links=False,
                        uniqueness_checked=True, group_fields_prepared=True,
                    )
                    await _assign_new_project_manager(db, project, current_user, staff_id)
                created.append(project)
                successful_rows.append(row)
                created_by_key[(row.company_code, row.audit_year, row.report_scope)] = project
            except Exception as exc:
                failures.append(BatchImportFailure(
                    row_number=row.row_number, errors=[_public_error(exc)]
                ))

        groups: dict[tuple[str, int], list[workbook_io.ParsedRow]] = defaultdict(list)
        for row in successful_rows:
            if row.ultimate_company_code and row.audit_year is not None:
                groups[(row.ultimate_company_code, row.audit_year)].append(row)
        # 使用预检时锁定的库存快照，避免后出现的根被静默复用。
        prefetched_groups: dict[tuple[str, int], list[Project]] = defaultdict(list)
        for project in current_inventory:
            project_key = _entity_key(project.company_code, _project_year(project))
            if project_key is not None:
                prefetched_groups[project_key].append(project)
        for (ultimate_code, audit_year), rows in sorted(groups.items()):
            root, was_created = await _ensure_consolidated_root(
                db, ultimate_code=ultimate_code, audit_year=audit_year,
                group_rows=rows, created_by_key=created_by_key,
                actor=current_user, staff_id=staff_id,
                existing_projects=prefetched_groups.get((ultimate_code, audit_year), []),
            )
            if was_created:
                roots.append(root)

        if created:
            from app.services.group_links import sync_group_links
            for year in sorted({row.audit_year for row in successful_rows if row.audit_year is not None}):
                await sync_group_links(db, year)
            await db.commit()
    except Exception as exc:
        await db.rollback()
        reason = _public_error(exc)
        all_failures = [
            BatchImportFailure(row_number=row.row_number, errors=[reason])
            for row in candidates
        ] + [failure for failure in failures if failure.row_number in errors_by_row]
        return BatchImportResult(
            success_count=0, fail_count=len(all_failures), failures=all_failures,
            skipped_count=analysis.response.summary.skip,
        )

    project_ids = [str(project.id) for project in created]
    root_ids = [str(project.id) for project in roots]
    return BatchImportResult(
        success_count=len(created), fail_count=len(failures), failures=failures,
        created_count=len(created), auto_root_count=len(roots),
        skipped_count=analysis.response.summary.skip,
        project_ids=project_ids + root_ids, root_project_ids=root_ids,
    )


__all__ = [
    "BatchActionSummary", "BatchImportFailure", "BatchImportResult",
    "BatchValidateResponse", "BatchAnalysis", "RowError", "RowWarning",
    "analyze_batch", "parse_and_import", "validate_batch",
]
