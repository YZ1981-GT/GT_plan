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
from app.services.batch_project_inventory import (
    build_plan_dependencies,
    entity_key as _entity_key,
    inventory_baseline_matches,
    load_dependency_inventory,
)
from app.services.batch_project_creator import (
    assign_new_project_creator,
    ensure_consolidated_root,
)
from app.services.batch_project_template_origin import validate_template_origin
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
from app.services.project_creation_grant_service import (
    ProjectCreationGrantStale,
    authorize_creation_codes,
    required_creation_codes,
    revalidate_plan_grants,
)

logger = logging.getLogger(__name__)


_SELF_REFERENCE_ROW_HINTS = {
    SELF_TOP: "上级企业代码与本企业代码相同，将按「本企业就是上级企业」处理（集团顶层企业，不另建上级节点）",
    SELF_ULTIMATE: "三个代码相同，将按「本企业即为最终控制方（集团总部或母公司）」处理",
}


async def _load_year_projects(
    db: AsyncSession,
    rows: list[workbook_io.ParsedRow],
    *,
    current_user: Any | None = None,
    permitted_codes: set[str] | None = None,
) -> list[Project]:
    years = sorted({row.audit_year for row in rows if row.audit_year is not None})
    ids = sorted({row.project_id for row in rows if row.project_id is not None}, key=str)
    if not years and not ids:
        return []
    predicates = []
    role = _role_value(current_user)
    if years:
        year_predicate = Project.audit_year.in_(years)
        if role == "manager":
            # manager 只可读取本人已有项目和已通过精确 grant 的代码；不扫描同年度无关隐藏项目。
            from app.deps import readable_project_ids

            readable = await readable_project_ids(db, current_user)
            allowed_ids = sorted(set(readable or set()) | set(ids), key=str)
            scopes = [Project.id.in_(allowed_ids)]
            if permitted_codes:
                scopes.append(Project.company_code.in_(sorted(permitted_codes)))
            year_predicate = sa.and_(year_predicate, sa.or_(*scopes))
        predicates.append(year_predicate)
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


