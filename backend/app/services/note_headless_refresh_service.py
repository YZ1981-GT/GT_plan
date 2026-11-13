"""离屏披露手工触发：不开附注页 / 底稿披露 Tab，后端拉起 Node 执行器把底稿披露表刷进附注
（spec note-disclosure-pull-regression-and-headless-backend 任务 13，design §5.2 / §5.4；ADR-NPR-03 路线 A）。

执行器 = ``audit-platform/frontend/tools/headless-disclosure/run.mjs refresh``：在 Node 里跑附注页「全部刷新」的同一套前端
代码（prepare → 各底稿披露 Tab 的同一个 builder 离屏现算 → ``sync-from-workpaper`` → push → 后端重算），不翻译、不复制。

- 身份：子进程拿一枚**触发人本人**的短期 access 令牌（与登录同一签发函数，``purpose=headless_disclosure``，有效期 = 本次
  超时 + 余量），只经子进程 env 传入，不进命令行 / 日志 / 返回值；跑完即进黑名单（Redis 不可用时到期作废）。子进程的
  每个请求照常过各端点自己的门禁 ⇒ 触发人能做的它才能做，不提权。
- 范围：子进程只连本机环回地址；写请求只发取数 / 披露同步 / 重算这几个现有端点（执行器的 ``headlessWriteAllowlist``），
  四层人工保护与推送 ownership 重放都在这些端点里，原样生效。
- env 从零构造：不继承平台进程的数据库 / 密钥变量。
- 并发：本进程内同一项目同一年度同时只跑一个，全进程最多 ``MAX_CONCURRENT_RUNS`` 个；超出即拒绝（不排队）。
  多 worker 之间的互斥留给期 3（``platform_jobs``）。
- 新鲜度：构建产物与源码不一致时执行器拒绝运行（退出码 3）⇒ 这里报「不可用」，不拿旧版 builder 的数写附注。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

#: 执行器目录（前端源码同仓，解析前端 node_modules）
RUNNER_DIR = Path(__file__).resolve().parents[3] / "audit-platform" / "frontend" / "tools" / "headless-disclosure"
#: 单次运行墙钟上限（秒）：全部刷新实测几十秒级，留足余量
RUN_TIMEOUT_SECONDS = 300
#: 令牌有效期 = 超时 + 余量（秒）
TOKEN_GRACE_SECONDS = 60
#: 全进程同时运行的子进程上限
MAX_CONCURRENT_RUNS = 2
#: 令牌用途标记（操作日志 / 排查时认得出）
TOKEN_PURPOSE = "headless_disclosure"
#: 执行器退出码：未构建或构建产物已过期
EXIT_BUILD_STALE = 3
_STDERR_TAIL = 4000
_LOOPBACK = re.compile(r"^http://(?:127\.0\.0\.1|\[::1\]|localhost):\d{1,5}$")
_SECTION_MAX = 64

_running: set[tuple[UUID, int]] = set()


class HeadlessRefreshError(Exception):
    """离屏刷新失败的基类；``str(exc)`` 是给用户看的中文原因。"""


class HeadlessRefreshUnavailable(HeadlessRefreshError):
    """执行器跑不起来：没有 Node、未构建或构建产物过期（503）。"""


class HeadlessRefreshBusy(HeadlessRefreshError):
    """同一项目年度正在跑，或全进程已达并发上限（409）。"""


class HeadlessRefreshTimeout(HeadlessRefreshError):
    """超时，子进程已终止（504）。"""


class HeadlessRefreshFailed(HeadlessRefreshError):
    """子进程报错退出或没有给出结果（502）。"""


def loopback_api_base(server: Any, default_port: int | None = None) -> str:
    """子进程回连本后端的地址：请求所在服务的端口，主机一律 127.0.0.1（不用 localhost：Windows 先试 ::1 多等约 2s）。"""
    port = None
    if isinstance(server, (tuple, list)) and len(server) >= 2 and isinstance(server[1], int):
        port = server[1]
    if port is None:
        from app.core.config import settings

        port = default_port or int(getattr(settings, "PORT", 9980))
    return f"http://127.0.0.1:{port}"


def mint_run_token(user_id: UUID, ttl_seconds: int) -> str:
    """触发人本人的短期 access 令牌（与登录同一签发函数；``purpose`` 只作标记，鉴权口径不变）。"""
    from app.core.security import create_access_token

    return create_access_token({"sub": str(user_id), "purpose": TOKEN_PURPOSE},
                               expires_delta=timedelta(seconds=ttl_seconds))


async def revoke_run_token(token: str, ttl_seconds: int) -> bool:
    """跑完即吊销（进黑名单，``get_current_user`` 查的同一个键）；Redis 不可用时返回 False，令牌到期自然作废。"""
    try:
        from app.core.redis import redis_client
        from app.services.auth_service import blacklist_token

        await blacklist_token(token, redis_client, ttl_seconds)
        return True
    except Exception as exc:  # noqa: BLE001 — 吊销是兜底，失败不影响已完成的刷新
        logger.warning("headless refresh token revoke skipped: %s", type(exc).__name__)
        return False


def child_env(*, token: str, api_base: str) -> dict[str, str]:
    """子进程 env：从零构造，只放 Node 运行必需的系统变量与本次的令牌 / 回连地址。"""
    env = {
        "GT_HEADLESS_TOKEN": token,
        "GT_HEADLESS_API_BASE": api_base,
        "NODE_ENV": "production",
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", ""),
    }
    for name in ("SYSTEMROOT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def _node_path() -> str:
    node = shutil.which("node")
    if not node:
        raise HeadlessRefreshUnavailable("服务器上没有 Node.js，离屏刷新跑不起来（需 Node 20+）")
    return node


def _runner_script(runner_dir: Path) -> Path:
    script = runner_dir / "run.mjs"
    if not script.is_file():
        raise HeadlessRefreshUnavailable(f"离屏执行器不存在：{script}")
    if not (runner_dir / "dist" / "entry.mjs").is_file():
        raise HeadlessRefreshUnavailable(
            "离屏执行器尚未构建：在 audit-platform/frontend 下执行 "
            "node node_modules/vite/bin/vite.js build --config tools/headless-disclosure/vite.config.ts")
    return script


def _process_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _popen(args: list[str], env: dict[str, str], cwd: str) -> subprocess.Popen:
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd,
                            **_process_group_kwargs())


async def _spawn(args: list[str], *, env: dict[str, str], cwd: str) -> subprocess.Popen:
    """拉起执行器子进程（测试在这一层换成假进程）。

    在线程里用 ``subprocess.Popen``，不用 ``asyncio.create_subprocess_exec``：Windows 开发服务器（``run_uvicorn.py``）
    跑在 SelectorEventLoop 上，它不支持子进程（``NotImplementedError``）。等待也放线程（``communicate``），
    任何事件循环下行为一致。
    """
    return await asyncio.to_thread(_popen, args, env, cwd)


def _kill_tree_blocking(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, check=False)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, ProcessLookupError, OSError) as exc:
        logger.warning("headless refresh child kill failed pid=%s: %s", proc.pid, exc)
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass


async def _kill_tree(proc: subprocess.Popen) -> None:
    """Windows 用 ``taskkill /T``（TerminateProcess 不连带子进程）；POSIX 向进程组发信号。"""
    if proc.poll() is not None:
        return
    await asyncio.to_thread(_kill_tree_blocking, proc)


def _tail(raw: bytes, token: str) -> str:
    """stderr 末尾（报错用）；令牌即使被打印出来也抹掉。"""
    text = raw.decode("utf-8", "replace")
    if token:
        text = text.replace(token, "***")
    return text[-_STDERR_TAIL:].strip()


async def run_headless_refresh(
    *,
    project_id: UUID,
    year: int,
    user_id: UUID,
    section: str | None,
    api_base: str,
    timeout: float = RUN_TIMEOUT_SECONDS,
    runner_dir: Path | None = None,
) -> dict[str, Any]:
    """跑一次离屏刷新（全部章节，或 ``section`` 一个章节），返回执行器结果（``ok`` / ``stage`` / ``outcomes`` / ``pending`` /
    ``push`` / ``refresh``）加本次运行信息；跑不起来、超时、出错时抛 ``HeadlessRefreshError`` 的子类。"""
    if not _LOOPBACK.match(api_base):
        raise ValueError(f"离屏执行器只回连本机环回地址，拒绝 {api_base}")
    if section is not None and not (0 < len(section) <= _SECTION_MAX):
        raise ValueError("章节号长度不对")
    runner_dir = runner_dir or RUNNER_DIR
    node = _node_path()
    script = _runner_script(runner_dir)
    key = (project_id, int(year))
    if key in _running:
        raise HeadlessRefreshBusy("该项目本年度的离屏刷新正在运行，请等它结束")
    if len(_running) >= MAX_CONCURRENT_RUNS:
        raise HeadlessRefreshBusy("服务器同时在跑的离屏刷新已达上限，请稍后再试")
    _running.add(key)
    ttl = int(timeout) + TOKEN_GRACE_SECONDS
    token = ""
    started = time.monotonic()
    try:
        token = mint_run_token(user_id, ttl)
        with tempfile.TemporaryDirectory(prefix="gt_headless_", ignore_cleanup_errors=True) as tmp:
            out = Path(tmp) / "result.json"
            args = [node, str(script), "refresh", "--project", str(project_id), "--year", str(int(year))]
            if section is not None:
                args += ["--section", section]
            args += ["--out", str(out)]
            proc = await _spawn(args, env=child_env(token=token, api_base=api_base), cwd=str(runner_dir.parents[1]))
            try:
                _stdout, stderr = await asyncio.wait_for(asyncio.to_thread(proc.communicate), timeout=timeout)
            except asyncio.TimeoutError:
                await _kill_tree(proc)
                raise HeadlessRefreshTimeout(f"离屏刷新超过 {int(timeout)} 秒未完成，已终止") from None
            except asyncio.CancelledError:
                await _kill_tree(proc)
                raise
            if proc.returncode == EXIT_BUILD_STALE:
                raise HeadlessRefreshUnavailable(_tail(stderr, token) or "离屏执行器构建产物不可用")
            if proc.returncode != 0:
                raise HeadlessRefreshFailed(
                    f"离屏执行器出错退出（退出码 {proc.returncode}）：{_tail(stderr, token) or '没有输出'}")
            try:
                result = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise HeadlessRefreshFailed(f"离屏执行器没有给出可读的结果：{type(exc).__name__}") from None
        if not isinstance(result, dict):
            raise HeadlessRefreshFailed("离屏执行器结果格式不对")
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info("headless refresh done project=%s year=%s section=%s ok=%s elapsed_ms=%s",
                    project_id, year, section, result.get("ok"), elapsed_ms)
        return {**result, "project_id": str(project_id), "year": int(year), "section": section,
                "elapsed_ms": elapsed_ms}
    finally:
        _running.discard(key)
        if token:
            await revoke_run_token(token, ttl)
