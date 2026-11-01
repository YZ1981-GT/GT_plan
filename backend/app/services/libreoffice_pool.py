"""LibreOffice 有界异步执行器。

每个转换使用独立 UUID profile 和输出目录；进程 stdout/stderr 由
``communicate()`` 同时排空。进程内 semaphore、队列上限和 acquire timeout
阻止 Web worker 在突发请求下无限创建子进程或协程。多 worker 总容量仍须按
``worker 数 × LIBREOFFICE_MAX_CONCURRENCY`` 计算，批 E 再外置主机级调度。
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import weakref
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Process-local admission control. Deployment capacity must multiply this value
# by the number of workers; batch E will move host-wide scheduling out of process.
# ---------------------------------------------------------------------------


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("[LIBREOFFICE_POOL] invalid %s; using %d", name, default)
        return default


def _positive_float_env(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("[LIBREOFFICE_POOL] invalid %s; using %.1f", name, default)
        return default


LIBREOFFICE_MAX_CONCURRENCY = _positive_int_env(
    "LIBREOFFICE_MAX_CONCURRENCY", 2
)
LIBREOFFICE_MAX_QUEUE = _positive_int_env("LIBREOFFICE_MAX_QUEUE", 8)
LIBREOFFICE_ACQUIRE_TIMEOUT_SECONDS = _positive_float_env(
    "LIBREOFFICE_ACQUIRE_TIMEOUT_SECONDS", 5.0
)
LIBREOFFICE_RETRY_AFTER_SECONDS = _positive_int_env(
    "LIBREOFFICE_RETRY_AFTER_SECONDS", 10
)
LIBREOFFICE_REAP_TIMEOUT_SECONDS = _positive_float_env(
    "LIBREOFFICE_REAP_TIMEOUT_SECONDS", 5.0
)

_libreoffice_semaphore = asyncio.Semaphore(LIBREOFFICE_MAX_CONCURRENCY)
_queue_waiters = 0
_active_conversions = 0
_waiter_started: set[float] = set()
_preview_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Gauge, Histogram

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _MetricStub:
        """可链式调用的空指标，保持无 prometheus_client 环境可运行。"""

        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    Counter = Gauge = Histogram = _MetricStub  # type: ignore[misc,assignment]

LIBREOFFICE_QUEUE_DEPTH = Gauge(
    "libreoffice_queue_depth",
    "Number of tasks waiting for a process-local LibreOffice slot",
)
LIBREOFFICE_ACTIVE = Gauge(
    "libreoffice_active_processes",
    "Number of active LibreOffice child processes in this worker",
)
LIBREOFFICE_OLDEST_WAIT_SECONDS = Gauge(
    "libreoffice_oldest_wait_seconds",
    "Age of the oldest request waiting for a LibreOffice slot",
)
LIBREOFFICE_WAIT_SECONDS = Histogram(
    "libreoffice_queue_wait_seconds",
    "Time spent waiting for a process-local LibreOffice slot",
)
LIBREOFFICE_RUN_SECONDS = Histogram(
    "libreoffice_run_seconds",
    "LibreOffice child process execution time",
    labelnames=("format",),
)
LIBREOFFICE_RESULTS = Counter(
    "libreoffice_conversion_total",
    "LibreOffice conversion outcomes",
    labelnames=("result", "format"),
)

# ---------------------------------------------------------------------------
# 4 path fallback for finding soffice binary (Req 8.3)
# ---------------------------------------------------------------------------
_SOFFICE_CANDIDATE_PATHS: tuple[str, ...] = (
    "libreoffice",
    "soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/lib/libreoffice/program/soffice",
)

# Cached soffice path after startup probe
_cached_soffice_path: Optional[str] = None


def _find_soffice() -> Optional[str]:
    """检测 LibreOffice 可执行路径（4+ 路径 fallback）。

    搜索顺序：
    1. PATH 中的 libreoffice / soffice
    2. 环境变量 LIBREOFFICE_PATH 显式指定
    3. Windows 默认安装目录
    4. macOS / Linux 默认安装目录
    """
    global _cached_soffice_path
    if _cached_soffice_path is not None:
        return _cached_soffice_path

    # Check env override first
    env_path = os.environ.get("LIBREOFFICE_PATH")
    if env_path and Path(env_path).exists():
        _cached_soffice_path = env_path
        return env_path

    for cmd in _SOFFICE_CANDIDATE_PATHS:
        if Path(cmd).is_absolute():
            if Path(cmd).exists():
                _cached_soffice_path = cmd
                return cmd
        else:
            path = shutil.which(cmd)
            if path:
                _cached_soffice_path = path
                return path

    return None


def _build_user_installation(profile_dir: Path) -> str:
    """为本次 job 的独立 profile 生成规范 file URI。"""
    return profile_dir.resolve().as_uri()


def get_queue_depth() -> int:
    """返回本 worker 正在等待 semaphore 的请求数。"""
    return _queue_waiters


def _refresh_wait_metrics(now: float | None = None) -> None:
    sampled = time.perf_counter() if now is None else now
    oldest = max(0.0, sampled - min(_waiter_started)) if _waiter_started else 0.0
    LIBREOFFICE_QUEUE_DEPTH.set(_queue_waiters)
    LIBREOFFICE_OLDEST_WAIT_SECONDS.set(oldest)


def get_capacity_snapshot() -> dict[str, int | float]:
    """返回可观测的进程内容量状态。"""
    sampled = time.perf_counter()
    return {
        "active": _active_conversions,
        "waiting": _queue_waiters,
        "oldest_wait_seconds": (
            max(0.0, sampled - min(_waiter_started)) if _waiter_started else 0.0
        ),
        "concurrency_limit": LIBREOFFICE_MAX_CONCURRENCY,
        "queue_limit": LIBREOFFICE_MAX_QUEUE,
    }


def _overloaded(reason: str, message: str) -> HTTPException:
    LIBREOFFICE_RESULTS.labels(result=reason, format="unknown").inc()
    return HTTPException(
        status_code=503,
        detail={"reason": reason, "message": message},
        headers={"Retry-After": str(LIBREOFFICE_RETRY_AFTER_SECONDS)},
    )


async def _acquire_slot(queue_timeout: float) -> None:
    """有界等待一个进程内转换槽；超载时给出可重试响应。"""
    global _active_conversions, _queue_waiters

    if _libreoffice_semaphore.locked() and _queue_waiters >= LIBREOFFICE_MAX_QUEUE:
        raise _overloaded(
            "libreoffice_queue_full",
            "Office 转换队列已满，请稍后重试",
        )

    wait_started = time.perf_counter()
    _queue_waiters += 1
    _waiter_started.add(wait_started)
    _refresh_wait_metrics(wait_started)
    acquire_task = asyncio.create_task(_libreoffice_semaphore.acquire())
    try:
        await asyncio.wait_for(acquire_task, timeout=queue_timeout)
    except asyncio.TimeoutError as exc:
        # 极窄竞态下 acquire 可能已完成；不得泄漏 semaphore permit。
        if acquire_task.done() and not acquire_task.cancelled():
            try:
                if acquire_task.result():
                    _libreoffice_semaphore.release()
            except Exception:
                pass
        raise _overloaded(
            "libreoffice_queue_timeout",
            "Office 转换排队超时，请稍后重试",
        ) from exc
    except asyncio.CancelledError:
        if not acquire_task.done():
            acquire_task.cancel()
        acquired = await asyncio.gather(acquire_task, return_exceptions=True)
        if acquired == [True]:
            _libreoffice_semaphore.release()
        raise
    finally:
        _queue_waiters = max(0, _queue_waiters - 1)
        _waiter_started.discard(wait_started)
        _refresh_wait_metrics()
        LIBREOFFICE_WAIT_SECONDS.observe(time.perf_counter() - wait_started)

    _active_conversions += 1
    LIBREOFFICE_ACTIVE.set(_active_conversions)


def _release_slot() -> None:
    global _active_conversions
    _active_conversions = max(0, _active_conversions - 1)
    LIBREOFFICE_ACTIVE.set(_active_conversions)
    _libreoffice_semaphore.release()


async def _terminate_and_reap(proc, communicate_task: asyncio.Task) -> None:
    """终止子进程并排空 PIPE；取消和超时共用。"""
    if proc.returncode is None:
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=LIBREOFFICE_REAP_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if not communicate_task.done():
            communicate_task.cancel()
        await asyncio.gather(communicate_task, return_exceptions=True)
    except Exception:
        # 进程已终止，清理阶段不应覆盖原始超时/取消原因。
        await asyncio.gather(communicate_task, return_exceptions=True)


async def _run_conversion(
    source_path: Path,
    *,
    output_format: str,
    timeout: float,
    queue_timeout: float,
    application_flag: str | None = None,
    soffice_path: str | None = None,
) -> bytes:
    """执行一次隔离转换并返回产物；所有出口都回收进程、槽位和临时目录。"""
    soffice = soffice_path or _find_soffice()
    format_name = output_format.split(":", 1)[0].lower()
    if soffice is None:
        raise HTTPException(
            status_code=503,
            detail={
                "reason": "libreoffice_unavailable",
                "message": "服务器未安装 LibreOffice，请下载后查看",
            },
        )

    await _acquire_slot(queue_timeout)
    job_root: Path | None = None
    outcome = "failed"
    run_started = time.perf_counter()
    try:
        job_root = Path(
            await asyncio.to_thread(
                tempfile.mkdtemp,
                prefix=f"lo_job_{uuid4().hex}_",
            )
        )
        profile_dir = job_root / "profile"
        output_dir = job_root / "output"
        await asyncio.to_thread(profile_dir.mkdir, parents=True, exist_ok=False)
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=False)
        user_installation = _build_user_installation(profile_dir)

        cmd = [
            soffice,
            f"-env:UserInstallation={user_installation}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
        ]
        if application_flag:
            cmd.append(application_flag)
        cmd.extend(
            [
                "--convert-to",
                output_format,
                "--outdir",
                str(output_dir),
                str(source_path),
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            outcome = "spawn_failed"
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": "libreoffice_start_failed",
                    "message": "Office 转换服务启动失败，请稍后重试",
                },
                headers={"Retry-After": str(LIBREOFFICE_RETRY_AFTER_SECONDS)},
            ) from exc

        communicate_task = asyncio.create_task(proc.communicate())
        try:
            _stdout, stderr_bytes = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            outcome = "timeout"
            await _terminate_and_reap(proc, communicate_task)
            raise HTTPException(
                status_code=504,
                detail={
                    "reason": "libreoffice_timeout",
                    "elapsed_seconds": timeout,
                    "message": f"Office 转换超时（{timeout:g}s），请稍后重试",
                },
                headers={"Retry-After": str(LIBREOFFICE_RETRY_AFTER_SECONDS)},
            ) from exc
        except asyncio.CancelledError:
            outcome = "cancelled"
            await _terminate_and_reap(proc, communicate_task)
            raise

        if proc.returncode != 0:
            outcome = "nonzero_exit"
            err_msg = stderr_bytes.decode("utf-8", errors="ignore")[:500]
            logger.warning(
                "[LIBREOFFICE_POOL] conversion failed rc=%s: %s",
                proc.returncode,
                err_msg,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    f"LibreOffice 转换失败: {err_msg}"
                    if err_msg
                    else "LibreOffice 转换失败"
                ),
            )

        converted = output_dir / f"{source_path.stem}.{format_name}"
        if not await asyncio.to_thread(converted.is_file):
            outcome = "missing_output"
            raise HTTPException(
                status_code=500,
                detail="LibreOffice 转换后文件不存在",
            )

        payload = await asyncio.to_thread(converted.read_bytes)
        outcome = "success"
        return payload
    finally:
        LIBREOFFICE_RUN_SECONDS.labels(format=format_name).observe(
            time.perf_counter() - run_started
        )
        LIBREOFFICE_RESULTS.labels(result=outcome, format=format_name).inc()
        try:
            if job_root is not None:
                await asyncio.shield(
                    asyncio.to_thread(shutil.rmtree, job_root, True)
                )
        finally:
            _release_slot()


async def convert_office_to_pdf_bytes(
    source_path: Path,
    *,
    timeout: float = 90,
    queue_timeout: float = LIBREOFFICE_ACQUIRE_TIMEOUT_SECONDS,
    soffice_path: str | None = None,
) -> bytes:
    """把 Office 文件转成 PDF；转换在异步子进程中执行。"""
    return await _run_conversion(
        source_path,
        output_format="pdf",
        timeout=timeout,
        queue_timeout=queue_timeout,
        soffice_path=soffice_path,
    )


async def get_or_create_preview_pdf(
    source_path: Path,
    cache_path: Path,
    *,
    timeout: float = 90,
    queue_timeout: float = LIBREOFFICE_ACQUIRE_TIMEOUT_SECONDS,
    soffice_path: str | None = None,
) -> tuple[bytes, str]:
    """同缓存键单飞转换，并以临时文件原子发布缓存。"""

    async def _read_cache() -> bytes | None:
        try:
            return await asyncio.to_thread(cache_path.read_bytes)
        except FileNotFoundError:
            return None

    cached = await _read_cache()
    if cached is not None:
        return cached, "hit"

    lock_key = str(cache_path.resolve())
    lock = _preview_locks.get(lock_key)
    if lock is None:
        lock = asyncio.Lock()
        _preview_locks[lock_key] = lock

    async with lock:
        cached = await _read_cache()
        if cached is not None:
            return cached, "hit"

        payload = await convert_office_to_pdf_bytes(
            source_path,
            timeout=timeout,
            queue_timeout=queue_timeout,
            soffice_path=soffice_path,
        )

        def _publish() -> None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_name(
                f".{cache_path.name}.{uuid4().hex}.tmp"
            )
            try:
                temporary.write_bytes(payload)
                temporary.replace(cache_path)
            finally:
                temporary.unlink(missing_ok=True)

        try:
            await asyncio.to_thread(_publish)
        except OSError:
            logger.warning(
                "[LIBREOFFICE_POOL] preview cache write failed: %s",
                cache_path,
                exc_info=True,
            )
        return payload, "miss"


async def convert_with_libreoffice(
    xlsx_path: Path,
    timeout: int = 60,
    *,
    queue_timeout: float = LIBREOFFICE_ACQUIRE_TIMEOUT_SECONDS,
) -> Path:
    """重算 xlsx，并用原子替换覆盖原文件。"""
    payload = await _run_conversion(
        xlsx_path,
        output_format="xlsx",
        timeout=timeout,
        queue_timeout=queue_timeout,
        application_flag="--calc",
    )
    temporary = xlsx_path.with_name(f".{xlsx_path.name}.{uuid4().hex}.tmp")
    try:
        await asyncio.to_thread(temporary.write_bytes, payload)
        await asyncio.to_thread(temporary.replace, xlsx_path)
    finally:
        await asyncio.to_thread(temporary.unlink, missing_ok=True)
    return xlsx_path


def get_queue_depth_header() -> dict[str, str]:
    """有等待者时向响应暴露当前进程内队列深度。"""
    depth = get_queue_depth()
    LIBREOFFICE_QUEUE_DEPTH.set(depth)
    if depth > 0:
        return {"X-Recompute-Queue-Depth": str(depth)}
    return {}


async def startup_health_check() -> None:
    """应用启动时探测 LibreOffice 可用性 (Req 8.3)。

    简化策略：仅检测可执行文件是否存在，不实际运行 --version
    （Windows 上启动 LO 需要 8-15 秒，会拖慢启动；运行时按需启动）。
    """
    soffice = _find_soffice()
    if soffice is None:
        logger.warning(
            "[LIBREOFFICE_POOL] 未找到 LibreOffice 可执行文件，三级数据源前两级仍可用。",
        )
        return

    logger.info("[LIBREOFFICE_POOL] 检测到 LibreOffice: path=%s（运行时按需启动）", soffice)


# ---------------------------------------------------------------------------
# Public API for external modules
# ---------------------------------------------------------------------------
def find_soffice_path() -> str | None:
    """返回统一探测到的 LibreOffice 路径。"""
    return _find_soffice()


def get_semaphore() -> asyncio.Semaphore:
    """获取模块级 semaphore 引用（供测试使用）。"""
    return _libreoffice_semaphore


def reset_cached_path() -> None:
    """重置缓存的 soffice 路径（供测试使用）。"""
    global _cached_soffice_path
    _cached_soffice_path = None
