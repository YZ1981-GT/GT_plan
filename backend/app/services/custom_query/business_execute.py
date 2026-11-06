"""业务视图查询执行主体（AQF 任务 4：router 主体迁移；N3 净减行数约束）。

路由 `routers/custom_query.execute_query` 只保留 HTTP 层（响应头、错误映射、审计），
主逻辑移到本函数；签名与路由的 `execute_query` 兼容，以保留任务 0 清单里的 monkeypatch 点。

接入版本向量（§4.4）与运行记录（§5.3）：
- adapter.execute 返回 dict 里可能带 ``_version_hash``（内部键）与 ``version``；
- 记录登记在 SAVEPOINT 内，失败不阻断查询，响应追加 ``run`` 键（R1.5/R1.6）。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from functools import partial
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def execute_business_query(
    body: Any,
    *,
    user: Any,
    db: AsyncSession,
    origin: str = "direct",
    template_id: uuid.UUID | None = None,
) -> dict:
    """执行业务视图查询并登记运行记录（路由主体，供 execute_query 和 execute_template 调用）。

    返回 dict（含 run 键）；异常由调用方的路由层映射为 HTTP 响应。
    """
    from app.services.custom_query.audit_helper import record_query_rejected
    from app.services.custom_query.business_fetchers import business_fetcher
    from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
    from app.services.custom_query.query_runs import normalize_definition, record_run

    source = getattr(body, "source", "") or ""
    pid = getattr(body, "project_id", None)
    year = getattr(body, "year", None)
    filters = getattr(body, "filters", {}) or {}

    # 唯一执行路径（ExecuteCompatibilityAdapter → QueryOrchestrator）
    adapter = ExecuteCompatibilityAdapter(business_fetcher=partial(business_fetcher, user=user))
    result = await adapter.execute(body, user=user, db=db)

    if result.get("cache_hit"):
        # 由调用方（路由）设 X-Cache 响应头；这里只让标记穿透
        pass

    # ── 审计日志（关键来源按 60s 节流，quiet 路径跳过）──────────────────
    _SENSITIVE_PREFIXES = ("workpaper:", "consol_unit:", "disclosure_note:", "adj_", "disclosure")
    if source.startswith(_SENSITIVE_PREFIXES) or source in ("workpaper", "adjustment", "disclosure"):
        try:
            from app.core.redis import get_redis
            from app.services.custom_query.audit_helper import record_query_execution
            redis = await get_redis()
            await record_query_execution(
                redis=redis,
                user_id=user.id,
                source=source,
                filters=filters,
                project_id=pid,
                action="custom_query.execute",
                details={
                    "source": source,
                    "year": year,
                    "filters": {k: v for k, v in filters.items()
                                if not isinstance(v, (dict, list)) or len(str(v)) < 200},
                    "row_count": result.get("total", 0),
                    "has_error": "error" in result,
                },
            )
        except Exception as audit_e:
            logger.warning("audit_log enqueue failed for custom_query: %s", audit_e)

    # ── 登记运行记录（AQF §5.3）───────────────────────────────────────────
    run_info: dict[str, Any] = {"recorded": False, "reason": "未采集到版本向量"}
    try:
        version_hash: str = result.pop("_version_hash", None) or ""
        version_dict: dict = result.get("version", {})
        if version_hash:
            definition = normalize_definition(body, entry="business")
            run_info = await record_run(
                db,
                user_id=user.id,
                entry="business",
                origin=origin,
                template_id=template_id,
                project_id=pid,
                year=year,
                source_key=source,
                definition=definition,
                scope={"project_id": str(pid) if pid else None, "year": year},
                version_vector=version_dict,
                vector_hash=version_hash,
                vector_weak=version_dict.get("weak", False),
                captured_at=datetime.now(timezone.utc),
                last_total=result.get("total"),
            )
    except Exception as run_exc:
        logger.warning("AQF 运行记录登记异常: %s", run_exc)
        run_info = {"recorded": False, "reason": f"运行记录异常：{type(run_exc).__name__}"}

    result["run"] = run_info
    return result


__all__ = ["execute_business_query"]
