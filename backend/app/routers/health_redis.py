"""Redis 健康检查端点 — GET /api/health/redis

返回 Redis 集群状态：master 状态 / replica 数量 / sentinel 状态 / 内存使用。
集成到现有 /api/health 端点（增加 redis 详情字段）。

Requirements: F5.4
"""

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


async def _get_redis_health_info() -> dict[str, Any]:
    """收集 Redis 健康信息，失败时返回降级状态。"""
    from app.core.redis import redis_client, REDIS_MODE, REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_SERVICE

    result: dict[str, Any] = {
        "mode": REDIS_MODE,
        "master_status": "unavailable",
        "replica_count": 0,
        "sentinel_status": "unavailable",
        "memory_used_mb": None,
        "connected": False,
    }

    if redis_client is None:
        return result

    # 检查 master 连接
    try:
        pong = await redis_client.ping()
        if pong:
            result["master_status"] = "ok"
            result["connected"] = True
    except Exception as e:
        logger.debug("Redis master ping failed: %s", e)
        return result

    # 获取内存使用
    try:
        info = await redis_client.info("memory")
        used_bytes = info.get("used_memory", 0)
        result["memory_used_mb"] = round(used_bytes / (1024 * 1024), 2)
    except Exception:
        pass

    # 获取 replica 信息
    try:
        replication_info = await redis_client.info("replication")
        role = replication_info.get("role", "unknown")
        result["master_role"] = role
        # connected_slaves 字段表示 replica 数量
        result["replica_count"] = replication_info.get("connected_slaves", 0)
    except Exception:
        pass

    # Sentinel 状态（仅 sentinel 模式）
    if REDIS_MODE == "sentinel":
        result["sentinel_service"] = REDIS_SENTINEL_SERVICE
        try:
            from redis.asyncio import Redis as RedisClient

            # 尝试连接第一个 sentinel 获取状态
            sentinel_hosts = []
            for hp in REDIS_SENTINEL_HOSTS.split(","):
                hp = hp.strip()
                if ":" in hp:
                    host, port = hp.rsplit(":", 1)
                    sentinel_hosts.append((host, int(port)))
                else:
                    sentinel_hosts.append((hp, 26379))

            if sentinel_hosts:
                host, port = sentinel_hosts[0]
                sentinel_conn = RedisClient(host=host, port=port, socket_timeout=1.0)
                try:
                    sentinel_info = await sentinel_conn.execute_command(
                        "SENTINEL", "master", REDIS_SENTINEL_SERVICE
                    )
                    # sentinel_info 是一个 flat list: [key, value, key, value, ...]
                    if sentinel_info:
                        result["sentinel_status"] = "ok"
                        # Parse flat list to dict
                        if isinstance(sentinel_info, list):
                            info_dict = {}
                            for i in range(0, len(sentinel_info) - 1, 2):
                                info_dict[sentinel_info[i]] = sentinel_info[i + 1]
                            result["sentinel_master_host"] = info_dict.get("ip", "unknown")
                            result["sentinel_master_port"] = info_dict.get("port", "unknown")
                            result["sentinel_num_slaves"] = info_dict.get("num-slaves", "0")
                            result["sentinel_num_sentinels"] = info_dict.get(
                                "num-other-sentinels", "0"
                            )
                finally:
                    await sentinel_conn.aclose()
        except Exception as e:
            logger.debug("Sentinel status check failed: %s", e)
            result["sentinel_status"] = "unavailable"
    else:
        result["sentinel_status"] = "not_applicable"

    return result


@router.get("/redis")
async def redis_health_check() -> JSONResponse:
    """Redis 健康检查端点。

    返回 Redis 集群详细状态信息。
    200 = Redis 可用，503 = Redis 不可用。
    """
    info = await _get_redis_health_info()

    status_code = 200 if info["connected"] else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if info["connected"] else "unhealthy",
            "redis": info,
        },
    )
