"""Worker 通用辅助 — Spec C R10 Sprint 1.1

write_heartbeat:
    每个 worker 主循环每轮调用一次，写 Redis key worker_heartbeat:{name}（TTL=60s）。
    被 EventCascadeHealthService 用于探测 worker 是否存活。
    Redis 不可用时静默降级（仅日志），不阻断 worker。

设计依据：
- design.md D1：心跳走 Redis 不走 PG（TTL 自然过期 + 写入频率高 + 读取速度快）
- value 含 last_heartbeat / pid / version / hostname 四字段
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 60s = 2 倍心跳间隔（worker 30s 一次），过期视为 miss
_HEARTBEAT_TTL_SECONDS = 60


async def write_heartbeat(worker_name: str, *, version: str = "1.0") -> None:
    """写入 worker 心跳到 Redis（不可用时降级）。

    Args:
        worker_name: worker 名称（写入 key worker_heartbeat:{worker_name}）
        version: 可选版本号，默认 "1.0"
    """
    try:
        from app.core.redis import redis_client  # 延迟 import 避免循环
    except Exception:  # pragma: no cover - 模块级 import 失败极罕见
        return

    if redis_client is None:
        return

    try:
        payload = {
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "version": version,
            "hostname": socket.gethostname(),
        }
        await redis_client.setex(
            f"worker_heartbeat:{worker_name}",
            _HEARTBEAT_TTL_SECONDS,
            json.dumps(payload),
        )
    except Exception as e:  # pragma: no cover - Redis 临时故障
        logger.debug("Failed to write heartbeat for %s: %s", worker_name, e)


__all__ = ["write_heartbeat"]
