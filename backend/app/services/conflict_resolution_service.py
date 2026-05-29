"""跨模块冲突调解服务 — V3 收官增强 Req 7.1

提供 cross_module_conflicts 表的生命周期管理：

- enqueue(...)                     入队冲突（status='pending' resolution=None）
- resolve(...)                     用户调解（keep_manual / accept_new / merge）
- auto_resolve_system_recompute(...)  系统自动重算（直接写 status='resolved' resolution='accept_new'）
- list_pending(...)                仅 pending（前端 banner / 守门规则用）
- list_by_project(...)             分页 + 过滤
- count_pending(...)               计数（前端 badge 用）

每次状态变更都通过 ``audit_log_helper.append_audit_log`` 写审计：

- enqueue   → event_type='cross_module_conflict_enqueued' action='conflict_enqueue'
- resolve   → event_type='cross_module_conflict_resolved' action='conflict_resolve'
- auto      → event_type='cross_module_conflict_resolved' action='conflict_resolve'

入队成功后通过 ``event_bus.broadcast_raw('cross_module_conflict.enqueued', ...)``
推送 SSE，让在线用户立刻感知（Task 7.3 SSE 接入完整链路）。

依赖：
- backend/app/models/v3_refinement_models.py:CrossModuleConflict
- backend/app/services/audit_log_helper.py:append_audit_log
- backend/app/services/event_bus.py:event_bus.broadcast_raw（可选，无则记 logger）
- backend/migrations/V017__v3_refinement_tables.sql

Validates: Requirements 7.1, AC 7.1~7.4
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import CrossModuleConflict
from app.services.audit_log_helper import append_audit_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量与类型
# ---------------------------------------------------------------------------

Resolution = Literal["keep_manual", "accept_new", "merge"]
ConflictStatus = Literal["pending", "resolved", "auto_skipped"]
PropagationOrigin = Literal["user_edit", "system_recompute"]

VALID_RESOLUTIONS: set[str] = {"keep_manual", "accept_new", "merge"}
VALID_STATUSES: set[str] = {"pending", "resolved", "auto_skipped"}


# ---------------------------------------------------------------------------
# 业务异常（继承 ValueError，由 router 层映射 422）
# ---------------------------------------------------------------------------


class ConflictNotFoundError(ValueError):
    """冲突记录不存在。"""


class ConflictAlreadyResolvedError(ValueError):
    """冲突已调解过，不可重复操作。"""


class ConflictMergeValueRequiredError(ValueError):
    """resolution='merge' 必须提供 merge_value。"""


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _emit_enqueued_event(conflict: CrossModuleConflict) -> None:
    """通过 event_bus.broadcast_raw 推送 cross_module_conflict.enqueued。

    没有 event_bus 或运行时无 event loop 时静默回退到 logger.info。
    Task 7.3 SSE 接入会进一步对接前端订阅。
    """
    extra = {
        "conflict_id": str(conflict.id),
        "project_id": str(conflict.project_id),
        "source_module": conflict.source_module,
        "target_module": conflict.target_module,
    }
    try:
        # 延迟导入，避免循环依赖与测试环境未注册时报错
        from app.services.event_bus import event_bus  # noqa: WPS433

        event_bus.broadcast_raw("cross_module_conflict.enqueued", extra)
    except Exception as exc:  # pragma: no cover - 兜底，不应阻断业务
        logger.info(
            "cross_module_conflict.enqueued event_bus 不可用，仅记录日志: %s | %s",
            extra,
            exc,
        )


async def _write_enqueue_audit(
    *,
    db: AsyncSession,
    conflict: CrossModuleConflict,
    user_id: uuid.UUID | None,
) -> None:
    """入队审计：event_type='cross_module_conflict_enqueued'。"""
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": conflict.project_id,
            "action": "conflict_enqueue",
            "resource_type": "cross_module_conflict",
            "resource_id": str(conflict.id),
            "details": {
                "event_type": "cross_module_conflict_enqueued",
                "conflict_id": str(conflict.id),
                "source_module": conflict.source_module,
                "source_id": str(conflict.source_id),
                "target_module": conflict.target_module,
                "target_id": str(conflict.target_id),
                "target_field": conflict.target_field,
                "upstream_value": conflict.upstream_value,
                "manual_value": conflict.manual_value,
            },
        },
    )


async def _write_resolve_audit(
    *,
    db: AsyncSession,
    conflict: CrossModuleConflict,
    user_id: uuid.UUID | None,
    resolution_label: str,
) -> None:
    """调解审计：event_type='cross_module_conflict_resolved'。

    schema 强制 5 字段：conflict_id / resolution / upstream_value / manual_value / final_value。
    resolution_label 既可能是 keep_manual/accept_new/merge，
    也可能是 system_auto（系统自动重算场景，留痕用）。
    """
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": conflict.project_id,
            "action": "conflict_resolve",
            "resource_type": "cross_module_conflict",
            "resource_id": str(conflict.id),
            "details": {
                "event_type": "cross_module_conflict_resolved",
                "conflict_id": str(conflict.id),
                "resolution": resolution_label,
                "upstream_value": conflict.upstream_value,
                "manual_value": conflict.manual_value,
                "final_value": conflict.final_value,
            },
        },
    )


async def _load_pending_or_raise(
    db: AsyncSession, conflict_id: uuid.UUID
) -> CrossModuleConflict:
    """加载冲突，校验存在 + status='pending'。"""
    result = await db.execute(
        select(CrossModuleConflict).where(CrossModuleConflict.id == conflict_id)
    )
    conflict = result.scalar_one_or_none()
    if conflict is None:
        raise ConflictNotFoundError("冲突记录不存在")
    if conflict.status != "pending":
        raise ConflictAlreadyResolvedError("冲突已调解过，不可重复操作")
    return conflict


# ---------------------------------------------------------------------------
# 公共 API — 写入
# ---------------------------------------------------------------------------


async def enqueue(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    source_module: str,
    source_id: uuid.UUID,
    target_module: str,
    target_id: uuid.UUID,
    target_field: str,
    upstream_value: str | None,
    manual_value: str | None,
    user_id: uuid.UUID | None = None,
    propagation_origin: PropagationOrigin = "user_edit",
) -> CrossModuleConflict:
    """入队一条 pending 冲突记录。

    参数:
        db: 异步数据库会话
        project_id: 所属项目 UUID
        source_module: 上游模块标识（'workpaper' / 'adjustment' / 'trial_balance' 等）
        source_id: 上游业务实例 UUID
        target_module: 目标模块标识（'disclosure' / 'report' / 'workpaper' 等）
        target_id: 目标业务实例 UUID
        target_field: 目标字段名（如 'cells.A1' / 'amount' / 'narrative_p3'）
        upstream_value: 上游变更后的新值（None 表示清空）
        manual_value: 目标当前的手工值
        user_id: 触发上游变更的用户 UUID（system_recompute 时可为 None）
        propagation_origin: 传播来源；当前仅用于审计 details 留痕，
            后续 task 7.2 hook 会基于此自动选择 enqueue / auto_resolve 路径

    返回:
        新建的 CrossModuleConflict（status='pending', resolution=None, final_value=None）

    副作用:
        1. INSERT cross_module_conflicts
        2. append_audit_log(event_type='cross_module_conflict_enqueued')
        3. event_bus.broadcast_raw('cross_module_conflict.enqueued', ...)
    """
    conflict = CrossModuleConflict(
        id=uuid.uuid4(),
        project_id=project_id,
        source_module=source_module,
        source_id=source_id,
        target_module=target_module,
        target_id=target_id,
        target_field=target_field,
        upstream_value=upstream_value,
        manual_value=manual_value,
        final_value=None,
        resolution=None,
        resolved_by=None,
        resolved_at=None,
        status="pending",
    )
    db.add(conflict)
    await db.flush()

    await _write_enqueue_audit(db=db, conflict=conflict, user_id=user_id)

    # SSE 推送（不阻断；测试环境无 event loop 时 broadcast_raw 内部自洽）
    _emit_enqueued_event(conflict)

    logger.info(
        "cross_module_conflict 入队 conflict_id=%s project=%s %s.%s -> %s.%s.%s origin=%s",
        conflict.id,
        project_id,
        source_module,
        source_id,
        target_module,
        target_id,
        target_field,
        propagation_origin,
    )
    return conflict


async def resolve(
    *,
    db: AsyncSession,
    conflict_id: uuid.UUID,
    user_id: uuid.UUID,
    resolution: Resolution,
    merge_value: str | None = None,
) -> CrossModuleConflict:
    """用户调解一条 pending 冲突。

    final_value 写入策略：
      - keep_manual → manual_value
      - accept_new  → upstream_value
      - merge       → merge_value（必传）

    异常:
        ConflictNotFoundError: conflict_id 不存在
        ConflictAlreadyResolvedError: 当前 status != 'pending'
        ConflictMergeValueRequiredError: resolution='merge' 但 merge_value 为 None
        ValueError: resolution 不在合法集合内

    副作用:
        UPDATE conflict + append_audit_log(event_type='cross_module_conflict_resolved')
    """
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(
            f"resolution 必须是以下之一: {sorted(VALID_RESOLUTIONS)}, 收到 {resolution!r}"
        )
    if resolution == "merge" and merge_value is None:
        raise ConflictMergeValueRequiredError("merge 决议必须提供 merge_value")

    conflict = await _load_pending_or_raise(db, conflict_id)

    if resolution == "keep_manual":
        conflict.final_value = conflict.manual_value
    elif resolution == "accept_new":
        conflict.final_value = conflict.upstream_value
    else:  # merge
        conflict.final_value = merge_value

    conflict.resolution = resolution
    conflict.resolved_by = user_id
    conflict.resolved_at = datetime.now(timezone.utc)
    conflict.status = "resolved"
    await db.flush()

    await _write_resolve_audit(
        db=db, conflict=conflict, user_id=user_id, resolution_label=resolution
    )
    return conflict


async def auto_resolve_system_recompute(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    source_module: str,
    source_id: uuid.UUID,
    target_module: str,
    target_id: uuid.UUID,
    target_field: str,
    new_value: str | None,
    manual_value: str | None = None,
    user_id: uuid.UUID | None = None,
) -> CrossModuleConflict:
    """系统自动重算（汇率刷新、公式联动等）— 直接写 status='resolved' resolution='accept_new'。

    场景：上游是系统重算（非用户操作），即便目标 manual_override，
    依然采用新值并留痕，避免阻塞自动化链路。

    参数:
        new_value: 上游计算后的新值（写入 final_value 与 upstream_value）
        manual_value: 目标当前手工值（仅留痕，不影响 final_value）
        user_id: 写审计时的 user_id（None 表示系统行为，audit_log.user_id=NULL）

    返回:
        新建的 CrossModuleConflict（status='resolved', resolution='accept_new'）
    """
    now = datetime.now(timezone.utc)
    conflict = CrossModuleConflict(
        id=uuid.uuid4(),
        project_id=project_id,
        source_module=source_module,
        source_id=source_id,
        target_module=target_module,
        target_id=target_id,
        target_field=target_field,
        upstream_value=new_value,
        manual_value=manual_value,
        final_value=new_value,
        resolution="accept_new",
        resolved_by=user_id,
        resolved_at=now,
        status="resolved",
    )
    db.add(conflict)
    await db.flush()

    # 留痕：审计 event_type 仍用 cross_module_conflict_resolved
    # resolution_label 写为 'system_auto' 表明这是系统自动决策（不同于用户主动 accept_new）
    await _write_resolve_audit(
        db=db,
        conflict=conflict,
        user_id=user_id,
        resolution_label="system_auto",
    )

    logger.info(
        "cross_module_conflict 系统自动重算 conflict_id=%s project=%s %s.%s -> %s.%s.%s",
        conflict.id,
        project_id,
        source_module,
        source_id,
        target_module,
        target_id,
        target_field,
    )
    return conflict


# ---------------------------------------------------------------------------
# 公共 API — 查询
# ---------------------------------------------------------------------------


async def list_pending(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    limit: int = 100,
) -> list[CrossModuleConflict]:
    """仅返回 status='pending' 的冲突记录（前端 banner / 守门规则用）。"""
    stmt = (
        select(CrossModuleConflict)
        .where(
            CrossModuleConflict.project_id == project_id,
            CrossModuleConflict.status == "pending",
        )
        .order_by(CrossModuleConflict.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_by_project(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    status: str | None = None,
    target_module: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CrossModuleConflict]:
    """按项目列出冲突记录，可选状态 + 目标模块过滤。

    参数:
        status: 'pending' / 'resolved' / 'auto_skipped'，None=不过滤
        target_module: 目标模块标识匹配，None=不过滤
        limit: 单次最多返回条数（默认 100）
        offset: 分页偏移（默认 0）

    返回:
        CrossModuleConflict 列表，按 created_at DESC 排序。
    """
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(
            f"status 必须是以下之一: {sorted(VALID_STATUSES)}, 收到 {status!r}"
        )

    stmt = select(CrossModuleConflict).where(
        CrossModuleConflict.project_id == project_id
    )
    if status is not None:
        stmt = stmt.where(CrossModuleConflict.status == status)
    if target_module is not None:
        stmt = stmt.where(CrossModuleConflict.target_module == target_module)

    stmt = (
        stmt.order_by(CrossModuleConflict.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_pending(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
) -> int:
    """pending 冲突计数（前端 badge / 守门规则阈值用）。"""
    stmt = (
        select(func.count())
        .select_from(CrossModuleConflict)
        .where(
            CrossModuleConflict.project_id == project_id,
            CrossModuleConflict.status == "pending",
        )
    )
    result = await db.execute(stmt)
    count = result.scalar_one()
    return int(count or 0)


# ---------------------------------------------------------------------------
# Hook：联动前置守卫（Task 7.2）
# ---------------------------------------------------------------------------


CheckResult = Literal["allow", "block_enqueued", "auto_resolved"]


async def _check_manual_override_before_propagate(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    source_module: str,
    source_id: uuid.UUID,
    target_module: str,
    target_id: uuid.UUID,
    target_field: str,
    new_value: str | None,
    current_value: str | None,
    is_manual_override: bool,
    user_id: uuid.UUID | None,
    propagation_origin: PropagationOrigin = "user_edit",
) -> CheckResult:
    """检查目标字段的 ``manual_override`` 标记决定是否允许联动写入。

    本 hook 是 ``wp_disclosure_sync_service.sync_from_workpaper`` /
    ``cross_ref_service.CrossRefService.propagate_with_manual_override_check``
    的前置守卫，按 design §1278~§1432、Req 7 AC 1/2/6/7 实现。

    返回:
        - ``"allow"``           目标字段无 manual_override，调用方继续写入
        - ``"block_enqueued"``  目标字段有 manual_override + 用户触发联动
                               已 enqueue 一条 pending 冲突，调用方必须 abort 写入
        - ``"auto_resolved"``   propagation_origin='system_recompute'（汇率刷新等）
                               已 auto_resolve 写入新值并留痕，调用方可继续写入
    """
    if not is_manual_override:
        return "allow"

    if propagation_origin == "system_recompute":
        await auto_resolve_system_recompute(
            db=db,
            project_id=project_id,
            source_module=source_module,
            source_id=source_id,
            target_module=target_module,
            target_id=target_id,
            target_field=target_field,
            new_value=new_value,
            manual_value=current_value,
            user_id=user_id,
        )
        return "auto_resolved"

    # user_edit + manual_override → 拦截，入队 pending 冲突等待调解
    await enqueue(
        db=db,
        project_id=project_id,
        source_module=source_module,
        source_id=source_id,
        target_module=target_module,
        target_id=target_id,
        target_field=target_field,
        upstream_value=new_value,
        manual_value=current_value,
        user_id=user_id,
        propagation_origin="user_edit",
    )
    return "block_enqueued"
