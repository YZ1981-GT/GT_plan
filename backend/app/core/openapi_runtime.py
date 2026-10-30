"""OpenAPI/docs 运行时策略（runtime-performance-and-reload-hardening-followup R5.4）。

生产/预发布不注册三个公开文档端点；开发环境用自定义 async `/openapi.json`，schema 在工作线程
单飞生成，普通 API 不会被首次 2500+ 路由遍历同步卡住。后台预热与其他 CPU/GIL 重阶段共用锁。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

PRODUCTION_ENVS = frozenset({"prod", "production", "staging"})
OPENAPI_PREWARM_DELAY_S = float(os.getenv("GT_OPENAPI_PREWARM_DELAY", "90"))
_TASK_STATE_KEY = "_gt_openapi_task"


def docs_enabled(app_env: str | None) -> bool:
    return (app_env or "dev").strip().lower() not in PRODUCTION_ENVS


def fastapi_docs_kwargs(_app_env: str | None) -> dict[str, None]:
    """始终关掉 FastAPI 同步默认路由；开发环境稍后安装 async 版本。"""
    return {"openapi_url": None, "docs_url": None, "redoc_url": None}


async def _generate(app: FastAPI) -> dict[str, Any]:
    from app.core.gc_tuning import heavy_phase

    async with heavy_phase("openapi-schema"):
        # 只调 FastAPI 自己的 schema 生成，不再 materialize_all；候选路由已在 ready 前物化，
        # 首次 worker 的后台 verifier 也走同一重阶段锁。
        return await asyncio.to_thread(app.openapi)


async def ensure_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """同一 app 的并发调用共用一个 Task；失败后允许下一次重试。"""
    if app.openapi_schema is not None:
        return app.openapi_schema
    task = getattr(app.state, _TASK_STATE_KEY, None)
    if (
        not isinstance(task, asyncio.Task)
        or task.cancelled()
        or (task.done() and task.exception() is not None)
    ):
        task = asyncio.create_task(_generate(app))
        setattr(app.state, _TASK_STATE_KEY, task)
    try:
        return await asyncio.shield(task)
    except Exception:
        if getattr(app.state, _TASK_STATE_KEY, None) is task:
            delattr(app.state, _TASK_STATE_KEY)
        raise


def schedule_openapi_prewarm(app: FastAPI | None, worker_tasks: list[asyncio.Task], app_env: str) -> bool:
    if app is None or not docs_enabled(app_env):
        return False

    async def delayed() -> None:
        await asyncio.sleep(OPENAPI_PREWARM_DELAY_S)
        try:
            await ensure_openapi_schema(app)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            import logging

            logging.getLogger("audit_platform").warning("[启动] OpenAPI 后台预生成失败：%s", exc)

    worker_tasks.append(asyncio.create_task(delayed()))
    return True


def install_deferred_docs(app: FastAPI, app_env: str) -> bool:
    """开发环境安装 docs/redoc 与异步 schema 路由；生产三路径都不存在。"""
    if not docs_enabled(app_env):
        return False

    async def openapi_json():
        try:
            schema = await ensure_openapi_schema(app)
            return JSONResponse(schema)
        except Exception as exc:  # 文档能力失败不影响业务 API
            return JSONResponse(
                {"detail": f"OpenAPI 生成失败：{type(exc).__name__}"},
                status_code=503,
                headers={"Retry-After": "5"},
            )

    async def swagger_docs():
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")

    async def redoc_docs():
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")

    app.add_api_route("/openapi.json", openapi_json, include_in_schema=False)
    app.add_api_route("/docs", swagger_docs, include_in_schema=False)
    app.add_api_route("/redoc", redoc_docs, include_in_schema=False)
    return True
