"""Gate evaluation ID 幂等令牌存储 — R1 需求 3

提供 gate_eval_id 的 5 分钟 TTL 存取，用于：

1. ``SignReadinessService`` / ``ArchiveReadinessService`` 每次评估后生成
   一个全新 ``gate_eval_id``，写入 Redis key ``gate_eval:{id}``（TTL 300s）。
2. ``POST /api/signatures/sign`` 校验请求里携带的 ``gate_eval_id`` 仍
   存活、对应 ``project_id`` 与 ``gate_type`` 一致、且 ``ready=True``，
   否则返回 ``GATE_STALE``。

Redis 不可用时自动降级到本地进程字典（带过期清理），保证本机开发/单元
测试场景不抛异常。降级模式在首次写入时打印一条 warning。

**gate_eval_id 与 GateEvaluateResult.trace_id 的区别**：

- ``trace_id`` 用于执行链路追踪（trace_events 落库），每次评估生成，
  可能被 GateEngine 内部幂等缓存命中而复用。
- ``gate_eval_id`` 是面向客户端的"签字幂等令牌"，只由本门面生成，
  携带 ready 决策供后续签字请求核验。两者职责分离。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

_logger = logging.getLogger(__name__)


# 5 分钟 TTL，按 v1.4 需求 3 验收标准 5
GATE_EVAL_TTL_SECONDS: int = 300

_REDIS_KEY_PREFIX = "gate_eval:"

# ------------------------------------------------------------------
# 本地降级存储
# ------------------------------------------------------------------
#
# Redis 不可用时临时落在进程内字典，结构：
#   {eval_id: (payload_dict, expires_at_epoch)}
# 使用锁保证并发安全；惰性清理（每次写入/读取顺便剔除过期项）。

_local_store: dict[str, tuple[dict[str, Any], float]] = {}
_local_store_lock: asyncio.Lock | None = None  # 懒初始化，避免模块导入阶段无事件循环


def _get_lock() -> asyncio.Lock:
    global _local_store_lock
    if _local_store_lock is None:
        _local_store_lock = asyncio.Lock()
    return _local_store_lock


def _prune_local() -> None:
    now = time.monotonic()
    expired = [k for k, (_, exp) in _local_store.items() if exp <= now]
    for k in expired:
        _local_store.pop(k, None)


# ------------------------------------------------------------------
# Redis 客户端获取（容错）
# ------------------------------------------------------------------

async def _get_redis_client():
    """尝试返回 Redis 客户端。获取失败返回 None 进入降级模式。"""
    try:
        from app.core.redis import redis_client
        # ping 一下确认连通；不阻塞超过 0.5s
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[gate_eval_store] Redis ping 失败，降级本地字典: %s", exc)
            return None
        return redis_client
    except Exception as exc:  # noqa: BLE001
        _logger.warning("[gate_eval_store] Redis 客户端获取失败，降级: %s", exc)
        return None


# ------------------------------------------------------------------
# 对外 API
# ------------------------------------------------------------------

async def store_gate_eval(
    *,
    project_id: uuid.UUID,
    gate_type: str,
    ready: bool,
    decision: str,
    ttl_seconds: int = GATE_EVAL_TTL_SECONDS,
) -> tuple[str, datetime]:
    """生成新 ``gate_eval_id`` 并写入存储。

    Returns
    -------
    (gate_eval_id, expires_at_utc)
    """
    eval_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc.timestamp() + ttl_seconds
    payload = {
        "project_id": str(project_id),
        "gate_type": gate_type,
        "ready": bool(ready),
        "decision": str(decision),
        "created_at": now_utc.isoformat(),
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
    }
    redis = await _get_redis_client()
    if redis is not None:
        try:
            await redis.set(
                _REDIS_KEY_PREFIX + eval_id,
                json.dumps(payload, ensure_ascii=False),
                ex=ttl_seconds,
            )
            return eval_id, datetime.fromtimestamp(expires_at, tz=timezone.utc)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[gate_eval_store] Redis SET 失败，降级: %s", exc)

    # 本地降级
    async with _get_lock():
        _prune_local()
        _local_store[eval_id] = (payload, time.monotonic() + ttl_seconds)
    return eval_id, datetime.fromtimestamp(expires_at, tz=timezone.utc)


async def get_gate_eval(eval_id: str) -> dict[str, Any] | None:
    """读取 payload；不存在或已过期返回 None。"""
    if not eval_id:
        return None
    redis = await _get_redis_client()
    if redis is not None:
        try:
            raw = await redis.get(_REDIS_KEY_PREFIX + eval_id)
            if raw is None:
                # Redis 正常但 key 不在：也检查本地（可能曾经降级写过）
                pass
            else:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    return json.loads(raw)
                except Exception:  # noqa: BLE001
                    _logger.warning(
                        "[gate_eval_store] 无法反序列化 Redis payload eval_id=%s", eval_id
                    )
                    return None
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[gate_eval_store] Redis GET 失败，退回本地: %s", exc)

    async with _get_lock():
        _prune_local()
        entry = _local_store.get(eval_id)
        if entry is None:
            return None
        payload, expires = entry
        if expires <= time.monotonic():
            _local_store.pop(eval_id, None)
            return None
        return dict(payload)


async def validate_gate_eval(
    eval_id: str,
    *,
    project_id: uuid.UUID,
    gate_type: str,
    require_ready: bool = True,
) -> tuple[bool, str]:
    """校验 gate_eval_id 是否可用于签字/归档。

    Returns
    -------
    (is_valid, reason)
        ``reason`` 在 is_valid=False 时给出 ``GATE_STALE`` 子码，可直接
        拼到 HTTPException detail。
    """
    payload = await get_gate_eval(eval_id)
    if payload is None:
        return False, "GATE_EVAL_NOT_FOUND_OR_EXPIRED"
    if payload.get("project_id") != str(project_id):
        return False, "GATE_EVAL_PROJECT_MISMATCH"
    if payload.get("gate_type") != gate_type:
        return False, "GATE_EVAL_TYPE_MISMATCH"
    if require_ready and not payload.get("ready"):
        return False, "GATE_EVAL_NOT_READY"
    return True, "OK"


async def clear_gate_eval(eval_id: str) -> None:
    """删除令牌（供签字成功后消费一次即失效，可选调用）。"""
    if not eval_id:
        return
    redis = await _get_redis_client()
    if redis is not None:
        try:
            await redis.delete(_REDIS_KEY_PREFIX + eval_id)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[gate_eval_store] Redis DELETE 失败: %s", exc)

    async with _get_lock():
        _local_store.pop(eval_id, None)


# ------------------------------------------------------------------
# 测试钩子
# ------------------------------------------------------------------


def _reset_local_for_tests() -> None:
    """仅单测使用：清空本地字典。"""
    _local_store.clear()
