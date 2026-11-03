"""生成 operation 的路由层事务编排。

多次 commit 是两阶段边界本身：service 只 flush，本模块由 FastAPI 路由调用并统一提交/回滚。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import assert_project_permission
from app.models.core import User
from app.services.wp_generation_header_stage import prepare_staged_headers
from app.services.wp_generation_operation_service import (
    OperationConflict,
    claim_operation,
    finalize_operation,
    get_operation,
    load_materialization_snapshot,
    mark_operation_failed,
    operation_payload,
    prepare_operation,
    record_materialized,
    record_source_snapshots,
    release_operation_lease,
)
from app.services.wp_generation_staging import (
    cleanup_staging,
    materialize_atomic,
    materialize_per_item,
    snapshot_sources,
)


@dataclass(frozen=True)
class FlowResult:
    payload: dict
    status_code: int = 200


async def run_generation_operation(
    db: AsyncSession,
    current_user: User,
    *,
    operation_id: UUID,
    project_id: UUID,
    year: int,
    kind: Literal["template_set", "from_codes"],
    template_set_id: UUID | None,
    codes: list[str] | None,
) -> FlowResult:
    """准备 → 锁外 staging → 发布；网络重试以同 id 进入同一状态机。"""
    prepared = await prepare_operation(
        db,
        operation_id=operation_id,
        project_id=project_id,
        actor_user_id=current_user.id,
        year=year,
        kind=kind,
        template_set_id=template_set_id,
        codes=codes,
    )
    if prepared.action == "terminal":
        await db.commit()
        return FlowResult(dict(prepared.receipt or {}), 200)
    if prepared.action == "active":
        operation = await get_operation(db, project_id, operation_id)
        payload = operation_payload(operation) if operation else {"operation_id": str(operation_id), "status": "missing"}
        await db.commit()
        return FlowResult(payload, 202)
    await db.commit()  # Phase A：释放项目 scope lock

    claim = await claim_operation(db, project_id, operation_id)
    if claim.status in {"succeeded", "partial_failed", "failed", "stale"}:
        operation = await get_operation(db, project_id, operation_id)
        payload = dict((operation.receipt if operation else None) or {})
        await db.commit()
        return FlowResult(payload, 200)
    if claim.active or claim.lease_token is None:
        operation = await get_operation(db, project_id, operation_id)
        payload = operation_payload(operation) if operation else {"operation_id": str(operation_id), "status": "missing"}
        await db.commit()
        return FlowResult(payload, 202)
    token = claim.lease_token
    await db.commit()  # lease 对其他请求可见；此后不持项目锁

    snapshot = await load_materialization_snapshot(db, project_id, operation_id, token)
    await db.commit()  # 文件 hash / IO 前释放只读事务和连接
    try:
        if claim.status == "materializing":
            sources = await asyncio.to_thread(snapshot_sources, list(snapshot.items), snapshot.scenario)
            await record_source_snapshots(db, project_id, operation_id, token, sources)
            await db.commit()
            snapshot = await load_materialization_snapshot(db, project_id, operation_id, token)
            await db.commit()
            if snapshot.failure_policy == "atomic":
                materialized = await asyncio.to_thread(
                    materialize_atomic,
                    project_id,
                    operation_id,
                    list(snapshot.items),
                    scenario=snapshot.scenario,
                    has_foreign_currency=snapshot.has_foreign_currency,
                )
                failures: list[tuple[UUID, str]] = []
            else:
                materialized, failures = await asyncio.to_thread(
                    materialize_per_item,
                    project_id,
                    operation_id,
                    list(snapshot.items),
                    scenario=snapshot.scenario,
                    has_foreign_currency=snapshot.has_foreign_currency,
                )
            await record_materialized(
                db, project_id, operation_id, token, materialized, failures,
            )
            await db.commit()
        if snapshot.kind == "from_codes":
            await prepare_staged_headers(
                db, project_id=project_id, operation_id=operation_id, lease_token=token,
            )
            await db.commit()
    except Exception as exc:
        await db.rollback()
        cleanup_staging(project_id, operation_id)
        payload = await mark_operation_failed(db, project_id, operation_id, exc)
        await db.commit()
        return FlowResult(dict(payload.get("receipt") or payload), 200)

    # Phase B：权限和归档状态必须按当前事务重新判定，不能沿用 Phase A 的结果。
    try:
        await assert_project_permission(db, current_user, project_id, "edit")
        payload = await finalize_operation(
            db,
            project_id=project_id,
            operation_id=operation_id,
            lease_token=token,
        )
        await db.commit()
    except Exception as exc:
        # commit 可能在服务端已成功、客户端仅丢响应；不删正式文件，不把 operation 错标 failed。
        await db.rollback()
        await release_operation_lease(db, project_id, operation_id, token, exc)
        await db.commit()
        raise

    receipt = dict(payload.get("receipt") or {})
    return FlowResult(receipt or payload, 200)
