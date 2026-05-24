"""LibreOffice 池化管理器 — Semaphore(2) 限流 + UserInstallation 隔离 + 健康探测

Req 8（P2-12）：6000 并发场景下 LibreOffice 重算路径稳定性保障。

核心能力：
  - 模块级 asyncio.Semaphore(2) 限制同一时刻最多 2 个 soffice 子进程
  - Windows pid+tid UserInstallation 隔离避免 user profile 冲突
  - startup 事件 4 路径探测 + soffice --version 健康检查
  - 60s 超时 kill + semaphore 释放 + HTTP 504
  - X-Recompute-Queue-Depth 响应头 + libreoffice_queue_depth metric

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level semaphore: max 2 concurrent soffice processes (Req 8.1)
# ---------------------------------------------------------------------------
_libreoffice_semaphore = asyncio.Semaphore(2)

# ---------------------------------------------------------------------------
# Prometheus metric (Req 8.5)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Gauge
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _GaugeStub:
        """Nil-op 占位"""
        def __init__(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass

    Gauge = _GaugeStub  # type: ignore[misc,assignment]

LIBREOFFICE_QUEUE_DEPTH = Gauge(
    "libreoffice_queue_depth",
    "Number of tasks waiting for LibreOffice semaphore",
) if _PROMETHEUS_AVAILABLE else _GaugeStub(
    "libreoffice_queue_depth", ""
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


def _build_user_installation() -> str:
    """构建 Windows pid+tid UserInstallation 隔离路径 (Req 8.2)。

    每个调用拼接 -env:UserInstallation=file:///tmp/soffice_<pid>_<tid>
    避免多子进程共用 user profile 互锁导致启动失败。
    """
    pid = os.getpid()
    tid = threading.get_ident()
    if sys.platform == "win32":
        # Windows: use temp directory with forward slashes for file:// URI
        tmp_base = os.environ.get("TEMP", r"C:\Temp")
        path = f"{tmp_base}\\soffice_{pid}_{tid}".replace("\\", "/")
        return f"file:///{path}"
    else:
        return f"file:///tmp/soffice_{pid}_{tid}"


def get_queue_depth() -> int:
    """获取当前 semaphore 等待队列深度。

    asyncio.Semaphore 内部 _waiters 是等待获取信号量的 Future 列表。
    """
    waiters = getattr(_libreoffice_semaphore, "_waiters", None)
    if waiters is None:
        return 0
    return len(waiters)


async def convert_with_libreoffice(xlsx_path: Path, timeout: int = 60) -> Path:
    """使用 LibreOffice headless 重算 xlsx 公式（池化 + 超时 + 隔离）。

    Args:
        xlsx_path: 待重算的 xlsx 文件路径
        timeout: 超时秒数，默认 60s

    Returns:
        重算后的 xlsx 文件路径（覆盖原文件）

    Raises:
        HTTPException(504): 超时强制 kill
        HTTPException(503): LibreOffice 不可用
        HTTPException(500): 转换失败
    """
    soffice = _find_soffice()
    if soffice is None:
        raise HTTPException(
            status_code=503,
            detail="LibreOffice 不可用，无法重算公式",
        )

    # Update queue depth metric before acquiring
    depth = get_queue_depth()
    LIBREOFFICE_QUEUE_DEPTH.set(depth)

    async with _libreoffice_semaphore:
        # Update metric after acquiring (depth should decrease)
        LIBREOFFICE_QUEUE_DEPTH.set(get_queue_depth())

        user_install = _build_user_installation()
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="lo_pool_")
        tmpdir_path = Path(tmpdir)

        cmd = [
            soffice,
            "--headless",
            "--calc",
            "--convert-to", "xlsx",
            f"-env:UserInstallation={user_install}",
            "--outdir", str(tmpdir_path),
            str(xlsx_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Req 8.4: 60s 超时 kill + HTTP 504
            proc.kill()
            await proc.wait()  # ensure process is reaped
            # Cleanup temp dir
            try:
                shutil.rmtree(tmpdir_path, ignore_errors=True)
            except Exception:
                pass
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "libreoffice_timeout",
                    "elapsed_seconds": timeout,
                    "message": f"LibreOffice 重算超时（{timeout}s），子进程已强制终止",
                },
            )

        if proc.returncode != 0:
            stderr_bytes = await proc.stderr.read() if proc.stderr else b""
            err_msg = stderr_bytes.decode("utf-8", errors="ignore")[:500]
            logger.warning(
                "[LIBREOFFICE_POOL] conversion failed rc=%d: %s",
                proc.returncode, err_msg,
            )
            # Cleanup temp dir
            try:
                shutil.rmtree(tmpdir_path, ignore_errors=True)
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail=f"LibreOffice 转换失败: {err_msg}" if err_msg else "LibreOffice 转换失败",
            )

        # Copy converted file back to original path
        converted = tmpdir_path / f"{xlsx_path.stem}.xlsx"
        if not converted.exists():
            try:
                shutil.rmtree(tmpdir_path, ignore_errors=True)
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail="LibreOffice 转换后文件不存在",
            )

        shutil.copy(converted, xlsx_path)
        shutil.rmtree(tmpdir_path, ignore_errors=True)

        return xlsx_path


def get_queue_depth_header() -> dict[str, str]:
    """如果 semaphore 等待队列 ≥ 10，返回 X-Recompute-Queue-Depth 响应头 (Req 8.5)。"""
    depth = get_queue_depth()
    LIBREOFFICE_QUEUE_DEPTH.set(depth)
    if depth >= 10:
        return {"X-Recompute-Queue-Depth": str(depth)}
    return {}


async def startup_health_check() -> None:
    """应用启动时探测 LibreOffice 可用性 (Req 8.3)。

    探测 4 路径 + 执行 soffice --version 验证响应。
    失败时记录 logger.error 但不阻塞应用启动。
    """
    soffice = _find_soffice()
    if soffice is None:
        logger.error(
            "[LIBREOFFICE_POOL] 启动健康检查失败：未找到 LibreOffice 可执行文件。"
            "已探测路径: %s。三级数据源前两级仍可用。",
            _SOFFICE_CANDIDATE_PATHS,
        )
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            soffice, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        version_str = stdout.decode("utf-8", errors="ignore").strip()
        logger.info(
            "[LIBREOFFICE_POOL] 启动健康检查通过: path=%s, version=%s",
            soffice, version_str,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[LIBREOFFICE_POOL] 启动健康检查超时（15s）: path=%s。"
            "LibreOffice 可能卡死，三级数据源前两级仍可用。",
            soffice,
        )
    except Exception as e:
        logger.error(
            "[LIBREOFFICE_POOL] 启动健康检查异常: path=%s, error=%s。"
            "三级数据源前两级仍可用。",
            soffice, e,
        )


# ---------------------------------------------------------------------------
# Public API for external modules
# ---------------------------------------------------------------------------
def get_semaphore() -> asyncio.Semaphore:
    """获取模块级 semaphore 引用（供测试使用）。"""
    return _libreoffice_semaphore


def reset_cached_path() -> None:
    """重置缓存的 soffice 路径（供测试使用）。"""
    global _cached_soffice_path
    _cached_soffice_path = None