async def analyze_batch(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    current_user: Any | None = None,
    mode: str = "project",
    authorization_entrypoint: str = "batch_validate",
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
    # 更新关系是“当前集团树导出”协议专属能力：缺失或清空元数据不能降级为通用模板。
    for row in parsed_rows:
        if row.action == "update" and (
            loaded.mode != "consolidation" or loaded.root_project_id is None
        ):
            row_errors[row.row_number].append(
                "更新集团关系必须使用从当前合并项目导出的完整模板"
            )

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

    authorization_rows = [
        row for row in parsed_rows if not row_errors[row.row_number]
    ]
    # 第一阶段只按文件显式代码授权，必须先于任何项目库存读取。
    await authorize_creation_codes(
        db,
        current_user,
        required_creation_codes(authorization_rows),
        entrypoint=authorization_entrypoint,
    )
    template_root, _template_member_ids = await validate_template_origin(
        db, loaded=loaded, mode=mode, current_user=current_user, rows=parsed_rows,
    )
    permitted_codes = {
        str(code).strip().upper()
        for row in authorization_rows
        for code in (row.company_code, row.parent_company_code, row.ultimate_company_code)
        if code
    }
    # 授权/模板项目权限必须先于库存读取；manager 只查本人项目与本次已授权精确代码。
    all_projects = await _load_year_projects(
        db, parsed_rows, current_user=current_user, permitted_codes=permitted_codes,
    )
    while True:
        visible_projects, _ = await _visible_projects(db, all_projects, current_user)
        existing_by_key: dict[tuple[str, int | None, str], list[Project]] = defaultdict(list)
        all_by_code_year: dict[tuple[str, int | None], list[Project]] = defaultdict(list)
        visible_by_code_year: dict[tuple[str, int | None], list[Project]] = defaultdict(list)
        visible_ids = {project.id for project in visible_projects}
        for project in all_projects:
            existing_by_key[_project_key(project)].append(project)
            all_by_code_year[((project.company_code or "").strip(), _project_year(project))].append(project)
        for project in visible_projects:
            visible_by_code_year[((project.company_code or "").strip(), _project_year(project))].append(project)
        _prepare_create_group_fields(parsed_rows, visible_by_code_year)
        # 库存补齐可能新增 parent/ultimate。每轮先授权新增代码，才允许把它加入下一次
        # 库存查询；最终计划快照因此与持久行严格同域。
        final_permitted_codes = required_creation_codes(authorization_rows)
        creation_grants = await authorize_creation_codes(
            db,
            current_user,
            final_permitted_codes,
            entrypoint=f"{authorization_entrypoint}_final",
        )
        if final_permitted_codes.issubset(permitted_codes):
            break
        permitted_codes |= final_permitted_codes
        all_projects = await _load_year_projects(
            db, parsed_rows, current_user=current_user, permitted_codes=permitted_codes,
        )

    projects_by_id = {project.id: project for project in all_projects}
    from app.deps import assert_project_permission
    for row in parsed_rows:
        if row.action == "skip":
            continue
        if row_errors[row.row_number]:
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
            entity_projects = all_by_code_year.get((row.company_code, row.audit_year), [])
            hidden_entity = [project for project in entity_projects if project.id not in visible_ids]
            if hidden_entity:
                row_errors[row.row_number].append(
                    "该企业已有您无权维护的项目，请联系管理员或项目负责人处理"
                )
                continue
            inaccessible_reference = False
            for code in (row.parent_company_code, row.ultimate_company_code):
                if not code:
                    continue
                matches = all_by_code_year.get((code, row.audit_year), [])
                if any(project.id not in visible_ids for project in matches):
                    inaccessible_reference = True
                    break
            if inaccessible_reference:
                row_errors[row.row_number].append(
                    "上级企业或最终控制方已有您无权维护的项目，请联系项目负责人处理"
                )
                continue
            existing = existing_by_key.get(_key(row), [])
            if existing:
                row_errors[row.row_number].append(
                    "该企业、年度和报表类型当前不能新建；如需维护既有集团关系，请从有权限的合并模块导出当前树"
                )

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
        parsed_rows,
        visible_projects=visible_projects,
        visible_by_code_year=visible_by_code_year,
        tree_preview=tree_preview,
        template_root_project_id=template_root.id if template_root is not None else None,
    )
    dependencies["creation_grants"] = creation_grants
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
    mode: str = "project", authorization_entrypoint: str = "batch_validate",
) -> BatchValidateResponse:
    return (await analyze_batch(
        file_bytes, db, current_user=current_user, mode=mode,
        authorization_entrypoint=authorization_entrypoint,
    )).response


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
        file_bytes, db, current_user=current_user, mode=mode,
        authorization_entrypoint="batch_import",
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

    # 兼容入口同样先锁年度，再按当前时间冻结 actor/grant；等待不能把已过期授权带入写路径。
    from app.services.group_topology_lock import lock_topology_years

    await lock_topology_years(db, [row.audit_year for row in candidates])
    try:
        await revalidate_plan_grants(
            db, current_user, candidates, analysis.dependencies,
        )
    except ProjectCreationGrantStale:
        reason = "当前建项授权已变化，请重新预校验"
        failures.extend(
            BatchImportFailure(row_number=row.row_number, errors=[reason]) for row in candidates
        )
        return BatchImportResult(
            success_count=0, fail_count=len(failures), failures=failures,
            skipped_count=analysis.response.summary.skip,
        )
    if current_user is not None:
        from app.deps import assert_project_permission
        from app.services.project_creation_grant_service import (
            lock_actor_and_project_memberships,
        )

        read_ids = [UUID(str(raw)) for raw in analysis.dependencies.get("read_project_ids", [])]
        edit_ids = [UUID(str(raw)) for raw in analysis.dependencies.get("edit_project_ids", [])]
        try:
            await lock_actor_and_project_memberships(
                db, current_user, set(read_ids) | set(edit_ids),
            )
            for project_id in read_ids:
                await assert_project_permission(db, current_user, project_id, "readonly")
            for project_id in edit_ids:
                await assert_project_permission(db, current_user, project_id, "edit")
        except (HTTPException, ProjectCreationGrantStale, TypeError, ValueError):
            reason = "当前项目权限或库存已变化，请重新预校验后确认执行"
            failures.extend(
                BatchImportFailure(row_number=row.row_number, errors=[reason]) for row in candidates
            )
            return BatchImportResult(
                success_count=0, fail_count=len(failures), failures=failures,
                skipped_count=analysis.response.summary.skip,
            )

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

    staff_id: UUID | None = None
    if current_user is not None and _role_value(current_user) == "manager":
        from app.services.procedure_authorization import resolve_user_active_staff_id_optional
        # 未绑定人员档案时为 None：创建者只加项目成员、不写团队委派（R7）。
        staff_id = await resolve_user_active_staff_id_optional(db, current_user.id)

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
                    await assign_new_project_creator(db, project, current_user, staff_id)
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
            root, was_created = await ensure_consolidated_root(
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
