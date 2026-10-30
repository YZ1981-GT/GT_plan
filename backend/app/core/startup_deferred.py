"""ready 之后才跑的重阶段调度（从 ``startup_registry`` 抽出）。

``startup_registry`` 承载的是**冻结的启动任务有序序列**（``STARTUP_TASKS`` + 两个顺序/关键性断言），
而这里三件事的共同点是「不在 ready 路径上、都要排进 ``gc_tuning.heavy_phase``」：

- 底稿同步注册表预热（primary-only，等事件积压恢复后才跑，结束后等空闲窗口 freeze）；
- lazy route 验证（候选在 ready 前必须全量物化，首次启动只在后台低强度验证）；
- 开发环境 OpenAPI 后台预生成（生产三条 docs 路由根本不注册）。

拆出来的理由是行数门（``backend/scripts/file_size_whitelist.txt``）要求打磨让文件变小：
这一组与冻结序列无耦合，调用方只通过 ``STARTUP_TASKS`` 里的 ``run`` 引用它们。
``startup_registry`` 仍 re-export 这四个名字，既有测试与外部引用不变。

# spec: runtime-performance-and-reload-hardening-followup 任务 5
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 只为类型：避免与 startup_registry 形成 import 期循环
    from app.core.startup_registry import StartupContext

logger = logging.getLogger(__name__)


def task_schedule_workpaper_sync_prewarm(ctx: StartupContext) -> None:
    """primary worker 在事件恢复后串行预热；结束后等 HTTP 连续空闲才 freeze。"""
    from app.core.gc_tuning import configure_gc
    from app.services.workpaper_sync.startup_prewarm import warm_workpaper_sync_registry

    configure_gc()
    ctx.worker_tasks.append(asyncio.create_task(
        run_workpaper_prewarm(ctx, warm_workpaper_sync_registry)
    ))


async def run_workpaper_prewarm(ctx: StartupContext, work: Callable[[], Awaitable[None]]) -> None:
    """候选成为 primary 前不重复预热；事件积压先恢复，再让预热占重阶段锁。"""
    from app.core import reload_handoff
    from app.core.gc_tuning import run_then_freeze

    if not await reload_handoff.wait_primary(ctx.stop_event):
        return
    event_task = ctx.extras.get("event_drain_task")
    if isinstance(event_task, asyncio.Task):
        try:
            await asyncio.shield(event_task)
        except Exception:  # 事件恢复自己已记录失败，不能让 best-effort 预热永不运行
            pass
    if ctx.stop_event.is_set():
        return
    await run_then_freeze(work, stop_event=ctx.stop_event)


def task_schedule_lazy_route_verification(ctx: StartupContext) -> None:
    """候选在 ready 前全量验证；首次启动仍在后台低强度验证。"""
    from app.core import reload_handoff
    from app.core.lazy_api_routes import materialize_all, schedule_background_verification
    from app.core.startup_registry import update_task_result

    app = ctx.extras.get("app")
    if reload_handoff.is_candidate():
        if app is None:
            raise RuntimeError("候选 lazy route 验证缺少应用对象")
        started = time.perf_counter()
        failures = materialize_all(app.router.routes)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if failures:
            head = "；".join(f"{path} {reason}" for path, reason in failures[:3])
            raise RuntimeError(f"候选 lazy route 验证失败 {len(failures)} 项：{head}")
        logger.info("[lazy-routes] 候选 ready 前物化完成，耗时 %dms", duration_ms)
        return

    schedule_background_verification(
        app,
        ctx.worker_tasks,
        lambda status, detail: update_task_result("verify_lazy_routes", status=status, detail=detail),
    )


def task_schedule_openapi_prewarm(ctx: StartupContext) -> None:
    """开发环境后台单飞预生成 OpenAPI；生产三条 docs 路由根本不注册。"""
    from app.core.config import settings
    from app.core.openapi_runtime import schedule_openapi_prewarm

    schedule_openapi_prewarm(ctx.extras.get("app"), ctx.worker_tasks, settings.APP_ENV)
