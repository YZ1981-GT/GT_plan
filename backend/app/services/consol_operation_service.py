"""持久合并 operation 的请求合并、lease 与 revision CAS。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.schemas.consol_context import ConsolContext
from app.schemas.consol_operation import ConsolVersionVector
from app.services.consol_version_vector import build_version_vector

LEASE_SECONDS = 90


class OperationConflict(RuntimeError):
    """幂等键、lease 或 revision 冲突。"""


class OperationBoundaryError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class OperationRequest:
    operation: ConsolOperation
    disposition: str  # created / coalesced / replayed


@dataclass(frozen=True)
class OperationClaim:
    operation_id: UUID
    project_id: UUID
    year: int
    operation_type: str
    lease_owner: UUID
    revision: int


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_request(
    *,
    project_id: UUID,
    year: int,
    operation_type: str,
    trigger_source: str,
    requested_actions: Iterable[str] = (),
) -> dict[str, Any]:
    if operation_type not in {"refresh_all", "push"}:
        raise ValueError("operation_type 只能是 refresh_all 或 push")
    trigger = str(trigger_source or "manual").strip()
    if not trigger:
        raise ValueError("trigger_source 不能为空")
    return {
        "project_id": str(project_id),
        "year": int(year),
        "operation_type": operation_type,
        "trigger_sources": [trigger],
        "requested_actions": sorted({str(item).strip() for item in requested_actions if str(item).strip()}),
    }


def merge_requests(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if left.get("project_id") != right.get("project_id") or left.get("year") != right.get("year"):
        raise ValueError("只能合并同一项目和年度的合并请求")
    return {
        "project_id": left["project_id"],
        "year": int(left["year"]),
        "operation_type": (
            "refresh_all" if "refresh_all" in {left.get("operation_type"), right.get("operation_type")}
            else "push"
        ),
        "trigger_sources": sorted(set(left.get("trigger_sources") or []) | set(right.get("trigger_sources") or [])),
        "requested_actions": sorted(set(left.get("requested_actions") or []) | set(right.get("requested_actions") or [])),
    }


def request_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


async def validate_project_boundary(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    writable: bool,
) -> Any:
    from app.models.core import Project
    from app.models.base import ProjectStatus
    from app.services.project_audit_year import resolve_project_audit_year

    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise OperationBoundaryError(404, "PROJECT_NOT_FOUND", "项目不存在或已删除")
    if str(project.report_scope or "").strip().lower() != "consolidated":
        raise OperationBoundaryError(400, "NOT_CONSOLIDATED", "只有合并报表项目可以运行合并任务")
    actual_year = resolve_project_audit_year(project)
    if actual_year is None:
        raise OperationBoundaryError(422, "AUDIT_YEAR_MISSING", "项目未设置审计年度")
    if actual_year != year:
        raise OperationBoundaryError(
            409, "AUDIT_YEAR_MISMATCH", f"请求年度 {year} 与项目审计年度 {actual_year} 不一致",
        )
    if writable and project.status == ProjectStatus.archived:
        raise OperationBoundaryError(423, "PROJECT_ARCHIVED", "项目已归档，不能更新合并结果")
    if writable and bool(project.consol_lock):
        raise OperationBoundaryError(423, "CONSOLIDATION_LOCKED", "项目已被合并锁定，不能更新合并结果")
    return project


async def _snapshot(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    operation_id: UUID,
) -> tuple[ConsolContext, ConsolVersionVector]:
    from app.services.consol_context_service import build_consol_context
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db, project_id)
    if tree is None:
        raise OperationBoundaryError(409, "CONSOL_TREE_MISSING", "当前项目没有可计算的企业树")
    seed = ConsolContext(project_id=project_id, year=year, run_id=operation_id)
    context = await build_consol_context(db, project_id, year, tree=tree, seed=seed)
    vector = await build_version_vector(db, context=context, tree=tree)
    context = context.with_resolution(
        source_version=vector.digest,
        formula_version=vector.formula_digest,
        template_version=vector.template_digest,
    )
    return context, vector


async def _find_idempotent(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    key: str,
) -> tuple[ConsolOperation, str] | None:
    # JSONB 下标访问在 SQLite 编译成 JSON_EXTRACT，在 PostgreSQL 编译成 ->>；
    # 原 incoming hash 非空，精确按键取值即可判断别名，不扫描最近 N 条或模糊匹配文本。
    alias_hash = ConsolOperation.idempotency_keys[key].as_string()
    row = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            sa.or_(ConsolOperation.idempotency_key == key, alias_hash.is_not(None)),
        ).order_by(ConsolOperation.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    keys = dict(row.idempotency_keys or {})
    if key == row.idempotency_key:
        return row, keys.get(key) or row.request_hash
    return row, keys[key]


async def _request_lock(db: AsyncSession, project_id: UUID, year: int) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"consol_operation_request:{project_id}:{year}"},
    )


async def request_operation(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    operation_type: str,
    idempotency_key: str | None = None,
    trigger_source: str = "manual",
    triggered_by: UUID | None = None,
    requested_actions: Iterable[str] = (),
) -> OperationRequest:
    """创建 queued 行；已有 queued 时合并到同一行并递增 revision。"""
    await _request_lock(db, project_id, year)
    await validate_project_boundary(db, project_id, year, writable=True)
    key = str(idempotency_key or uuid4()).strip()
    if not 1 <= len(key) <= 128:
        raise ValueError("幂等键长度必须为 1 到 128")
    incoming = canonical_request(
        project_id=project_id,
        year=year,
        operation_type=operation_type,
        trigger_source=trigger_source,
        requested_actions=requested_actions,
    )
    incoming_hash = request_digest(incoming)
    replay = await _find_idempotent(db, project_id, year, key)
    if replay is not None:
        operation, original_hash = replay
        if original_hash != incoming_hash:
            raise OperationConflict("同一幂等键对应了不同的合并请求")
        return OperationRequest(operation, "replayed")

    queued = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "queued",
        ).with_for_update()
    )).scalar_one_or_none()
    if queued is not None:
        merged = merge_requests(dict(queued.request_payload or {}), incoming)
        context, vector = await _snapshot(db, project_id, year, queued.id)
        keys = dict(queued.idempotency_keys or {})
        keys[key] = incoming_hash
        queued.idempotency_keys = keys
        queued.request_payload = merged
        queued.request_hash = request_digest(merged)
        queued.operation_type = merged["operation_type"]
        queued.trigger_source = trigger_source
        queued.triggered_by = triggered_by
        queued.context_json = context.to_dict()
        queued.version_vector = vector.model_dump(mode="json")
        queued.revision += 1
        queued.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return OperationRequest(queued, "coalesced")

    operation_id = uuid4()
    context, vector = await _snapshot(db, project_id, year, operation_id)
    operation = ConsolOperation(
        id=operation_id,
        project_id=project_id,
        year=year,
        operation_type=operation_type,
        idempotency_key=key,
        idempotency_keys={key: incoming_hash},
        request_hash=incoming_hash,
        request_payload=incoming,
        context_json=context.to_dict(),
        version_vector=vector.model_dump(mode="json"),
        status="queued",
        revision=1,
        trigger_source=trigger_source,
        triggered_by=triggered_by,
        steps=[], errors=[], result_refs={},
        metrics={"tree_nodes": len(context.node_keys)},
    )
    db.add(operation)
    await db.flush()
    return OperationRequest(operation, "created")


async def get_operation(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    operation_id: UUID,
) -> ConsolOperation | None:
    return (await db.execute(sa.select(ConsolOperation).where(
        ConsolOperation.id == operation_id,
        ConsolOperation.project_id == project_id,
        ConsolOperation.year == year,
    ))).scalar_one_or_none()


async def list_operations(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    limit: int = 20,
) -> list[ConsolOperation]:
    return list((await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
        ).order_by(ConsolOperation.queued_at.desc(), ConsolOperation.id.desc())
        .limit(max(1, min(int(limit), 100)))
    )).scalars().all())


def _claim_from(operation: ConsolOperation, owner: UUID) -> OperationClaim:
    return OperationClaim(
        operation_id=operation.id,
        project_id=operation.project_id,
        year=operation.year,
        operation_type=operation.operation_type,
        lease_owner=owner,
        revision=operation.revision,
    )


async def claim_next_operation(
    db: AsyncSession,
    *,
    lease_owner: UUID,
    operation_id: UUID | None = None,
    lease_seconds: int = LEASE_SECONDS,
) -> OperationClaim | None:
    """认领 queued 或 lease 过期的 running；同项目已有 running 时不认领 queued。"""
    now = datetime.now(timezone.utc)
    running = sa.orm.aliased(ConsolOperation)
    candidate = sa.or_(
        sa.and_(
            ConsolOperation.status == "queued",
            ~sa.exists(sa.select(1).where(
                running.project_id == ConsolOperation.project_id,
                running.year == ConsolOperation.year,
                running.status == "running",
            )),
        ),
        sa.and_(
            ConsolOperation.status == "running",
            ConsolOperation.lease_expires_at.is_not(None),
            ConsolOperation.lease_expires_at <= now,
        ),
    )
    stmt = sa.select(ConsolOperation).where(candidate)
    if operation_id is not None:
        stmt = stmt.where(ConsolOperation.id == operation_id)
    operation = (await db.execute(
        stmt.order_by(ConsolOperation.queued_at, ConsolOperation.id)
        .with_for_update(skip_locked=True).limit(1)
    )).scalars().first()
    if operation is None:
        return None
    operation.status = "running"
    operation.lease_owner = lease_owner
    operation.lease_expires_at = now + timedelta(seconds=max(15, lease_seconds))
    operation.heartbeat_at = now
    operation.started_at = operation.started_at or now
    operation.finished_at = None
    operation.attempt += 1
    operation.updated_at = now
    await db.flush()
    return _claim_from(operation, lease_owner)


async def renew_lease(
    db: AsyncSession,
    claim: OperationClaim,
    *,
    lease_seconds: int = LEASE_SECONDS,
) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.execute(sa.update(ConsolOperation).where(
        ConsolOperation.id == claim.operation_id,
        ConsolOperation.status == "running",
        ConsolOperation.revision == claim.revision,
        ConsolOperation.lease_owner == claim.lease_owner,
    ).values(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=max(15, lease_seconds)),
        updated_at=now,
    ))
    return result.rowcount == 1


async def record_progress(
    db: AsyncSession,
    claim: OperationClaim,
    *,
    steps: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> bool:
    operation = (await db.execute(sa.select(ConsolOperation).where(
        ConsolOperation.id == claim.operation_id,
        ConsolOperation.status == "running",
        ConsolOperation.revision == claim.revision,
        ConsolOperation.lease_owner == claim.lease_owner,
    ).with_for_update())).scalar_one_or_none()
    if operation is None:
        return False
    if steps is not None:
        operation.steps = list(steps)
    if errors is not None:
        operation.errors = list(errors)
    if metrics:
        operation.metrics = {**dict(operation.metrics or {}), **metrics}
    operation.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def complete_operation(
    db: AsyncSession,
    claim: OperationClaim,
    status: str,
    *,
    steps: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    metrics: dict[str, Any],
    result_refs: dict[str, Any],
) -> bool:
    if status not in {"succeeded", "partial", "failed", "stale", "cancelled"}:
        raise ValueError(f"非法合并 operation 终态：{status}")
    now = datetime.now(timezone.utc)
    result = await db.execute(sa.update(ConsolOperation).where(
        ConsolOperation.id == claim.operation_id,
        ConsolOperation.status == "running",
        ConsolOperation.revision == claim.revision,
        ConsolOperation.lease_owner == claim.lease_owner,
    ).values(
        status=status,
        steps=list(steps),
        errors=list(errors),
        metrics=dict(metrics),
        result_refs=dict(result_refs),
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=now,
        finished_at=now,
        updated_at=now,
    ))
    return result.rowcount == 1


async def seal_operation_for_signoff(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    snapshot_id: str,
    snapshot_hash: str,
    signed_by: UUID | None,
) -> ConsolOperation | None:
    """签字/锁定时把产出本次合并数的 operation 标记为已封存（terminal / sealed）。

    批 7 任务 7.3：签字路由在一致事务边界内调用。只认已成功的最近一次 operation
    （sign/lock 门已保证存在成功 operation），通过 batch 2 的 `result_refs` 输出通道
    写 `sealed` 标记——不新增列、不改状态机枚举（`succeeded` 本就是终态），
    使 operation 与签字快照/锁定互相引用、可追溯。只 flush，commit 由路由层负责。

    返回被封存的 operation（无成功 operation 时返回 None）。
    """
    operation = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "succeeded",
        ).order_by(ConsolOperation.finished_at.desc().nullslast()).limit(1)
        .with_for_update()
    )).scalar_one_or_none()
    if operation is None:
        return None

    refs = dict(operation.result_refs or {})
    refs["sealed"] = {
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "signed_by": str(signed_by) if signed_by else None,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }
    # 原地改 JSONB 再赋回同一对象 ORM 不发 UPDATE（#conventions 教训）⇒ 赋新 dict。
    operation.result_refs = refs
    operation.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return operation


async def cancel_operation(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    operation_id: UUID,
) -> ConsolOperation | None:
    operation = (await db.execute(sa.select(ConsolOperation).where(
        ConsolOperation.id == operation_id,
        ConsolOperation.project_id == project_id,
        ConsolOperation.year == year,
    ).with_for_update())).scalar_one_or_none()
    if operation is None:
        return None
    if operation.status != "queued":
        raise OperationConflict("只有尚未开始的合并运行可以取消")
    operation.status = "cancelled"
    operation.finished_at = datetime.now(timezone.utc)
    operation.updated_at = operation.finished_at
    operation.lease_owner = None
    operation.lease_expires_at = None
    await db.flush()
    return operation


def validate_snapshot(operation: ConsolOperation) -> ConsolContext:
    context = ConsolContext.from_dict(dict(operation.context_json or {}))
    if context.project_id != operation.project_id or context.year != operation.year:
        raise OperationConflict("合并运行上下文与记录边界不一致")
    if context.run_id != operation.id:
        raise OperationConflict("合并运行上下文 run_id 与 operation 不一致")
    ConsolVersionVector.model_validate(operation.version_vector)
    return context


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def operation_payload(operation: ConsolOperation) -> dict[str, Any]:
    return {
        "id": str(operation.id),
        "operation_id": str(operation.id),
        "project_id": str(operation.project_id),
        "year": operation.year,
        "operation_type": operation.operation_type,
        "idempotency_key": operation.idempotency_key,
        "request_hash": operation.request_hash,
        "status": operation.status,
        "revision": operation.revision,
        "attempt": operation.attempt,
        "context": dict(operation.context_json or {}),
        "version_vector": dict(operation.version_vector or {}),
        "steps": list(operation.steps or []),
        "errors": list(operation.errors or []),
        "result_refs": dict(operation.result_refs or {}),
        "metrics": dict(operation.metrics or {}),
        "trigger_source": operation.trigger_source,
        "queued_at": _iso(operation.queued_at),
        "started_at": _iso(operation.started_at),
        "finished_at": _iso(operation.finished_at),
        "updated_at": _iso(operation.updated_at),
    }


def legacy_refresh_payload(operation: ConsolOperation) -> dict[str, Any]:
    refs = dict(operation.result_refs or {})
    refresh = dict(refs.get("refresh_result") or {})
    legacy_status = {
        "queued": "queued",
        "running": "running",
        "succeeded": "completed",
        "partial": "completed",
        "failed": "failed",
        "stale": "failed",
        "cancelled": "failed",
    }[operation.status]
    return {
        "job_id": str(operation.id),
        "operation_id": str(operation.id),
        "project_id": str(operation.project_id),
        "year": operation.year,
        "status": legacy_status,
        "operation_status": operation.status,
        "current_step": (operation.metrics or {}).get("current_step"),
        "steps_completed": refresh.get("steps_completed", [
            row.get("step") for row in operation.steps or [] if row.get("status") == "succeeded"
        ]),
        "steps_skipped": refresh.get("steps_skipped", [
            row.get("step") for row in operation.steps or [] if row.get("status") == "skipped"
        ]),
        "total_steps": 6,
        "errors": list(operation.errors or []),
        "result": refresh or None,
        "created_at": _iso(operation.created_at),
        "updated_at": _iso(operation.updated_at),
    }


__all__ = [
    "LEASE_SECONDS", "OperationBoundaryError", "OperationClaim", "OperationConflict",
    "OperationRequest", "canonical_request", "cancel_operation", "claim_next_operation",
    "complete_operation", "get_operation", "legacy_refresh_payload", "list_operations",
    "merge_requests", "operation_payload", "record_progress", "renew_lease",
    "request_digest", "request_operation", "validate_project_boundary", "validate_snapshot",
]
