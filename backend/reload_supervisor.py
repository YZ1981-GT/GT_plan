"""热重载不中断：新 worker 就绪后才停旧 worker（spec backend-startup-and-request-overhead R2）。

uvicorn 原来的 ``ChangeReload.restart``：先让旧 worker 退出（Windows 下发 CTRL_C），再起新 worker；新 worker 导入、
启动的这段时间（实测约 15 s）新请求卡在监听队列里。这里只换 ``startup / restart / shutdown``，文件监听
（``should_restart``）沿用 uvicorn 的。

每个 worker 带交接事件（应用侧见 ``app.core.reload_handoff``）：
- ready：worker 设 —— lifespan 完成、uvicorn 已开始 accept；候选在此前同步物化全部 lazy route；
- stop / handoff_stop：父进程请求退出，并区分热交接与普通 shutdown；
- primary：父进程设 —— 旧 worker 已退出，可以做 singleton；
- primary_ready / primary_failed：worker 回报 singleton 接管完成或关键失败。
新旧 worker 共用父进程的监听 socket。候选就绪且稳定后才排空旧 worker；排空期间持续监控候选。
最近一次重载的结果写进 ``GT_RELOAD_STATUS_FILE``（``/api/health`` 的 ``reload.last``）。

``run_uvicorn.py`` 在调 uvicorn ``main()`` 前调 :func:`install`；``GT_OVERLAP_RELOAD=0`` 时不换，退回 uvicorn 原来的方式。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from uvicorn._subprocess import get_subprocess, spawn
from uvicorn.supervisors import ChangeReload
from uvicorn.supervisors.basereload import HANDLED_SIGNALS

logger = logging.getLogger("uvicorn.error")

STATUS_FILE_ENV = "GT_RELOAD_STATUS_FILE"  # 与 app.core.reload_handoff 同名（父进程不导入 app）


def _env_seconds(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


_SENSITIVE_REASON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(password|passwd|pwd|token|api[_-]?key|secret|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(postgres(?:ql)?|redis|mysql|mongodb)://[^\s\"']+"),
    re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s；,]+"),
)


def _sanitize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    out = str(reason).replace("\r", " ").replace("\n", " ")
    for pattern in _SENSITIVE_REASON_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out[:500]


def _rounded_timing(value: float | None) -> float | None:
    return None if value is None else round(max(0.0, value), 3)


class _ErrorCollector(logging.Handler):
    """worker 里收集 ERROR 日志的一行摘要（uvicorn 的导入失败 / lifespan 启动失败只记日志）。"""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            line = f"{type(exc).__name__}: {exc}"
        else:
            text = [s for s in record.getMessage().strip().splitlines() if s.strip()]
            line = text[-1].strip() if text else ""
        if line and line not in self.lines:
            self.lines.append(line[:200])


class _WorkerTarget:
    """worker 进程入口（必须可 pickle）：注入交接事件、监视 ready / stop，再运行 ``server.run``。"""

    def __init__(
        self,
        run: Any,
        ready: Any,
        stop: Any,
        handoff_stop: Any,
        primary: Any,
        primary_ready: Any,
        primary_failed: Any,
        candidate: bool,
        error_file: str,
    ) -> None:
        self.run = run
        self.ready = ready
        self.stop = stop
        self.handoff_stop = handoff_stop
        self.primary = primary
        self.primary_ready = primary_ready
        self.primary_failed = primary_failed
        self.candidate = candidate
        self.error_file = error_file

    def __call__(self, sockets: Any = None) -> None:
        from app.core import reload_handoff

        reload_handoff.attach(
            ready=self.ready,
            stop=self.stop,
            handoff_stop=self.handoff_stop,
            primary=self.primary,
            primary_ready=self.primary_ready,
            primary_failed=self.primary_failed,
            candidate=self.candidate,
            error_file=self.error_file,
        )
        server = self.run.__self__
        errors = _ErrorCollector()
        uvicorn_log = logging.getLogger("uvicorn.error")
        uvicorn_log.addHandler(errors)
        threading.Thread(target=self._watch, args=(server,), name="gt-reload-handoff", daemon=True).start()
        try:
            self.run(sockets=sockets)
        except BaseException as exc:
            if not server.started:
                own = "" if isinstance(exc, SystemExit) else f"{type(exc).__name__}: {exc}"
                self._record("；".join([*errors.lines, own] if own else errors.lines) or type(exc).__name__)
            raise
        else:
            if not server.started:
                self._record("；".join(errors.lines) or "启动失败（没有就绪就退出）")
        finally:
            uvicorn_log.removeHandler(errors)

    def _record(self, reason: str) -> None:
        try:
            Path(self.error_file).write_text(reason[-600:], encoding="utf-8")
        except OSError:
            pass

    def _watch(self, server: Any) -> None:
        while not server.started:
            if self.stop.wait(0.05):  # 还没就绪就被要求停（交接取消 / 关闭）
                server.should_exit = True
                return
        self.ready.set()
        self.stop.wait()
        if not self.handoff_stop.is_set():
            # 普通 supervisor shutdown：保留 lifespan 的 2 s pre-drain 与 SSE 关闭路径。
            server.should_exit = True
            return
        from app.core import reload_handoff

        loop = server.servers[0].get_loop()
        asyncio.run_coroutine_threadsafe(reload_handoff.drain_for_handoff(server), loop)


@dataclass
class _Worker:
    process: Any
    ready: Any
    stop: Any
    handoff_stop: Any
    primary: Any
    primary_ready: Any
    primary_failed: Any
    candidate: bool
    error_file: Path

    @property
    def pid(self) -> int | None:
        return self.process.pid


class OverlapReload(ChangeReload):  # type: ignore[misc, valid-type]
    """新 worker 就绪后才停旧 worker。"""

    def __init__(self, config: Any, target: Any, sockets: list) -> None:
        super().__init__(config, target, sockets)
        default = Path(tempfile.gettempdir()) / f"gt_reload_status_{config.port}.json"
        self.status_file = Path(os.environ.setdefault(STATUS_FILE_ENV, str(default)))
        self.ready_timeout = _env_seconds("GT_RELOAD_READY_TIMEOUT", 180)
        self.primary_timeout = _env_seconds("GT_RELOAD_PRIMARY_TIMEOUT", 180)
        self.stability_seconds = _env_seconds("GT_RELOAD_STABILITY_SECONDS", 0.2)
        self.stop_timeout = _env_seconds("GT_RELOAD_STOP_TIMEOUT", 30)
        self.workers: list[_Worker] = []
        self._seq = 0

    @property
    def serving(self) -> _Worker | None:
        return self.workers[-1] if self.workers else None

    def startup(self) -> None:
        logger.info("Started reloader process [%d] using %s（新旧 worker 交接）", self.pid, self.reloader_name)
        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self.signal_handler)
        worker = self._spawn(candidate=False)
        worker.primary.set()  # 首次启动：没有旧 worker，与原来一样当场做全部启动任务
        self.workers = [worker]
        self._write_status("started", time.monotonic(), new=worker, phase="startup")

    def _spawn(self, *, candidate: bool) -> _Worker:
        self._seq += 1
        ready = spawn.Event()
        stop = spawn.Event()
        handoff_stop = spawn.Event()
        primary = spawn.Event()
        primary_ready = spawn.Event()
        primary_failed = spawn.Event()
        error_file = self.status_file.with_name(f"{self.status_file.stem}_worker{self._seq}.err")
        error_file.unlink(missing_ok=True)
        target = _WorkerTarget(
            self.target,
            ready,
            stop,
            handoff_stop,
            primary,
            primary_ready,
            primary_failed,
            candidate,
            str(error_file),
        )
        process = get_subprocess(config=self.config, target=target, sockets=self.sockets)
        process.start()
        return _Worker(
            process,
            ready,
            stop,
            handoff_stop,
            primary,
            primary_ready,
            primary_failed,
            candidate,
            error_file,
        )

    def restart(self) -> None:
        started = time.monotonic()
        old = self.serving
        new = self._spawn(candidate=True)
        ok, reason = self._wait_ready(new)
        ready_at = time.monotonic()
        timings: dict[str, float | None] = {
            "spawn_to_ready_s": ready_at - started if ok else None,
            "ready_to_old_exit_s": None,
            "old_exit_to_primary_ready_s": None,
        }
        if not ok:
            self._stop(new)
            logger.error("[热重载] 候选没有就绪，旧 worker [%s] 继续服务：%s", old.pid if old else "-", reason)
            self._write_status(
                "failed", started, reason=reason, old=old, new=new, phase="candidate_start", timings=timings,
            )
            return

        ok, reason = self._wait_stable(new)
        if not ok:
            self._stop(new)
            logger.error("[热重载] 候选就绪后未通过稳定检查，旧 worker [%s] 继续服务：%s", old.pid if old else "-", reason)
            self._write_status(
                "failed", started, reason=reason, old=old, new=new, phase="candidate_stability", timings=timings,
            )
            return

        forced = False
        candidate_alive = new.process.is_alive()
        if old is not None and candidate_alive:
            forced, candidate_alive, reason = self._drain_old_while_monitoring(old, new)
        old_exit_at = time.monotonic()
        timings["ready_to_old_exit_s"] = old_exit_at - ready_at

        if not candidate_alive:
            self._recover_after_candidate_loss(
                started=started,
                reason=reason or "候选在旧 worker 排空期间退出",
                old=old,
                failed_candidate=new,
                forced_stop=forced,
                timings=timings,
                old_exit_at=old_exit_at,
            )
            return

        new.primary.set()
        primary_state, reason = self._wait_primary_transition(new)
        primary_at = time.monotonic()
        timings["old_exit_to_primary_ready_s"] = primary_at - old_exit_at
        self.workers = [new]

        if primary_state == "ready":
            logger.warning(
                "[热重载] 交接完成：worker [%s] → [%s]，%.1fs%s",
                old.pid if old else "-",
                new.pid,
                primary_at - started,
                "（旧 worker 超时被强制结束）" if forced else "",
            )
            self._write_status(
                "ok", started, old=old, new=new, forced_stop=forced, phase="primary_ready", timings=timings,
            )
            return

        if primary_state in {"failed", "timeout"} and new.process.is_alive():
            logger.error("[热重载] 新 worker 已接管但 primary 启动任务未完成：%s", reason)
            self._write_status(
                "degraded", started, reason=reason, old=old, new=new, forced_stop=forced,
                phase="primary_failed" if primary_state == "failed" else "primary_timeout", timings=timings,
            )
            return

        self._recover_after_candidate_loss(
            started=started,
            reason=reason or "候选在 primary 接管阶段退出",
            old=old,
            failed_candidate=new,
            forced_stop=forced,
            timings=timings,
            old_exit_at=old_exit_at,
        )

    def _wait_stable(self, worker: _Worker) -> tuple[bool, str]:
        deadline = time.monotonic() + max(0.0, self.stability_seconds)
        while time.monotonic() < deadline:
            if not worker.process.is_alive():
                return False, self._read_error(worker) or f"候选就绪后退出（exitcode={worker.process.exitcode}）"
            if self.should_exit.is_set():
                return False, "收到退出信号"
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        return (True, "") if worker.process.is_alive() else (
            False,
            self._read_error(worker) or f"候选稳定检查末尾退出（exitcode={worker.process.exitcode}）",
        )

    def _drain_old_while_monitoring(self, old: _Worker, candidate: _Worker) -> tuple[bool, bool, str]:
        """热交接排空旧 worker，同时持续观察候选；返回 forced、候选是否存活、原因。"""
        old.handoff_stop.set()
        old.stop.set()
        deadline = time.monotonic() + self.stop_timeout
        candidate_alive = True
        reason = ""
        while old.process.is_alive() and time.monotonic() < deadline:
            old.process.join(min(0.1, max(0.0, deadline - time.monotonic())))
            if candidate_alive and not candidate.process.is_alive():
                candidate_alive = False
                reason = self._read_error(candidate) or f"候选在旧 worker 排空期间退出（exitcode={candidate.process.exitcode}）"
        forced = False
        if old.process.is_alive():
            logger.error("[热重载] worker [%s] %.0fs 内没有退出，强制结束", old.pid, self.stop_timeout)
            old.process.terminate()
            old.process.join(5)
            forced = True
        old.process.join()
        if candidate_alive and not candidate.process.is_alive():
            candidate_alive = False
            reason = self._read_error(candidate) or f"候选在旧 worker 退出时死亡（exitcode={candidate.process.exitcode}）"
        return forced, candidate_alive, reason

    def _wait_primary_transition(self, worker: _Worker) -> tuple[str, str]:
        deadline = time.monotonic() + self.primary_timeout
        while True:
            if worker.primary_failed.is_set():
                return "failed", self._read_error(worker) or "关键 singleton 启动任务失败"
            if worker.primary_ready.is_set():
                return "ready", ""
            if not worker.process.is_alive():
                return "dead", self._read_error(worker) or f"新 worker 接管时退出（exitcode={worker.process.exitcode}）"
            if self.should_exit.is_set():
                return "shutdown", "收到退出信号"
            if time.monotonic() > deadline:
                return "timeout", f"{self.primary_timeout:.0f}s 内 primary 启动任务未完成"
            time.sleep(0.1)

    def _recover_after_candidate_loss(
        self,
        *,
        started: float,
        reason: str,
        old: _Worker | None,
        failed_candidate: _Worker,
        forced_stop: bool,
        timings: dict[str, float | None],
        old_exit_at: float,
    ) -> None:
        """旧 worker 已开始排空后候选死亡：只尝试一次新候选，不伪称旧 worker 可回滚。"""
        self._stop(failed_candidate)
        logger.critical("[热重载] 候选在排空后失败，启动一次恢复 worker：%s", reason)
        recovery = self._spawn(candidate=True)
        recovery.primary.set()
        ready, recovery_reason = self._wait_ready(recovery)
        if ready:
            ready, recovery_reason = self._wait_stable(recovery)
        primary_state = "dead"
        if ready:
            primary_state, recovery_reason = self._wait_primary_transition(recovery)
        timings["old_exit_to_primary_ready_s"] = time.monotonic() - old_exit_at

        if ready and recovery.process.is_alive():
            self.workers = [recovery]
            combined = reason
            if primary_state != "ready":
                combined = f"{reason}；恢复 worker primary 状态={primary_state}: {recovery_reason}"
            self._write_status(
                "degraded",
                started,
                reason=combined,
                old=old,
                new=recovery,
                forced_stop=forced_stop,
                phase="recovered_after_candidate_failure" if primary_state == "ready" else "recovery_primary_failed",
                timings=timings,
            )
            return

        self._stop(recovery)
        self.workers = []
        self._write_status(
            "failed",
            started,
            reason=f"{reason}；恢复 worker 失败：{recovery_reason}",
            old=old,
            new=recovery,
            forced_stop=forced_stop,
            phase="recovery_failed",
            timings=timings,
        )

    def _wait_ready(self, worker: _Worker) -> tuple[bool, str]:
        deadline = time.monotonic() + self.ready_timeout
        while not worker.ready.wait(0.1):
            if not worker.process.is_alive():
                return False, self._read_error(worker) or f"新 worker 退出（exitcode={worker.process.exitcode}）"
            if self.should_exit.is_set():
                return False, "收到退出信号"
            if time.monotonic() > deadline:
                return False, f"{self.ready_timeout:.0f}s 内没有就绪"
        return True, ""

    @staticmethod
    def _read_error(worker: _Worker) -> str:
        try:
            return worker.error_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _stop(self, worker: _Worker, *, handoff: bool = False) -> bool:
        """让 worker 优雅退出；只有 reload old-worker 路径设置 handoff pre-drain。"""
        if worker.process.is_alive():
            if handoff:
                worker.handoff_stop.set()
            worker.stop.set()
            worker.process.join(self.stop_timeout)
        if worker.process.is_alive():
            logger.error("[热重载] worker [%s] %.0fs 内没有退出，强制结束", worker.pid, self.stop_timeout)
            worker.process.terminate()
            worker.process.join(5)
            return True
        worker.process.join()
        return False

    def shutdown(self) -> None:
        alive = [w for w in self.workers if w.process.is_alive()]
        for worker in alive:
            worker.stop.set()
        deadline = time.monotonic() + self.stop_timeout
        for worker in alive:
            worker.process.join(max(0.0, deadline - time.monotonic()))
            if worker.process.is_alive():
                worker.process.terminate()
                worker.process.join(5)
        for sock in self.sockets:
            sock.close()
        logger.info("Stopping reloader process [%d]", self.pid)

    def _write_status(
        self,
        result: str,
        started: float,
        *,
        reason: str | None = None,
        old: _Worker | None = None,
        new: _Worker | None = None,
        forced_stop: bool = False,
        phase: str,
        timings: dict[str, float | None] | None = None,
    ) -> None:
        segment = timings or {}
        data = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "result": result,
            "duration_s": round(time.monotonic() - started, 3),
            "reason": _sanitize_reason(reason),
            "phase": phase,
            "spawn_to_ready_s": _rounded_timing(segment.get("spawn_to_ready_s")),
            "ready_to_old_exit_s": _rounded_timing(segment.get("ready_to_old_exit_s")),
            "old_exit_to_primary_ready_s": _rounded_timing(segment.get("old_exit_to_primary_ready_s")),
            # 状态文件是本机诊断面；公开 health 由 reload_handoff.status_snapshot 去掉 PID。
            "old_pid": old.pid if old else None,
            "new_pid": new.pid if new else None,
            "serving_pid": self.serving.pid if self.serving else None,
            "forced_stop": forced_stop,
        }
        try:
            tmp = self.status_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.status_file)
        except OSError as exc:
            logger.warning("[热重载] 写状态文件失败：%s", exc)


def install() -> bool:
    """把 uvicorn 的 ``ChangeReload`` 换成 :class:`OverlapReload`（``GT_OVERLAP_RELOAD=0`` 时不换）。返回是否换了。"""
    if os.environ.get("GT_OVERLAP_RELOAD", "1") == "0":
        return False
    import importlib

    # 🔴 不能写 `import uvicorn.main`：uvicorn 包把属性 `main` 换成了同名的 click 命令，
    # 那样拿到的是命令对象，赋值落在它身上、uvicorn.main 模块里的 ChangeReload 不变。
    importlib.import_module("uvicorn.main").ChangeReload = OverlapReload
    return True
