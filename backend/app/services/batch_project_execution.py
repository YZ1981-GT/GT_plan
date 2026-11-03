"""批量建项持久计划、幂等领取和整批原子执行。"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import anyio

from app.models.batch_project_models import ProjectBatchImportPlan
from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_inventory import (
    inventory_baseline_matches,
    load_dependency_inventory,
)
from app.services.batch_project_creator import (
    assign_new_project_creator,
    ensure_consolidated_root,
)
from app.services.batch_project_plan import (
    _tree_flags,
    analyze_batch,
)
from app.services.project_creation_grant_service import (
    ProjectCreationGrantStale,
    revalidate_plan_grants,
)
from app.services.group_topology_lock import lock_topology_years
from app.services.batch_project_types import (
    BatchAnalysis,
    BatchImportResult,
    BatchValidateResponse,
    project_key as _project_key,
    public_error as _public_error,
    project_year as _project_year,
    role_value as _role_value,
    row_key as _key,
)

PLAN_TTL = timedelta(minutes=30)
_PLAN_DEPENDENCIES_KEY = "_plan_dependencies"
_PLAN_FAILURE_ERROR_CODE_KEY = "_plan_failure_error_code"
BATCH_PLAN_STALE_ERROR_CODE = "BATCH_PLAN_STALE"
BATCH_PLAN_RESULT_UNKNOWN_ERROR_CODE = "BATCH_PLAN_RESULT_UNKNOWN"


def _stale_plan_error(message: str = "预校验计划的项目权限或库存已变化，请重新预校验") -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error_code": BATCH_PLAN_STALE_ERROR_CODE, "message": message},
    )


def is_stale_plan_error(error: BaseException) -> bool:
    """判断是否为可通过新幂等键重校验的已知计划陈旧错误。"""
    return (
        isinstance(error, HTTPException)
        and isinstance(error.detail, dict)
        and error.detail.get("error_code") == BATCH_PLAN_STALE_ERROR_CODE
    )


def _public_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    """移除计划执行期私有基线，避免 status/validate 响应暴露库存和权限依赖。"""
    return {
        key: value for key, value in (summary or {}).items()
        if key not in {_PLAN_DEPENDENCIES_KEY, _PLAN_FAILURE_ERROR_CODE_KEY}
    }


def _plan_dependencies(plan: ProjectBatchImportPlan) -> dict[str, Any]:
    dependencies = (plan.summary or {}).get(_PLAN_DEPENDENCIES_KEY)
    if not isinstance(dependencies, dict) or dependencies.get("version") != 1:
        raise _stale_plan_error("预校验计划已过期，请重新上传校验")
    return dependencies


def _dependency_project_ids(dependencies: dict[str, Any], key: str) -> list[UUID]:
    raw_ids = dependencies.get(key)
    if not isinstance(raw_ids, list):
        raise _stale_plan_error("预校验计划权限基线无效，请重新预校验")
    try:
        return sorted({UUID(str(value)) for value in raw_ids}, key=str)
    except (TypeError, ValueError, AttributeError) as exc:
        raise _stale_plan_error("预校验计划权限基线无效，请重新预校验") from exc


async def _assert_plan_project_access(
    db: AsyncSession,
    *,
    plan: ProjectBatchImportPlan,
    actor: Any,
    ids_key: str,
    permission: str,
    conceal: bool = False,
) -> None:
    """按当前成员关系重验计划所依赖项目；状态读取不暴露已失权计划。"""
    from app.deps import assert_project_permission

    try:
        for project_id in _dependency_project_ids(_plan_dependencies(plan), ids_key):
            await assert_project_permission(db, actor, project_id, permission)
    except HTTPException as exc:
        if conceal:
            raise HTTPException(status_code=404, detail="批量建项计划不存在或无权访问") from exc
        raise _stale_plan_error() from exc


async def get_readable_plan(
    db: AsyncSession,
    plan_id: UUID,
    actor: Any,
    *,
    for_update: bool = False,
) -> ProjectBatchImportPlan:
    """读取计划前按当前权限重验其已展示的项目，并可等待正在 apply 的行锁。"""
    plan = await get_owned_plan(db, plan_id, actor, for_update=for_update)
    await _assert_plan_project_access(
        db, plan=plan, actor=actor, ids_key="read_project_ids",
        permission="readonly", conceal=True,
    )
    return plan


async def _lock_plan_memberships(
    db: AsyncSession,
    *,
    dependencies: dict[str, Any],
    actor: Any,
) -> None:
    """在执行事务内冻结 actor 与当前成员行，使撤权和批量写入形成明确先后。"""
    project_ids = sorted(
        set(_dependency_project_ids(dependencies, "read_project_ids"))
        | set(_dependency_project_ids(dependencies, "edit_project_ids")),
        key=str,
    )
    from app.services.project_creation_grant_service import (
        lock_actor_and_project_memberships,
    )

    await lock_actor_and_project_memberships(db, actor, project_ids)


async def _assert_template_root_scope(
    db: AsyncSession,
    *,
    dependencies: dict[str, Any],
    rows: list[workbook_io.ParsedRow],
) -> None:
    """执行前再确认当前集团树导出模板没有被改造成跨集团更新入口。"""
    raw_root_id = dependencies.get("template_root_project_id")
    if raw_root_id in (None, ""):
        return
    try:
        root_project_id = UUID(str(raw_root_id))
    except (TypeError, ValueError) as exc:
        raise _stale_plan_error("预校验计划的集团来源已变化，请重新预校验") from exc
    # 上一步逐项目权限检查会把 RLS 指向末个项目；这里恢复为已经验证可编辑的来源根。
    from app.core.database import set_rls_context
    await set_rls_context(db, root_project_id)
    root = await db.get(Project, root_project_id)
    if root is None or root.is_deleted or (root.report_scope or "standalone") != "consolidated":
        raise _stale_plan_error("预校验计划的集团来源已变化，请重新预校验")
    from app.services.consol_tree_service import build_tree, iter_nodes
    tree = await build_tree(db, root_project_id)
    if tree is None:
        raise _stale_plan_error("预校验计划的集团来源已变化，请重新预校验")
    member_ids = {node.project_id for node in iter_nodes(tree) if node.project_id is not None}
    root_code = (root.company_code or "").strip()
    for row in rows:
        if row.action == "skip":
            continue
        if (
            row.audit_year != _project_year(root)
            or row.ultimate_company_code != root_code
            or (row.action == "update" and row.project_id not in member_ids)
        ):
            raise _stale_plan_error("预校验计划的集团来源已变化，请重新预校验")


class BatchApplyRequest(BaseModel):
    validation_id: UUID
    idempotency_key: str


class BatchPlanStatusResponse(BaseModel):
    validation_id: UUID
    mode: str
    status: str
    valid: bool
    total_rows: int
    errors: list[dict]
    summary: dict[str, Any]
    tree_preview: list[dict]
    warnings: list[dict]
    template_version: str | None = None
    receipt: dict[str, Any] | None = None
    public_error: str | None = None
    failure_error_code: str | None = None
    expires_at: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _canonical_payload(
    mode: str,
    rows: list[workbook_io.ParsedRow],
    *,
    template_root_project_id: str | None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "template_root_project_id": template_root_project_id,
        "rows": [row.model_dump(mode="json") for row in rows],
    }


def _request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rows_with_errors(analysis: BatchAnalysis) -> list[dict[str, Any]]:
    errors = {
        item.row_number: list(item.errors) for item in analysis.response.errors
        if item.row_number > 0
    }
    return [
        {"row": row.model_dump(mode="json"), "errors": errors.get(row.row_number, [])}
        for row in analysis.parsed_rows
    ]


def _analysis_summary(analysis: BatchAnalysis) -> dict[str, Any]:
    summary = analysis.response.summary.model_dump(mode="json")
    summary["global_errors"] = [
        message for error in analysis.response.errors if error.row_number == 0
        for message in error.errors
    ]
    summary[_PLAN_DEPENDENCIES_KEY] = analysis.dependencies
    return summary


def _validation_response(plan: ProjectBatchImportPlan) -> BatchValidateResponse:
    error_items = [
        {"row_number": item["row"].get("row_number", 0), "errors": item.get("errors") or []}
        for item in plan.rows if item.get("errors")
    ]
    global_errors = list((plan.summary or {}).get("global_errors") or [])
    if global_errors:
        error_items.insert(0, {"row_number": 0, "errors": global_errors})
    expired = plan.status == "validated" and _aware(plan.expires_at) <= _now()
    if expired:
        error_items.insert(0, {"row_number": 0, "errors": ["预校验结果已过期，请重新上传校验"]})
    response = BatchValidateResponse(
        valid=plan.status == "validated" and not expired,
        total_rows=len(plan.rows),
        tree_preview=list(plan.tree_preview or []),
        errors=error_items,
        warnings=list(plan.warnings or []),
        summary=_public_summary(plan.summary),
        file_sha256=plan.file_sha256,
        template_version=plan.template_version,
        validation_id=plan.id,
        expires_at=plan.expires_at.isoformat(),
    )
    return response

async def create_validation_plan(
    file_bytes: bytes,
    db: AsyncSession,
    *,
    actor: Any,
    file_name: str,
    mode: str,
    idempotency_key: str | None,
) -> tuple[ProjectBatchImportPlan, BatchValidateResponse, bool]:
    """解析一次并持久化计划；同键同摘要返回原计划。只 flush，由路由 commit。"""
    key = (idempotency_key or str(uuid4())).strip()
    if not 8 <= len(key) <= 64:
        raise HTTPException(status_code=422, detail="幂等键长度必须为 8-64 个字符")
    analysis = await analyze_batch(
        file_bytes, db, current_user=actor, mode=mode
    )
    payload = _canonical_payload(
        mode, analysis.parsed_rows,
        template_root_project_id=analysis.dependencies.get("template_root_project_id"),
    )
    digest = _request_hash(payload)
    existing = (await db.execute(sa.select(ProjectBatchImportPlan).where(
        ProjectBatchImportPlan.actor_user_id == actor.id,
        ProjectBatchImportPlan.idempotency_key == key,
    ).with_for_update())).scalar_one_or_none()
    if existing is not None:
        if existing.request_hash != digest:
            raise HTTPException(status_code=409, detail="同一幂等键对应的导入内容不同")
        if (
            existing.status in ("validated", "invalid")
            and _aware(existing.expires_at) <= _now()
        ):
            existing.status = "validated" if analysis.response.valid else "invalid"
            existing.file_name = (file_name or "建项模板.xlsx")[:500]
            existing.file_sha256 = analysis.loaded_sha256
            existing.template_version = analysis.template_version
            existing.rows = _rows_with_errors(analysis)
            existing.tree_preview = analysis.response.tree_preview
            existing.summary = _analysis_summary(analysis)
            existing.warnings = [
                warning.model_dump(mode="json") for warning in analysis.response.warnings
            ]
            existing.receipt = None
            existing.public_error = None
            existing.expires_at = _now() + PLAN_TTL
            existing.updated_at = _now()
            await db.flush()
        return existing, _validation_response(existing), True

    summary = _analysis_summary(analysis)
    plan = ProjectBatchImportPlan(
        actor_user_id=actor.id,
        mode=mode,
        status="validated" if analysis.response.valid else "invalid",
        file_name=(file_name or "建项模板.xlsx")[:500],
        file_sha256=analysis.loaded_sha256,
        template_version=analysis.template_version,
        request_hash=digest,
        idempotency_key=key,
        rows=_rows_with_errors(analysis),
        tree_preview=analysis.response.tree_preview,
        summary=summary,
        warnings=[warning.model_dump(mode="json") for warning in analysis.response.warnings],
        expires_at=_now() + PLAN_TTL,
    )
    try:
        async with db.begin_nested():
            db.add(plan)
            await db.flush()
    except IntegrityError:
        # 两个 worker 同时校验同一客户端幂等键：唯一索引串行后重读胜者。
        existing = (await db.execute(sa.select(ProjectBatchImportPlan).where(
            ProjectBatchImportPlan.actor_user_id == actor.id,
            ProjectBatchImportPlan.idempotency_key == key,
        ))).scalar_one_or_none()
        if existing is None:
            raise
        if existing.request_hash != digest:
            raise HTTPException(status_code=409, detail="同一幂等键对应的导入内容不同")
        return existing, _validation_response(existing), True
    return plan, _validation_response(plan), False


async def get_owned_plan(
    db: AsyncSession,
    plan_id: UUID,
    actor: Any,
    *,
    for_update: bool = False,
) -> ProjectBatchImportPlan:
    stmt = sa.select(ProjectBatchImportPlan).where(
        ProjectBatchImportPlan.id == plan_id,
        ProjectBatchImportPlan.actor_user_id == actor.id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="批量建项计划不存在或无权访问")
    return plan


def plan_status_response(plan: ProjectBatchImportPlan) -> BatchPlanStatusResponse:
    status = plan.status
    if status == "validated" and _aware(plan.expires_at) <= _now():
        status = "expired"
    validation = _validation_response(plan)
    return BatchPlanStatusResponse(
        validation_id=plan.id,
        mode=plan.mode,
        status=status,
        valid=status == "validated",
        total_rows=validation.total_rows,
        errors=[item.model_dump(mode="json") for item in validation.errors],
        summary=_public_summary(plan.summary),
        tree_preview=list(plan.tree_preview or []),
        warnings=list(plan.warnings or []),
        template_version=plan.template_version,
        receipt=plan.receipt,
        public_error=plan.public_error,
        failure_error_code=(plan.summary or {}).get(_PLAN_FAILURE_ERROR_CODE_KEY),
        expires_at=plan.expires_at.isoformat(),
    )


def _plan_rows(plan: ProjectBatchImportPlan) -> list[workbook_io.ParsedRow]:
    return [
        workbook_io.ParsedRow.model_validate(item["row"])
        for item in plan.rows if not item.get("errors")
    ]

async def _write_relationship_audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    project_id: UUID,
    before: dict[str, Any],
    after: dict[str, Any],
    synced_ids: list[str],
) -> None:
    try:
        async with db.begin_nested():
            await db.execute(sa.text(
                "INSERT INTO app_audit_log "
                "(id, user_id, action, resource_type, resource_id, details, created_at) "
                "VALUES (gen_random_uuid(), :uid, 'project.group_relationship.batch_change', "
                "'project', :pid, CAST(:details AS jsonb), :created_at)"
            ), {
                "uid": str(actor_id), "pid": str(project_id),
                "details": json.dumps({
                    "before": before, "after": after, "synced": synced_ids,
                }, ensure_ascii=False),
                "created_at": _now(),
            })
    except Exception:
        # SQLite 没有 app_audit_log/gen_random_uuid；PG 审计增强失败不污染主事务。
        return


async def apply_validation_plan(
    db: AsyncSession,
    *,
    plan_id: UUID,
    actor: Any,
    idempotency_key: str,
) -> BatchImportResult:
    """锁定并执行已验证计划。只 flush；调用方统一 commit。"""
    plan = await get_owned_plan(db, plan_id, actor, for_update=True)
    if plan.idempotency_key != idempotency_key:
        raise HTTPException(status_code=409, detail="幂等键与预校验计划不匹配")
    dependencies = _plan_dependencies(plan)
    # 所有状态（含 invalid/failed/applied 回执）先按当前权限过滤，不能让终态绕过撤权。
    await _assert_plan_project_access(
        db, plan=plan, actor=actor, ids_key="read_project_ids", permission="readonly",
    )
    if plan.status == "applied" and plan.receipt is not None:
        receipt = BatchImportResult.model_validate(plan.receipt)
        receipt.idempotent = True
        return receipt
    if _aware(plan.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="预校验结果已过期，请重新上传校验")
    if plan.status == "invalid":
        raise HTTPException(status_code=409, detail="预校验未通过，不能执行导入")
    if plan.status == "applying":
        raise HTTPException(status_code=409, detail="该批量建项计划正在执行")
    if plan.status == "failed":
        raise HTTPException(status_code=409, detail=plan.public_error or "该计划执行失败，请重新预校验")
    if plan.status != "validated":
        raise HTTPException(status_code=409, detail="批量建项计划状态不允许执行")

    rows = _plan_rows(plan)
    create_rows = [row for row in rows if row.action == "create"]
    update_rows = [row for row in rows if row.action == "update"]
    unchanged_rows = [row for row in rows if row.action == "unchanged"]
    skipped_rows = [row for row in rows if row.action == "skip"]
    # 集团边界可动态跨组。先按年度事务级 advisory lock 串行，再以当前时间冻结
    # actor/grant；否则等待期间到期或撤销的授权仍可能进入写路径。
    lock_years = {row.audit_year for row in rows}
    await lock_topology_years(db, lock_years)
    try:
        await revalidate_plan_grants(db, actor, create_rows, dependencies)
    except ProjectCreationGrantStale as exc:
        raise _stale_plan_error("预校验计划的建项授权已变化，请重新预校验") from exc
    if update_rows and (
        plan.mode != "consolidation"
        or dependencies.get("template_root_project_id") in (None, "")
    ):
        raise _stale_plan_error("更新集团关系必须使用从当前合并项目导出的完整模板")
    # 连“无变化”行也纳入最终图校验，避免双口径冲突在无写入路径中漏检。
    plan_years = {row.audit_year for row in rows if row.audit_year is not None}
    write_years = {
        row.audit_year for row in create_rows + update_rows if row.audit_year is not None
    }
    # 年度、actor/grant 之后先冻结成员行并重验权限，再进入可能等待的库存行锁。
    try:
        await _lock_plan_memberships(db, dependencies=dependencies, actor=actor)
    except ProjectCreationGrantStale as exc:
        raise _stale_plan_error("预校验计划的创建者状态已变化，请重新预校验") from exc
    await _assert_plan_project_access(
        db, plan=plan, actor=actor, ids_key="read_project_ids", permission="readonly",
    )
    await _assert_plan_project_access(
        db, plan=plan, actor=actor, ids_key="edit_project_ids", permission="edit",
    )
    try:
        current_inventory, inventory_keys = await load_dependency_inventory(
            db, dependencies, for_update=True,
        )
    except HTTPException as exc:
        raise _stale_plan_error("预校验计划库存基线无效，请重新预校验") from exc
    if not inventory_baseline_matches(dependencies, current_inventory, inventory_keys):
        raise _stale_plan_error()
    await _assert_template_root_scope(db, dependencies=dependencies, rows=rows)

    plan.status = "applying"
    plan.updated_at = _now()
    await db.flush()

    staff_id: UUID | None = None
    if _role_value(actor) == "manager":
        from app.services.procedure_authorization import resolve_user_active_staff_id_optional
        staff_id = await resolve_user_active_staff_id_optional(db, actor.id)

    defer_project_flush = True
    created: list[Project] = []
    roots: list[Project] = []
    updated_ids: set[UUID] = set()
    created_by_key: dict[tuple[str, int, str], Project] = {}
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project
    for row in create_rows:
        assert row.audit_year is not None
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
            manager_id=actor.id if _role_value(actor) == "manager" else None,
        )
        project = await create_project(
            data, db, auto_commit=False, propagate_group=False, sync_links=False,
            uniqueness_checked=True, group_fields_prepared=True,
            defer_flush=defer_project_flush,
        )
        await assign_new_project_creator(
            db, project, actor, staff_id, persist_assignment=False
        )
        created.append(project)
        created_by_key[(row.company_code, row.audit_year, row.report_scope)] = project

    groups: dict[tuple[str, int], list[workbook_io.ParsedRow]] = {}
    for row in create_rows + update_rows:
        if row.ultimate_company_code and row.audit_year is not None:
            groups.setdefault((row.ultimate_company_code, row.audit_year), []).append(row)
    # 复用已 CAS 的库存快照，不能在创建后重新查询并静默采用确认后才出现的合并根。
    prefetched_groups: dict[tuple[str, int], list[Project]] = {}
    for project in current_inventory:
        project_year = project.audit_year
        project_code = (project.company_code or "").strip()
        if project_year is None or not project_code:
            continue
        prefetched_groups.setdefault((project_code, project_year), []).append(project)
    for (ultimate_code, audit_year), group_rows in sorted(groups.items()):
        root, was_created = await ensure_consolidated_root(
            db, ultimate_code=ultimate_code, audit_year=audit_year,
            group_rows=group_rows, created_by_key=created_by_key,
            actor=actor, staff_id=staff_id,
            existing_projects=prefetched_groups.get((ultimate_code, audit_year), []),
            defer_flush=defer_project_flush,
            persist_manager_assignment=False,
        )
        if was_created:
            roots.append(root)
    actor_role = _role_value(actor)
    if actor_role == "manager" and (created or roots):
        from app.services.assignment_service import AssignmentService
        if staff_id is None:
            # 未绑定人员档案：只加项目成员（经理、编辑），不写团队委派（R7）。
            await AssignmentService(db).initialize_creator_members(
                [project.id for project in created + roots],
                user_id=actor.id, assigned_by=actor.id, role_key="manager",
            )
        else:
            await AssignmentService(db).initialize_project_managers(
                [project.id for project in created + roots],
                staff_id=staff_id, user_id=actor.id, assigned_by=actor.id,
            )
    elif actor_role == "partner" and (created or roots):
        from app.services.assignment_service import AssignmentService
        await AssignmentService(db).initialize_project_partners(
            [project.id for project in created + roots],
            user_id=actor.id, assigned_by=actor.id,
        )
    if defer_project_flush and (created or roots):
        await db.flush()

    from app.deps import assert_project_permission
    from app.services.group_links import find_counterpart, update_group_relationship
    for row in update_rows:
        assert row.project_id is not None
        target = (await db.execute(sa.select(Project).where(
            Project.id == row.project_id, Project.is_deleted == sa.false(),
        ).with_for_update())).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=409, detail="要更新的项目已不存在，请重新预校验")
        if _project_key(target) != _key(row):
            raise HTTPException(status_code=409, detail="项目身份在预校验后已变化")
        entity_projects = list((await db.execute(sa.select(Project).where(
            Project.company_code == target.company_code,
            Project.audit_year == target.audit_year,
            Project.is_deleted == sa.false(),
        ).with_for_update())).scalars().all())
        if workbook_io.entity_group_fields_hash(entity_projects) != row.base_hash:
            raise HTTPException(status_code=409, detail="集团关系在预校验后已变化，请重新预校验")
        for entity_project in entity_projects:
            await assert_project_permission(db, actor, entity_project.id, "edit")
        counterpart = await find_counterpart(
            db, project_id=target.id, company_code=target.company_code,
            audit_year=target.audit_year, report_scope=target.report_scope,
        )
        if counterpart is not None:
            await assert_project_permission(db, actor, counterpart.id, "edit")
        before_values = {
            "parent_company_code": target.parent_company_code,
            "ultimate_company_code": target.ultimate_company_code,
            "relation_to_parent": target.relation_to_parent,
        }
        result = await update_group_relationship(
            db, target,
            parent_company_code=row.parent_company_code or None,
            ultimate_company_code=row.ultimate_company_code or None,
            relation_to_parent=row.relation_to_parent,
            sync_links=False,
            validate_cycle=False,
        )
        target.updated_by = actor.id
        synced_ids = [item["id"] for item in result["synced"]]
        updated_ids.update(UUID(item_id) for item_id in synced_ids)
        await _write_relationship_audit(
            db, actor_id=actor.id, project_id=target.id,
            before=before_values,
            after={
                "parent_company_code": target.parent_company_code,
                "ultimate_company_code": target.ultimate_company_code,
                "relation_to_parent": target.relation_to_parent,
            },
            synced_ids=synced_ids,
        )

    if plan_years:
        await db.flush()
        from app.services.group_forest import build_forest
        for year in sorted(plan_years):
            final_projects = list((await db.execute(sa.select(Project).where(
                Project.audit_year == year,
                Project.is_deleted == sa.false(),
            ))).scalars().all())
            flags = _tree_flags(list(build_forest(final_projects, year=year).get("trees") or []))
            if "cycle_break" in flags:
                raise HTTPException(status_code=409, detail="执行后的企业树会形成循环引用，已全部回滚")
            if "relation_conflict" in flags:
                raise HTTPException(status_code=409, detail="执行后的单户与合并项目集团关系不一致，已全部回滚")

    from app.services.group_links import sync_group_links
    for year in sorted(write_years):
        await sync_group_links(db, year)

    explicit_roots = [
        project for project in created if (project.report_scope or "standalone") == "consolidated"
    ]
    root_ids = list(dict.fromkeys(str(project.id) for project in explicit_roots + roots))
    project_ids = list(dict.fromkeys(
        [str(project.id) for project in created + roots]
        + [str(project_id) for project_id in sorted(updated_ids, key=str)]
    ))
    result = BatchImportResult(
        success_count=len(created) + len(update_rows), fail_count=0,
        created_count=len(created), updated_count=len(update_rows),
        unchanged_count=len(unchanged_rows), skipped_count=len(skipped_rows),
        auto_root_count=len(roots), project_ids=project_ids,
        root_project_ids=root_ids,
    )
    # JSONB 原地改动不会触发 ORM UPDATE；复制后把新建/更新项目纳入后续 status 的当前可读校验。
    stored_dependencies = copy.deepcopy(dependencies)
    stored_dependencies["read_project_ids"] = sorted(
        {str(value) for value in stored_dependencies.get("read_project_ids", [])}
        | set(project_ids)
    )
    stored_summary = copy.deepcopy(plan.summary or {})
    stored_summary[_PLAN_DEPENDENCIES_KEY] = stored_dependencies
    plan.summary = stored_summary
    plan.status = "applied"
    plan.receipt = result.model_dump(mode="json")
    plan.public_error = None
    plan.applied_at = _now()
    plan.updated_at = _now()
    await db.flush()
    return result


async def mark_plan_failed(
    db: AsyncSession,
    *,
    plan_id: UUID,
    actor: Any,
    error: BaseException,
) -> None:
    plan = await get_owned_plan(db, plan_id, actor, for_update=True)
    if plan.status == "applied":
        return
    summary = copy.deepcopy(plan.summary or {})
    if isinstance(error, IntegrityError) or is_stale_plan_error(error):
        summary[_PLAN_FAILURE_ERROR_CODE_KEY] = BATCH_PLAN_STALE_ERROR_CODE
    else:
        summary.pop(_PLAN_FAILURE_ERROR_CODE_KEY, None)
    plan.summary = summary
    plan.status = "failed"
    plan.public_error = _public_error(error)
    plan.updated_at = _now()
    await db.flush()


async def build_plan_error_workbook(
    db: AsyncSession, *, plan_id: UUID, actor: Any,
):
    plan = await get_readable_plan(db, plan_id, actor, for_update=True)
    rows = [
        (workbook_io.ParsedRow.model_validate(item["row"]), list(item.get("errors") or []))
        for item in plan.rows if item.get("errors")
    ]
    global_errors = list((plan.summary or {}).get("global_errors") or [])
    return await anyio.to_thread.run_sync(
        lambda: workbook_io.generate_error_workbook(rows, global_errors=global_errors)
    )


__all__ = [
    "BATCH_PLAN_RESULT_UNKNOWN_ERROR_CODE", "BATCH_PLAN_STALE_ERROR_CODE",
    "BatchApplyRequest", "BatchPlanStatusResponse", "apply_validation_plan",
    "build_plan_error_workbook", "create_validation_plan", "get_owned_plan", "get_readable_plan",
    "is_stale_plan_error", "mark_plan_failed", "plan_status_response",
]
