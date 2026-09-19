"""高级查询审计节流策略 — advanced-query-module Task 15.4。

design.md §Components 11「WritebackPreview + SnapshotWriter（回写预览与审计）」的
审计策略单点收敛（R14.3 / R14.4）：

- **回写 (writeback) 与跨 sheet 溯源 (cross_sheet_trace)**：逐次记录（**不节流**），
  记录 *操作者 / UTC 秒级时间戳 / 操作类型 / 目标 addr_id 集合 / 新旧值 / 结果*。
- **查询执行 (query_execution)**：按 **60s 窗口**节流为 1 条
  （复用 ``audit_throttle.should_record``，``window_seconds=60``）。

本模块是高级查询审计的**唯一接线入口**：router 层的回写 / 溯源 / 查询执行审计统一
调用本模块的 ``record_writeback`` / ``record_cross_sheet_trace`` /
``record_query_execution``，避免节流策略散落在各端点内联实现（此前 60s 窗口未生效，
两处查询执行审计用的是 ``should_record`` 默认 5s 窗口）。

设计约束：
- 所有函数**吞异常**（记 ``logger.warning`` 后返回），审计失败不得阻塞主请求
  （与既有 router 内联审计块 ``try/except`` 语义一致）。「无审计不回写」的事务级
  强一致由 SnapshotWriter（Task 15.3）在回写事务内保证，本模块只负责**审计记录的
  节流策略与字段规范**，不承担回写回滚。
- 消费既有出口：``audit_logger_enhanced.audit_logger.log_action``（异步队列落库 +
  哈希链）与 ``audit_throttle.should_record``（Redis SET NX EX 分布式节流），不重写。

Requirements: 14.3, 14.4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from app.services.audit_logger_enhanced import audit_logger
from app.services.audit_throttle import should_record

logger = logging.getLogger("audit_platform.advanced_query.audit")

# ─── 常量 ────────────────────────────────────────────────────────────────────

# 查询执行审计节流窗口（design §Components 11：60s 窗口聚合为 1 条，R14.4）
QUERY_EXECUTION_THROTTLE_WINDOW_SECONDS = 60

# 操作类型标识
# 回写 / 溯源用 audit_throttle.SENSITIVE_ACTIONS 中登记的动作名，
# 语义上「不节流」由本模块直接调 log_action（不经 should_record）保证。
ACTION_WRITEBACK = "cell_writeback"
ACTION_CROSS_SHEET_TRACE = "cross_sheet_trace"
# 查询执行节流键使用的动作名（**非敏感**，故会被 should_record 节流）
ACTION_QUERY_EXECUTE = "custom_query.execute"

# 结果标识
RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


def _utc_second_timestamp() -> str:
    """UTC 秒级时间戳 ISO 字符串（R14.3「UTC 时间戳，精确到秒」）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_addr_ids(addr_ids: Iterable[str | None] | str | None) -> list[str]:
    """归一目标 addr_id 集合为去重、有序、去空的 list（R14.3「目标 addr_id 集合」）。

    - 接受单个 addr_id 字符串、可迭代集合，或 None。
    - 过滤 None / 空串；去重（保序）。
    """
    if addr_ids is None:
        return []
    if isinstance(addr_ids, str):
        candidates: Iterable[str | None] = [addr_ids]
    else:
        candidates = addr_ids
    seen: set[str] = set()
    result: list[str] = []
    for a in candidates:
        if a and a not in seen:
            seen.add(a)
            result.append(a)
    return result


