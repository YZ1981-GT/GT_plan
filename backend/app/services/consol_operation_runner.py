"""持久合并 operation 的业务编排适配层；不改合并金额内核。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.schemas.consol_context import ConsolContext
from app.schemas.consol_operation import ConsolVersionVector
from app.services.consol_operation_service import (
    OperationBoundaryError,
    OperationClaim,
    OperationConflict,
    complete_operation,
    get_operation,
    record_progress,
    validate_project_boundary,
    validate_snapshot,
)
from app.services.consol_version_vector import build_version_vector, vectors_equal

_INPUT_GUARD_KEYS = (
    "tree_fingerprint",
    "tb_digest",
    "elimination_digest",
    "formula_digest",
    "note_mapping_digest",
    "template_digest",
)


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    event: str | None
    event_payload: dict[str, Any]


def _source_inputs_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(before.get(key) == after.get(key) for key in _INPUT_GUARD_KEYS)


def _refresh_steps(result: Any) -> list[dict[str, Any]]:
    completed = set(result.steps_completed)
    skipped = set(result.steps_skipped)
    errors = {str(item.get("step")): item for item in result.errors}
    order = ("tree", "worksheet", "trial", "reconcile", "report", "notes")
    rows: list[dict[str, Any]] = []
    for step in order:
        if step in errors:
            rows.append({"step": step, "status": "failed", "detail": errors[step].get("error")})
        elif step in skipped:
            rows.append({"step": step, "status": "skipped"})
        elif step in completed:
            rows.append({"step": step, "status": "succeeded"})
    return rows


def _refresh_status(result: Any) -> str:
    failed_steps = {str(item.get("step")) for item in result.errors}
    if failed_steps & {"tree", "worksheet", "trial"}:
        return "failed"
    if result.errors:
        return "partial"
    return "succeeded"


def _reconciliation_payload(result: Any) -> dict[str, Any] | None:
    if result.reconciliation is None:
        return None
    return {
        "is_reconciled": result.reconciliation.is_reconciled,
        "diff_count": len(result.reconciliation.diffs),
        "max_abs_diff": str(result.reconciliation.max_abs_diff),
    }


async def _load_runtime(
    db: AsyncSession,
    claim: OperationClaim,
) -> tuple[ConsolOperation, ConsolContext, Any, ConsolVersionVector]:
    from app.services.consol_context_service import build_consol_context, validate_context
    from app.services.consol_tree_service import build_tree

    operation = await get_operation(
        db, claim.project_id, claim.year, claim.operation_id
    )
    if operation is None:
        raise OperationConflict("合并 operation 不存在")
    if (
        operation.status != "running"
        or operation.revision != claim.revision
        or operation.lease_owner != claim.lease_owner
    ):
        raise OperationConflict("合并 operation 租约或 revision 已失效")
    await validate_project_boundary(db, claim.project_id, claim.year, writable=True)
    stored_context = validate_snapshot(operation)
    tree = await build_tree(db, claim.project_id)
    context = await build_consol_context(
        db, claim.project_id, claim.year, tree=tree, seed=stored_context
    )
    validate_context(context, claim.project_id, claim.year, tree=tree)
    # 必须传已解析的 context（含 report_scope/period_end），与请求路径
    # consol_operation_service._snapshot 的 build_version_vector(context=context) 同源；
    # 否则 bare context 的 report_scope=None 会让 template_digest 恒不相等，
    # 把本应 succeeded 的运行永远判成 stale（INPUT_VERSION_CHANGED）。
    current_vector = await build_version_vector(db, context=context, tree=tree)
    return operation, context, tree, current_vector


async def execute_claim(db: AsyncSession, claim: OperationClaim) -> ExecutionResult:
    """执行已提交 claim；operation 终态只 flush，由 worker 在返回后 commit。"""
    started = time.monotonic()
    operation, context, tree, current_vector = await _load_runtime(db, claim)
    stored_vector = ConsolVersionVector.model_validate(operation.version_vector)
    if not vectors_equal(stored_vector, current_vector):
        errors = [{
            "code": "INPUT_VERSION_CHANGED",
            "message": "合并输入版本在排队期间已变化，请使用新 revision 重试",
        }]
        ok = await complete_operation(
            db,
            claim,
            "stale",
            steps=[],
            errors=errors,
            metrics={"duration_ms": int((time.monotonic() - started) * 1000)},
            result_refs={"observed_version_vector": current_vector.model_dump(mode="json")},
        )
        if not ok:
            raise OperationConflict("stale 结果写回时 lease 已失效")
        return ExecutionResult("stale", "consol.refresh.error", {
            "project_id": str(claim.project_id),
            "year": claim.year,
            "job_id": str(claim.operation_id),
            "operation_id": str(claim.operation_id),
            "status": "failed",
            "operation_status": "stale",
            "error": errors[0]["message"],
        })

    await record_progress(
        db,
        claim,
        metrics={"current_step": "starting", "attempt": operation.attempt},
    )
    if claim.operation_type == "push":
        execution = await _execute_push(db, operation, claim, context, tree, started)
    elif claim.operation_type == "refresh_all":
        execution = await _execute_refresh(db, operation, claim, context, tree, started)
    else:  # 数据库 CHECK 外再防御一次
        raise OperationConflict(f"未知合并运行类型：{claim.operation_type}")
    return execution


async def _post_vector(db: AsyncSession, claim: OperationClaim, context: ConsolContext, tree: Any):
    # 同 _load_runtime：传已解析 context 以与请求路径摘要同源，否则运行后对比恒判输入已变化。
    return await build_version_vector(db, context=context, tree=tree)


async def _execute_push(
    db: AsyncSession,
    operation: ConsolOperation,
    claim: OperationClaim,
    context: ConsolContext,
    tree: Any,
    started: float,
) -> ExecutionResult:
    from app.services.consol_push_service import push

    result = await push(
        db,
        claim.project_id,
        claim.year,
        trigger=operation.trigger_source,
        user_id=operation.triggered_by,
        operation_id=operation.id,
        operation_revision=claim.revision,
        context=context,
        tree=tree,
    )
    errors = [
        {"code": "PUSH_WARNING", "message": warning}
        for warning in result.warnings
        if result.status == "failed"
    ]
    status = result.status
    post = await _post_vector(db, claim, context, tree)
    if not _source_inputs_equal(dict(operation.version_vector), post.model_dump(mode="json")):
        status = "stale"
        errors.append({
            "code": "INPUT_VERSION_CHANGED",
            "message": "合并输入在运行期间发生变化，本次结果未标记为正式成功",
        })
    metrics = {
        "duration_ms": int((time.monotonic() - started) * 1000),
        "current_step": "finished",
        "step_count": len(result.steps),
        "warning_count": len(result.warnings),
    }
    refs = {
        "push_run_id": str(result.run_id),
        "pushed_projects": list(result.pushed_projects),
        "post_version_vector": post.model_dump(mode="json"),
    }
    if result.report_run_ids:
        refs["report_run_ids"] = dict(result.report_run_ids)
        refs["report_row_digests"] = dict(result.report_row_digests)
        refs["input_revision"] = claim.revision
        source_run = result.report_run_ids.get(str(claim.project_id))
        if source_run:
            refs["report_run_id"] = source_run
            refs["report_row_digest"] = result.report_row_digests.get(str(claim.project_id))
    ok = await complete_operation(
        db, claim, status, steps=list(result.steps), errors=errors, metrics=metrics, result_refs=refs
    )
    if not ok:
        raise OperationConflict("推送结果写回时 lease 或 revision 已失效")
    return ExecutionResult(status, None, {})


async def _execute_refresh(
    db: AsyncSession,
    operation: ConsolOperation,
    claim: OperationClaim,
    context: ConsolContext,
    tree: Any,
    started: float,
) -> ExecutionResult:
    from app.services.consol_cascade_refresh_service import refresh_all
    from app.services.consol_refresh_job_service import SSE_COMPLETED, SSE_ERROR, SSE_PROGRESS
    from app.services.event_bus import event_bus

    progress: dict[str, dict[str, Any]] = {}

    def publish(step: str, current: int, total: int, current_node: str | None, status: str) -> None:
        progress[step] = {
            "step": step,
            "status": "succeeded" if status == "completed" else status,
            "current": current,
            "total": total,
            "current_node": current_node,
        }
        event_bus.broadcast_raw(SSE_PROGRESS, {
            "project_id": str(claim.project_id),
            "year": claim.year,
            "job_id": str(claim.operation_id),
            "operation_id": str(claim.operation_id),
            "revision": claim.revision,
            "step": step,
            "current": current,
            "total": total,
            "current_node": current_node,
            "status": status,
        })

    result = await refresh_all(
        db,
        claim.project_id,
        claim.year,
        progress_cb=publish,
        context=context,
        tree=tree,
        operation_revision=claim.revision,
        triggered_by=operation.triggered_by,
        report_trigger=operation.trigger_source,
    )
    status = _refresh_status(result)
    errors = [dict(item) for item in result.errors]
    post = await _post_vector(db, claim, context, tree)
    if not _source_inputs_equal(dict(operation.version_vector), post.model_dump(mode="json")):
        status = "stale"
        errors.append({
            "code": "INPUT_VERSION_CHANGED",
            "message": "合并输入在运行期间发生变化，本次结果未标记为正式成功",
        })
    steps = _refresh_steps(result)
    refresh_result = {
        "nodes_refreshed": result.nodes_refreshed,
        "steps_completed": list(result.steps_completed),
        "steps_skipped": list(result.steps_skipped),
        "errors": list(result.errors),
        "duration_ms": result.duration_ms,
        "reconciliation": _reconciliation_payload(result),
    }
    metrics = {
        "duration_ms": int((time.monotonic() - started) * 1000),
        "cascade_duration_ms": result.duration_ms,
        "current_step": "finished",
        "nodes_refreshed": result.nodes_refreshed,
        "step_count": len(steps),
    }
    refs = {
        "refresh_result": refresh_result,
        "post_version_vector": post.model_dump(mode="json"),
    }
    if result.report_run_id is not None:
        refs["report_run_id"] = str(result.report_run_id)
        refs["report_row_digest"] = result.report_row_digest
        refs["input_revision"] = claim.revision
    ok = await complete_operation(
        db, claim, status, steps=steps, errors=errors, metrics=metrics, result_refs=refs
    )
    if not ok:
        raise OperationConflict("刷新结果写回时 lease 或 revision 已失效")

    legacy_status = "completed" if status in {"succeeded", "partial"} else "failed"
    event = SSE_COMPLETED if legacy_status == "completed" else SSE_ERROR
    payload = {
        "project_id": str(claim.project_id),
        "year": claim.year,
        "job_id": str(claim.operation_id),
        "operation_id": str(claim.operation_id),
        "revision": claim.revision,
        "status": legacy_status,
        "operation_status": status,
        "nodes_refreshed": result.nodes_refreshed,
        "steps_completed": list(result.steps_completed),
        "steps_skipped": list(result.steps_skipped),
        "errors": errors,
        "duration_ms": result.duration_ms,
    }
    if event == SSE_ERROR:
        payload["error"] = errors[0].get("message") if errors and "message" in errors[0] else (
            errors[0].get("error") if errors else "合并刷新失败"
        )
    return ExecutionResult(status, event, payload)


async def fail_claim(
    db: AsyncSession,
    claim: OperationClaim,
    error: BaseException,
) -> ExecutionResult:
    """把 runner 顶层异常安全落为 failed/stale；调用方先 rollback，再 commit 本结果。"""
    if isinstance(error, OperationBoundaryError):
        status = "stale"
        code = error.code
        message = error.message
    else:
        status = "failed"
        code = "OPERATION_FAILED"
        message = str(error) or type(error).__name__
    errors = [{"code": code, "message": message}]
    ok = await complete_operation(
        db,
        claim,
        status,
        steps=[],
        errors=errors,
        metrics={"current_step": "failed"},
        result_refs={},
    )
    if not ok:
        raise OperationConflict("失败状态写回时 lease 或 revision 已失效") from error
    payload = {
        "project_id": str(claim.project_id),
        "year": claim.year,
        "job_id": str(claim.operation_id),
        "operation_id": str(claim.operation_id),
        "revision": claim.revision,
        "status": "failed",
        "operation_status": status,
        "error": message,
    }
    return ExecutionResult(status, "consol.refresh.error", payload)


__all__ = ["ExecutionResult", "execute_claim", "fail_claim"]
