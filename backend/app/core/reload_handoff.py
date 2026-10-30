"""热重载新旧 worker 交接的应用侧（spec backend-startup-and-request-overhead R2.3 / R2.4 / R2.6）。

``backend/reload_supervisor.py`` 起的每个 worker 带交接事件：ready（本进程设：uvicorn 已开始 accept）、
stop（父进程设：请求退出）、handoff_stop（父进程设：本次退出是热交接）、primary（父进程设：旧 worker 已退出）、
primary_ready / primary_failed（本进程设：推迟的 singleton 已成功完成 / 关键任务失败）。候选身份随 worker
单独传入，只让 overlap 候选在 ready 前全量验证 lazy routes。

模式：
- ``standalone``：没有交接父进程（首次启动不带 ``--reload``、测试、脚本）—— 与原来相同，启动时全部执行；
- ``overlap``：交接父进程起的 worker；``StartupTaskSpec.singleton`` 的任务在本进程成为 primary 之前不执行，
  报告记 ``deferred``，成为 primary 后在后台按原顺序执行并回写报告；
- ``never``（``GT_NEVER_PRIMARY=1``，优先于以上两种）：那些任务永不执行，供另起的实例做测量，不和主实例抢后台任务。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, Sequence

logger = logging.getLogger("audit_platform")

Mode = Literal["standalone", "overlap", "never"]

#: 父进程写最近一次重载结果的文件（父进程设置，worker 继承）；``/api/health`` 的 ``reload.last`` 读它。
STATUS_FILE_ENV = "GT_RELOAD_STATUS_FILE"
NEVER_PRIMARY_ENV = "GT_NEVER_PRIMARY"


@dataclasses.dataclass(frozen=True)
class _Handoff:
    ready: Any
    stop: Any
    handoff_stop: Any
    primary: Any
    primary_ready: Any
    primary_failed: Any
    candidate: bool
    error_file: str


_handoff: _Handoff | None = None
_handoff_pre_drain_complete = False


def attach(
    *,
    ready: Any,
    stop: Any,
    handoff_stop: Any,
    primary: Any,
    primary_ready: Any,
    primary_failed: Any,
    candidate: bool,
    error_file: str,
) -> None:
    """worker 进程入口在 ``server.run`` 之前调用（``reload_supervisor._WorkerTarget``）。"""
    global _handoff, _handoff_pre_drain_complete
    _handoff = _Handoff(
        ready=ready,
        stop=stop,
        handoff_stop=handoff_stop,
        primary=primary,
        primary_ready=primary_ready,
        primary_failed=primary_failed,
        candidate=candidate,
        error_file=error_file,
    )
    _handoff_pre_drain_complete = False


def detach() -> None:
    """测试用：回到 standalone。"""
    global _handoff, _handoff_pre_drain_complete
    _handoff = None
    _handoff_pre_drain_complete = False


def mode() -> Mode:
    if os.environ.get(NEVER_PRIMARY_ENV) == "1":
        return "never"
    return "overlap" if _handoff is not None else "standalone"


def is_candidate() -> bool:
    """当前进程是否为 overlap 重载候选；首次 worker 与 standalone 均为 False。"""
    return bool(_handoff and _handoff.candidate)


def is_primary() -> bool:
    current = mode()
    if current == "never":
        return False
    return current == "standalone" or bool(_handoff and _handoff.primary.is_set())


def primary_transition_state() -> str:
    """供健康检查读取，不暴露进程事件对象。"""
    if _handoff is None:
        return "ready"
    if _handoff.primary_failed.is_set():
        return "failed"
    if _handoff.primary_ready.is_set():
        return "ready"
    return "pending"


def mark_primary_failed(reason: str) -> None:
    """记录 deferred critical 失败并通知父进程；原因文件只供父进程读取。"""
    if _handoff is None:
        return
    try:
        Path(_handoff.error_file).write_text(str(reason)[-600:], encoding="utf-8")
    except OSError:
        pass
    _handoff.primary_failed.set()


def mark_primary_ready() -> None:
    if _handoff is not None and not _handoff.primary_failed.is_set():
        _handoff.primary_ready.set()


def defers_singletons() -> bool:
    """现在执行 singleton 启动任务要不要推迟。"""
    return not is_primary()


def deferred_detail() -> str:
    if mode() == "never":
        return f"{NEVER_PRIMARY_ENV}=1：本实例不执行（避免与主实例抢后台任务）"
    return "热重载交接中：等旧 worker 退出后由本进程执行"


async def wait_primary(stop_event: asyncio.Event | None = None, *, poll_s: float = 0.2) -> bool:
    """等到本进程成为 primary（返回 True）；never 模式或 ``stop_event`` 置位时返回 False。"""
    while not is_primary():
        if mode() == "never" or (stop_event is not None and stop_event.is_set()):
            return False
        await asyncio.sleep(poll_s)
    return True


def schedule_deferred(specs: Sequence[Any], ctx: Any) -> None:
    """overlap worker 在启动完成后等待 primary，再串行执行 singleton 并回报接管结果。

    即使 ``specs`` 为空也安排信号任务，保证父进程只在 lifespan 启动完成且 primary 已授予后收到
    ``primary_ready``。任务进 ``ctx.worker_tasks``，关闭时与其余 worker 一起取消。
    """
    if mode() == "overlap":
        ctx.worker_tasks.append(asyncio.create_task(_run_when_primary(tuple(specs), ctx)))


async def _run_when_primary(specs: tuple[Any, ...], ctx: Any) -> None:
    from app.core import startup_registry as sr

    if not await wait_primary(ctx.stop_event):
        return
    if specs:
        logger.warning("[热重载] 旧 worker 已退出，开始执行推迟的 %d 个启动任务", len(specs))
    critical_failures: list[str] = []
    try:
        for spec in specs:
            if ctx.stop_event.is_set():
                return
            # 服务已开始 accept，不能再让异常退出 lifespan；仍按原 criticality 判断接管是否 degraded。
            once = dataclasses.replace(spec, singleton=False, criticality="best_effort")
            result = (await sr.run_startup_tasks([once], context=ctx, report=False))[0]
            sr.update_task_result(spec.name, status=result.status, detail=result.detail, duration_ms=result.duration_ms)
            if result.status == "failed" and spec.criticality == "critical":
                critical_failures.append(f"{spec.name}: {result.detail or 'failed'}")
                logger.error("[热重载] 推迟执行的关键启动任务 %s 失败：%s", spec.name, result.detail)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — 转成接管失败信号，worker 保持可诊断
        critical_failures.append(f"deferred_runner: {type(exc).__name__}: {exc}")
        logger.exception("[热重载] 推迟启动任务执行器异常")

    if critical_failures:
        mark_primary_failed("；".join(critical_failures))
    else:
        mark_primary_ready()


#: 停止 accept 之后、进入 uvicorn 关闭之前留的时间：让已接下的连接把请求读进来。
ACCEPT_GRACE_S = 0.5


def handoff_pre_drain_complete() -> bool:
    """仅当本 worker 已完整执行热交接 pre-drain 时为 True；普通关闭始终为 False。"""
    return _handoff_pre_drain_complete


async def drain_for_handoff(server: Any) -> None:
    """旧 worker 交接退出：停止 accept → SSE 连接收到 ``server_draining`` 并关闭（客户端重连到新 worker）→ 稍等 → uvicorn 优雅关闭。

    - 先停 accept：之后的新连接都由新 worker 接（监听 socket 两边共用）。已接下但请求还没读进来的连接在 uvicorn
      关闭时会被当成空闲连接直接关掉，客户端收到 RST（实测每 0.1 s 轮询一次、4 次交接里出现 1 次）⇒ 留
      ``ACCEPT_GRACE_S`` 让它们读进来，之后按进行中的请求处理完再关。
    - SSE 必须在 should_exit 之前关：uvicorn 关闭时先等全部连接结束才跑 lifespan 关闭，长连接不先关就会拖到超时被强杀。
    """
    from app.core.runtime_state import shutdown_state
    from app.core.sse_registry import sse_registry

    global _handoff_pre_drain_complete
    shutdown_state.start_draining()
    logger.warning("[热重载] 新 worker 已就绪，本进程排空后退出（SSE 连接 %d 个）", sse_registry.active_count)
    completed = False
    try:
        for listener in getattr(server, "servers", None) or ():
            listener.close()
        await sse_registry.close_all()
        await asyncio.sleep(ACCEPT_GRACE_S)
        completed = True
    finally:
        _handoff_pre_drain_complete = completed
        server.should_exit = True


_PUBLIC_STATUS_KEYS = {
    "at", "result", "duration_s", "reason", "forced_stop", "phase",
    "spawn_to_ready_s", "ready_to_old_exit_s", "old_exit_to_primary_ready_s",
}
_WINDOWS_PATH_RE = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s；,]+")


def _public_last_status(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    from app.core.startup_registry import desensitize_detail

    public = {key: value[key] for key in _PUBLIC_STATUS_KEYS if key in value}
    reason = desensitize_detail(public.get("reason"))
    if reason:
        public["reason"] = _WINDOWS_PATH_RE.sub("[PATH]", reason)
    return public


def status_snapshot() -> dict[str, Any]:
    """公开健康状态：只给阶段 / 耗时 / 脱敏原因，不暴露 worker PID。"""
    last: Any = None
    path = os.environ.get(STATUS_FILE_ENV)
    if path:
        try:
            last = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = None
    return {
        "mode": mode(),
        "primary": is_primary(),
        "primary_state": primary_transition_state(),
        "candidate": is_candidate(),
        "last": _public_last_status(last),
    }