async def _log_unthrottled(
    *,
    user_id: UUID | str,
    action: str,
    object_type: str,
    object_id: UUID | str | None,
    project_id: UUID | str | None,
    details: dict[str, Any],
) -> bool:
    """逐次记录一条审计（不节流）。审计失败吞异常并返回 False。"""
    try:
        await audit_logger.log_action(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            project_id=project_id,
            details=details,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — 审计失败不阻塞主请求
        logger.warning("advanced-query audit log failed (action=%s): %s", action, exc)
        return False


# ─── 回写审计（不节流，R14.3 / R14.4）────────────────────────────────────────


async def record_writeback(
    *,
    user_id: UUID | str,
    addr_ids: Iterable[str | None] | str | None,
    old_value: Any = None,
    new_value: Any = None,
    result: str = RESULT_SUCCESS,
    project_id: UUID | str | None = None,
    object_id: UUID | str | None = None,
    object_type: str = "working_paper",
    extra: dict[str, Any] | None = None,
) -> bool:
    """逐次记录回写审计（**不节流**，每次必记，R14.4）。

    记录 R14.3 要求的全部字段：操作者（``user_id``）/ UTC 秒级时间戳（``occurred_at``）
    / 操作类型（``operation``）/ 目标 addr_id 集合（``addr_ids``）/ 新旧值
    （``old_value`` / ``new_value``）/ 结果（``result``）。

    Returns:
        审计是否成功入队（失败已吞异常并记 warning）。
    """
    details: dict[str, Any] = {
        "operation": ACTION_WRITEBACK,
        "occurred_at": _utc_second_timestamp(),
        "addr_ids": _normalize_addr_ids(addr_ids),
        "old_value": old_value,
        "new_value": new_value,
        "result": result,
    }
    if extra:
        details.update(extra)
    return await _log_unthrottled(
        user_id=user_id,
        action=ACTION_WRITEBACK,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        details=details,
    )


# ─── 跨 sheet 溯源审计（不节流，R14.3 / R14.4）────────────────────────────────


async def record_cross_sheet_trace(
    *,
    user_id: UUID | str,
    addr_ids: Iterable[str | None] | str | None,
    result: str = RESULT_SUCCESS,
    project_id: UUID | str | None = None,
    object_id: UUID | str | None = None,
    object_type: str = "working_paper",
    extra: dict[str, Any] | None = None,
) -> bool:
    """逐次记录跨 sheet 溯源审计（**不节流**，每次必记，R14.4）。

    记录操作者 / UTC 秒级时间戳 / 操作类型 / 目标 addr_id 集合 / 结果。溯源为只读
    操作无新旧值，故不含 ``old_value`` / ``new_value``。
    """
    details: dict[str, Any] = {
        "operation": ACTION_CROSS_SHEET_TRACE,
        "occurred_at": _utc_second_timestamp(),
        "addr_ids": _normalize_addr_ids(addr_ids),
        "result": result,
    }
    if extra:
        details.update(extra)
    return await _log_unthrottled(
        user_id=user_id,
        action=ACTION_CROSS_SHEET_TRACE,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        details=details,
    )


# ─── 查询执行审计（60s 窗口节流，R14.4）──────────────────────────────────────


async def record_query_execution(
    *,
    redis: Any | None,
    user_id: UUID | str,
    source: str,
    filters: dict[str, Any],
    details: dict[str, Any],
    action: str = ACTION_QUERY_EXECUTE,
    project_id: UUID | str | None = None,
    object_type: str = "custom_query",
    object_id: UUID | str | None = None,
    window_seconds: int = QUERY_EXECUTION_THROTTLE_WINDOW_SECONDS,
) -> bool:
    """查询执行审计：同一 ``(user_id, source, filters)`` 在 ``window_seconds``（默认
    60s）窗口内聚合为 **1 条**（R14.4）。

    节流判定复用 ``audit_throttle.should_record``（Redis SET NX EX；Redis 不可用时
    降级为全部记录）。节流键的动作名固定用非敏感的 ``custom_query.execute``（确保
    参与节流），落库审计的动作类型标签由 ``action`` 决定（如批量执行传
    ``custom_query.batch_execute``）。

    Args:
        redis:    Redis 客户端（None → should_record 降级为全部记录）。
        user_id:  操作者。
        source:   查询数据源标识（节流键组成）。
        filters:  查询过滤条件（节流键组成）。
        details:  审计明细（落库 details 字段）。
        action:   落库审计动作类型标签（默认 ``custom_query.execute``）。
        window_seconds: 节流窗口（默认 60s）。

    Returns:
        本次是否实际记录了审计（False = 被节流窗口聚合跳过 / 审计失败）。
    """
    try:
        record = await should_record(
            redis=redis,
            user_id=str(user_id),
            source=source,
            filters=filters,
            action=ACTION_QUERY_EXECUTE,  # 非敏感 → 参与节流
            window_seconds=window_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — 节流判定失败不阻塞主请求（保守：不记录）
        logger.warning("advanced-query throttle check failed (source=%s): %s", source, exc)
        return False

    if not record:
        return False

    return await _log_unthrottled(
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        details=details,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 拒绝类审计（advanced-query-hardening-wiring-closure R5.5 / R12.3）
# ─────────────────────────────────────────────────────────────────────────────
#: 查询被时间预算掐断
ACTION_QUERY_TIMEOUT = "custom_query.timeout"
#: 查询因复杂度预算被拒（JOIN 条数 / 分组维度 / 聚合个数超限）
ACTION_QUERY_BUDGET_DENIED = "custom_query.budget_denied"
#: 查询因 PII 字段无权被拒
ACTION_PII_DENIED = "custom_query.pii_denied"

#: error_code → 审计动作名。归属拒绝由 ``OwnershipGuard._audit_denied`` 记
#: ``advanced_query.ownership_denied``，不在此表内（避免同一事件记两条）。
REJECTION_ACTION_BY_ERROR_CODE: dict[str, str] = {
    "QUERY_TIMEOUT": ACTION_QUERY_TIMEOUT,
    "COMPLEXITY_BUDGET_EXCEEDED": ACTION_QUERY_BUDGET_DENIED,
    "PII_FIELD_FORBIDDEN": ACTION_PII_DENIED,
}


def resolve_rejection_action(error_code: str | None) -> str | None:
    """把 error_code 映射为可区分的审计动作名；未登记的返回 None（不记审计）。

    要求「可区分」而非统一记一条「查询失败」：超时、预算超限、PII 越权三者的
    处置完全不同（前者要加筛选、中者要拆查询、后者要走权限申请），审计里混成
    一个动作名等于没记。
    """
    if not error_code:
        return None
    return REJECTION_ACTION_BY_ERROR_CODE.get(str(error_code))


async def record_query_rejected(
    *,
    user_id: UUID | str,
    error_code: str | None,
    source: str | None = None,
    project_id: UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """记录一条查询被拒审计（**不节流**）。

    不节流的理由：这类事件本身就是异常信号，60s 窗口内的重复尝试恰恰是需要被看见
    的模式（例如反复试探无权项目、反复提交超预算查询）。

    审计写入失败**不得**掩盖原始错误响应 —— 故全程吞异常并只返回布尔结果，
    调用方在 except 分支里调用它，原异常照常上抛（R5.5）。
    """
    action = resolve_rejection_action(error_code)
    if action is None:
        return False
    payload: dict[str, Any] = {
        "error_code": str(error_code),
        "recorded_at": _utc_second_timestamp(),
    }
    if source:
        payload["source"] = source
    if details:
        payload.update(details)
    try:
        return await _log_unthrottled(
            user_id=user_id,
            action=action,
            object_type="custom_query",
            object_id=None,
            project_id=project_id,
            details=payload,
        )
    except Exception as exc:  # noqa: BLE001 — 审计失败不掩盖原始错误
        logger.warning("查询拒绝审计写入失败（非致命）: %s", exc)
        return False
