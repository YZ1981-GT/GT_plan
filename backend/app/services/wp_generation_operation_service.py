"""持久 operation 驱动的底稿两阶段生成。

service 只 flush，不 commit；路由编排 Phase A commit、锁外物化、Phase B commit。正常请求同步完成，
响应丢失或进程重启后可用同一 operation id 重入并返回保存的原回执。
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_generation_models import (
    ACTIVE_OPERATION_STATUSES,
    WorkpaperGenerationItem,
    WorkpaperGenerationOperation,
)
from app.services.procedure_scope_retention import (
    GenerationPlan,
    plan_generation,
    scope_decision_revision,
)
from app.services.wp_generation_descriptors import (
    GenerationDescriptor,
    prepare_code_descriptors,
    prepare_template_set_descriptors,
)
from app.services.wp_generation_receipt import GenerationReceipt, failure_text
from app.services.wp_generation_staging import (
    MaterializedItem,
    SourceSnapshot,
    StagingItem,
)

TERMINAL_STATUSES = frozenset({"succeeded", "partial_failed", "failed", "stale"})
LEASE_SECONDS = 300
logger = logging.getLogger(__name__)


class OperationConflict(ValueError):
    pass


@dataclass(frozen=True)
class PrepareResult:
    operation_id: UUID
    status: str
    action: Literal["created", "resume", "active", "terminal"]
    receipt: dict[str, Any] | None = None


@dataclass(frozen=True)
class ClaimResult:
    operation_id: UUID
    status: str
    lease_token: UUID | None
    active: bool


@dataclass(frozen=True)
class MaterializationSnapshot:
    operation_id: UUID
    project_id: UUID
    kind: str
    failure_policy: str
    scenario: str
    has_foreign_currency: bool
    lease_token: UUID
    items: tuple[StagingItem, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def canonical_request(
    *,
    kind: str,
    project_id: UUID,
    year: int,
    template_set_id: UUID | None,
    codes: list[str] | None,
) -> dict[str, Any]:
    normalized_codes = sorted({str(code).strip().upper() for code in (codes or []) if str(code).strip()})
    return {
        "kind": kind,
        "project_id": str(project_id),
        "year": int(year),
        "template_set_id": str(template_set_id) if template_set_id else None,
        "codes": normalized_codes,
        # None 与 [] 语义不同：模板集 None=整套，[]=一个不生成。
        "codes_provided": codes is not None,
    }


def request_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def public_failure_text(error: BaseException | str) -> str:
    """给 operation/回执的安全错误；完整异常只进服务日志。"""
    text = failure_text(error)
    safe_prefixes = (
        "模板来源已变化", "模板物化期间来源发生变化", "staging 文件缺失或摘要不符",
        "正式文件已存在且摘要冲突", "表头 staging 尚未准备完成",
    )
    if text.startswith(safe_prefixes):
        return text
    return "底稿文件准备失败，请重试；若持续失败请联系管理员"


def _receipt_with_compat(receipt: GenerationReceipt, kind: str) -> dict[str, Any]:
    payload = receipt.to_payload()
    if kind == "template_set":
        payload["count"] = payload["created"]
    else:
        payload["skipped"] = len(payload["existing_codes"])
        payload["skipped_codes"] = list(payload["existing_codes"])
    return payload


def operation_payload(operation: WorkpaperGenerationOperation) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation_id": str(operation.id),
        "status": operation.status,
        "progress_total": operation.progress_total,
        "progress_done": operation.progress_done,
        "attempt": operation.attempt,
        "terminal": operation.status in TERMINAL_STATUSES,
        "public_error": operation.public_error,
    }
    if operation.receipt is not None:
        payload["receipt"] = dict(operation.receipt)
    lease_at = _aware(operation.lease_expires_at)
    payload["resumable"] = operation.status in ACTIVE_OPERATION_STATUSES and (
        lease_at is None or lease_at <= _utcnow()
    )
    payload["resumable_after"] = lease_at.isoformat() if lease_at else None
    return payload


async def get_operation(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    *,
    for_update: bool = False,
) -> WorkpaperGenerationOperation | None:
    stmt = sa.select(WorkpaperGenerationOperation).where(
        WorkpaperGenerationOperation.id == operation_id,
        WorkpaperGenerationOperation.project_id == project_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _prepare_descriptors(
    db: AsyncSession,
    *,
    kind: str,
    project_id: UUID,
    template_set_id: UUID | None,
    codes: list[str] | None,
) -> tuple[GenerationPlan, list[GenerationDescriptor], list[str], list[str]]:
    if kind == "template_set":
        if template_set_id is None:
            raise ValueError("模板集标识不能为空")
        return await prepare_template_set_descriptors(db, project_id, template_set_id, codes)
    plan, descriptors, effective = await prepare_code_descriptors(db, project_id, codes or [])
    return plan, descriptors, [], effective


async def prepare_operation(
    db: AsyncSession,
    *,
    operation_id: UUID,
    project_id: UUID,
    actor_user_id: UUID,
    year: int,
    kind: Literal["template_set", "from_codes"],
    template_set_id: UUID | None = None,
    codes: list[str] | None = None,
) -> PrepareResult:
    """Phase A：锁内冻结分流/描述符并预留身份；调用方随后 commit 释放项目锁。"""
    canonical = canonical_request(
        kind=kind, project_id=project_id, year=year,
        template_set_id=template_set_id, codes=codes,
    )
    digest = request_digest(canonical)
    existing = (await db.execute(
        sa.select(WorkpaperGenerationOperation)
        .where(WorkpaperGenerationOperation.id == operation_id)
        .with_for_update()
    )).scalar_one_or_none()
    if existing is not None:
        if existing.project_id != project_id:
            raise OperationConflict("operation_id 已用于其他生成请求")
        if existing.request_hash != digest:
            raise OperationConflict("operation_id 已用于不同的生成请求")
        if existing.status in TERMINAL_STATUSES:
            return PrepareResult(existing.id, existing.status, "terminal", existing.receipt)
        lease_at = _aware(existing.lease_expires_at)
        if existing.lease_token and lease_at and lease_at > _utcnow():
            return PrepareResult(existing.id, existing.status, "active")
        return PrepareResult(existing.id, existing.status, "resume")

    plan, descriptors, ignored, effective_codes = await _prepare_descriptors(
        db, kind=kind, project_id=project_id,
        template_set_id=template_set_id, codes=codes,
    )
    from app.services.wp_generate_file import load_generation_scenario

    scenario, has_foreign_currency = await load_generation_scenario(db, project_id)
    receipt = GenerationReceipt.from_plan(plan)
    receipt.ignored_codes = list(ignored)
    scope_revision = scope_decision_revision(plan.scope, effective_codes)
    operation = WorkpaperGenerationOperation(
        id=operation_id,
        project_id=project_id,
        year=year,
        actor_user_id=actor_user_id,
        kind=kind,
        template_set_id=template_set_id,
        failure_policy="atomic" if kind == "template_set" else "per_item",
        request_payload={
            "request": canonical,
            "effective_codes": list(effective_codes),
            "ignored_codes": list(ignored),
            "scenario": scenario,
            "has_foreign_currency": has_foreign_currency,
            "initial_receipt": _receipt_with_compat(receipt, kind),
        },
        request_hash=digest,
        scope_revision=scope_revision,
        progress_total=len(descriptors),
        progress_done=0,
    )
    db.add(operation)
    # operation/item 没有 ORM relationship；先 flush 父行，避免启用 FK 的 SQLite/PG 将 item 排在父行前插入。
    await db.flush()
    for ordinal, descriptor in enumerate(descriptors):
        db.add(WorkpaperGenerationItem(
            operation_id=operation_id,
            ordinal=ordinal,
            wp_code=descriptor.wp_code,
            wp_name=descriptor.wp_name,
            audit_cycle=descriptor.audit_cycle,
            wp_index_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            template_source={"library_file": descriptor.library_file} if descriptor.library_file else {},
        ))
    await db.flush()
    return PrepareResult(operation_id, "prepared", "created")


async def claim_operation(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
) -> ClaimResult:
    """原子领取 active operation；调用方 commit 后才开始文件 IO。"""
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None:
        raise LookupError("生成操作不存在")
    if operation.status in TERMINAL_STATUSES:
        return ClaimResult(operation.id, operation.status, None, False)
    now = _utcnow()
    lease_at = _aware(operation.lease_expires_at)
    if operation.lease_token and lease_at and lease_at > now:
        return ClaimResult(operation.id, operation.status, None, True)
    token = uuid.uuid4()
    operation.lease_token = token
    operation.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    operation.attempt += 1
    operation.started_at = operation.started_at or now
    if operation.status in {"prepared", "materializing"}:
        operation.status = "materializing"
    elif operation.status == "finalizing":
        operation.status = "materialized"
    operation.public_error = None
    await db.flush()
    return ClaimResult(operation.id, operation.status, token, False)


async def load_materialization_snapshot(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
) -> MaterializationSnapshot:
    operation = await get_operation(db, project_id, operation_id)
    if operation is None or operation.lease_token != lease_token:
        raise OperationConflict("生成操作租约已失效")
    rows = (await db.execute(
        sa.select(WorkpaperGenerationItem)
        .where(WorkpaperGenerationItem.operation_id == operation_id)
        .order_by(WorkpaperGenerationItem.ordinal)
    )).scalars().all()
    scenario = str((operation.request_payload or {}).get("scenario") or "normal")
    has_foreign_currency = bool((operation.request_payload or {}).get("has_foreign_currency"))
    items = tuple(StagingItem(
        item_id=row.id,
        wp_id=row.wp_id,
        wp_code=row.wp_code,
        wp_name=row.wp_name,
        library_file=(row.template_source or {}).get("library_file"),
        expected_source_fingerprint=row.template_fingerprint,
        expected_file_sha256=row.file_sha256,
        expected_from_template=bool(row.from_template),
        existing_staging_path=row.staging_path,
    ) for row in rows if row.status not in {"failed", "stale", "succeeded"})
    return MaterializationSnapshot(
        operation.id, operation.project_id, operation.kind, operation.failure_policy,
        scenario, has_foreign_currency, lease_token, items,
    )


async def record_source_snapshots(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
    snapshots: list[SourceSnapshot],
) -> None:
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None or operation.lease_token != lease_token or operation.status != "materializing":
        raise OperationConflict("生成操作不再处于模板冻结阶段")
    rows = {row.id: row for row in (await db.execute(
        sa.select(WorkpaperGenerationItem).where(WorkpaperGenerationItem.operation_id == operation_id)
    )).scalars().all()}
    for snapshot in snapshots:
        row = rows.get(snapshot.item_id)
        if row is None:
            raise OperationConflict("生成明细不存在")
        if row.template_fingerprint and row.template_fingerprint != snapshot.fingerprint:
            raise OperationConflict(f"模板来源已变化：{row.wp_code}")
        row.template_source = {**(row.template_source or {}), **snapshot.source}
        row.template_fingerprint = snapshot.fingerprint
        row.status = "materializing"
    await db.flush()


async def record_materialized(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
    materialized: list[MaterializedItem],
    failed: list[tuple[UUID, str]] | None = None,
) -> None:
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None or operation.lease_token != lease_token or operation.status != "materializing":
        raise OperationConflict("生成操作不再处于文件物化阶段")
    rows = {row.id: row for row in (await db.execute(
        sa.select(WorkpaperGenerationItem).where(WorkpaperGenerationItem.operation_id == operation_id)
    )).scalars().all()}
    for result in materialized:
        row = rows[result.item_id]
        row.staging_path = result.staging_path
        row.file_sha256 = result.file_sha256
        row.from_template = result.from_template
        row.status = "materialized"
        row.error = None
    for item_id, error in failed or []:
        row = rows[item_id]
        row.status = "failed"
        row.error = failure_text(error)
    operation.progress_done = len(materialized) + len(failed or [])
    operation.status = "materialized"
    operation.lease_expires_at = _utcnow() + timedelta(seconds=LEASE_SECONDS)
    await db.flush()


async def mark_operation_failed(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    error: BaseException | str,
) -> dict[str, Any]:
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None:
        raise LookupError("生成操作不存在")
    if operation.status in TERMINAL_STATUSES:
        return operation_payload(operation)
    base = dict((operation.request_payload or {}).get("initial_receipt") or {})
    message = public_failure_text(error)
    logger.error("底稿生成 operation 失败 operation=%s: %s", operation_id, error)
    base["failures"] = [*list(base.get("failures") or []), {"wp_code": "*", "error": message}]
    base["message"] = f"底稿生成失败：{message}"
    base["operation_id"] = str(operation.id)
    base["status"] = "failed"
    operation.status = "failed"
    operation.receipt = base
    operation.public_error = message
    operation.finished_at = _utcnow()
    operation.lease_token = None
    operation.lease_expires_at = None
    await db.flush()
    return operation_payload(operation)


async def release_operation_lease(
    db: AsyncSession,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
    error: BaseException | str,
) -> None:
    """commit 结果不确定时只释放租约，不把可恢复 operation 错标 failed。"""
    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None or operation.status in TERMINAL_STATUSES:
        return
    if operation.lease_token == lease_token:
        operation.lease_token = None
        operation.lease_expires_at = None
        operation.public_error = public_failure_text(error)
        if operation.status == "finalizing":
            operation.status = "materialized"
        await db.flush()


async def finalize_operation(
    db: AsyncSession,
    *,
    project_id: UUID,
    operation_id: UUID,
    lease_token: UUID,
) -> dict[str, Any]:
    """Phase B：锁内重判并发布；调用方 commit 后 terminal receipt 才生效。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
    from app.services.dataset_query import bind_to_active_dataset
    from app.services.wp_generate_file import GeneratedWorkpaperFile
    from app.services.wp_generation_staging import (
        cleanup_staging,
        discard_staging_file,
        file_sha256,
        promote_staging,
    )
    from app.services.wp_parsed_data_service import ensure_parsed_data_placeholder

    operation = await get_operation(db, project_id, operation_id, for_update=True)
    if operation is None:
        raise LookupError("生成操作不存在")
    if operation.status in TERMINAL_STATUSES:
        return operation_payload(operation)
    if operation.lease_token != lease_token or operation.status not in {"materialized", "finalizing"}:
        raise OperationConflict("生成操作不再处于发布阶段")
    operation.status = "finalizing"

    requested_codes = list((operation.request_payload or {}).get("effective_codes") or [])
    plan = await plan_generation(db, project_id, requested_codes)
    if scope_decision_revision(plan.scope, requested_codes) != operation.scope_revision:
        operation.status = "stale"
        operation.public_error = "程序裁剪结果已变化，请刷新生成计划后重试"
        operation.finished_at = _utcnow()
        operation.lease_token = None
        operation.lease_expires_at = None
        for item in (await db.execute(sa.select(WorkpaperGenerationItem).where(
            WorkpaperGenerationItem.operation_id == operation_id
        ))).scalars().all():
            item.status = "stale"
            discard_staging_file(project_id, operation_id, item.staging_path)
        receipt = GenerationReceipt.from_plan(plan)
        receipt.ignored_codes = list((operation.request_payload or {}).get("ignored_codes") or [])
        payload = _receipt_with_compat(receipt, operation.kind)
        payload.update(operation_id=str(operation.id), status="stale")
        operation.receipt = payload
        await db.flush()
        cleanup_staging(project_id, operation_id)
        return operation_payload(operation)

    receipt = GenerationReceipt.from_plan(plan)
    receipt.ignored_codes = list((operation.request_payload or {}).get("ignored_codes") or [])
    items = (await db.execute(
        sa.select(WorkpaperGenerationItem)
        .where(WorkpaperGenerationItem.operation_id == operation_id)
        .order_by(WorkpaperGenerationItem.ordinal)
    )).scalars().all()
    allowed = set(plan.to_create)
    moved_paths: list[tuple[Any, str]] = []

    async def publish_item(item: WorkpaperGenerationItem) -> None:
        if item.status == "failed":
            receipt.add_failure(item.wp_code, item.error or "文件物化失败")
            return
        if item.wp_code not in allowed:
            discard_staging_file(project_id, operation_id, item.staging_path)
            item.status = "stale"
            return
        if not item.staging_path or not item.file_sha256:
            raise RuntimeError(f"{item.wp_code} 缺少 staging manifest")

        index = WpIndex(
            id=item.wp_index_id,
            project_id=project_id,
            wp_code=item.wp_code,
            wp_name=item.wp_name,
            audit_cycle=item.audit_cycle,
            status=WpStatus.not_started,
        )
        paper = WorkingPaper(
            id=item.wp_id,
            project_id=project_id,
            wp_index_id=item.wp_index_id,
            file_path="",
            source_type=WpSourceType.template,
            file_version=1,
            created_by=operation.actor_user_id,
        )
        db.add(index)
        # WpIndex/WorkingPaper 没有 ORM relationship；先 flush 父索引，保证启用 FK 的数据库插入顺序。
        await db.flush()
        db.add(paper)
        await db.flush()
        try:
            await bind_to_active_dataset(db, paper, project_id, operation.year)
        except Exception:
            # 与旧生成入口一致：没有 active dataset 时不阻断底稿生成。
            pass

        header_issue: str | None = item.header_issue
        if operation.kind == "from_codes":
            if not item.header_prepared:
                raise RuntimeError(f"{item.wp_code} 表头 staging 尚未准备完成")
            ensure_parsed_data_placeholder(paper, wp_code=item.wp_code, created_by="generate_from_codes")

        promoted = promote_staging(project_id, item.wp_id, item.staging_path, item.file_sha256)
        paper.file_path = str(promoted.path)
        item.final_path = str(promoted.path)
        item.status = "succeeded"
        if promoted.moved:
            moved_paths.append((promoted.path, item.file_sha256))
        receipt.add_created(
            item.wp_code,
            GeneratedWorkpaperFile(promoted.path, bool(item.from_template)),
            header_issue=header_issue,
            header_filled=operation.kind == "from_codes",
        )

    try:
        if operation.failure_policy == "atomic":
            for item in items:
                await publish_item(item)
        else:
            for item in items:
                try:
                    async with db.begin_nested():
                        await publish_item(item)
                except Exception as exc:
                    receipt.add_failure(item.wp_code, exc)
                    item.status = "failed"
                    item.error = failure_text(exc)
                    discard_staging_file(project_id, operation_id, item.staging_path)
        await db.flush()
    except BaseException:
        for path, digest in moved_paths:
            try:
                if path.is_file() and file_sha256(path) == digest:
                    path.unlink()
            except OSError:
                pass
        raise

    operation.status = "partial_failed" if receipt.failures else "succeeded"
    operation.progress_done = operation.progress_total
    operation.public_error = None
    operation.finished_at = _utcnow()
    operation.lease_token = None
    operation.lease_expires_at = None
    payload = _receipt_with_compat(receipt, operation.kind)
    payload.update(operation_id=str(operation.id), status=operation.status)
    operation.receipt = payload
    await db.flush()
    cleanup_staging(project_id, operation_id)
    return operation_payload(operation)
