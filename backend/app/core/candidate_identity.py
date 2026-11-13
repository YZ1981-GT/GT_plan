"""候选验证实例的代码身份与启动隔离（platform-global-display-settings-closure 13A，design §15 A2 / §16 F2·F3）。

只有进程环境含 ``GT_EXPECTED_CANDIDATE_TREE_OID`` 时进入候选模式；未设置时本模块不调用 git，
health 的 ``candidate_tree`` 为 ``null``，共享开发服务、``start-dev.bat`` 与打包行为都不变。

候选模式下：
- 身份任务 ``verify_candidate_tree_identity``（启动注册表里紧跟 ``setup_logging``）以 backend
  目录为 cwd 解析 ``HEAD^{tree}``，与期望值逐字比较，并要求没有受跟踪改动（未跟踪文件不算）；
  端口只能经 ``UVICORN_PORT`` / ``UVICORN_HOST`` 传入且不得是共享端口 9980。任一不符即抛错，
  lifespan 失败，进程退出。结果在启动时只算一次并缓存，请求期不调用 git。
- 候选实例与共享后端连同一 PG / Redis ⇒ 启动任务按 ``CANDIDATE_MODE_POLICY`` 裁决：会写共享状态、
  会重放共享队列或只为预热的任务跳过，其余照常运行。策略是闭集：键集合必须等于启动注册表的任务名集合。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

logger = logging.getLogger("audit_platform")

ENV_EXPECTED_TREE = "GT_EXPECTED_CANDIDATE_TREE_OID"
SHARED_BACKEND_PORT = 9980
IDENTITY_TASK_NAME = "verify_candidate_tree_identity"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_FORBIDDEN_UVICORN_ENV = ("UVICORN_RELOAD", "UVICORN_UDS", "UVICORN_FD", "UVICORN_WORKERS")
_FORBIDDEN_ARGV_OPTIONS = ("--port", "--host", "--uds", "--fd", "--reload", "--workers")

Action = Literal["run", "skip"]
SKIP_REASONS: frozenset[str] = frozenset({"writes_shared_state", "replays_shared_queue", "optional_prewarm"})
RUN_REASONS: frozenset[str] = frozenset({"in_process_only", "file_or_config_read", "read_only_sql", "passive_subscribe"})

_SKIP_WORKER = ("skip", "writes_shared_state")

#: 启动任务名 → (动作, 理由码)。新增启动任务未登记 ⇒ 守卫失败（候选模式下运行时也拒绝启动）。
CANDIDATE_MODE_POLICY: dict[str, tuple[Action, str]] = {
    "setup_logging": ("run", "in_process_only"),
    IDENTITY_TASK_NAME: ("run", "file_or_config_read"),
    "run_migrations": ("skip", "writes_shared_state"),
    "migration_mark_complete": ("run", "read_only_sql"),
    "acnr_redis_inject": ("run", "passive_subscribe"),
    "register_event_handlers": ("run", "in_process_only"),
    "register_a13_event_handlers": ("run", "in_process_only"),
    "register_phase_handlers": ("run", "in_process_only"),
    "replay_startup_events": ("skip", "replays_shared_queue"),
    "validate_grammar_on_startup": ("run", "file_or_config_read"),
    "check_gin_index_status": ("run", "read_only_sql"),
    "check_libreoffice_health": ("run", "file_or_config_read"),
    "validate_procedure_rollout_config": ("run", "file_or_config_read"),
    "validate_template_manifest": ("run", "file_or_config_read"),
    # write_log 对共享 schema_drift_log 先 DELETE 后 INSERT；_diff_checksums 还会执行 DDL
    "run_schema_drift_check": ("skip", "writes_shared_state"),
    "seed_builtin_template_sets": ("skip", "writes_shared_state"),
    "warm_render_caches": ("run", "file_or_config_read"),
    "check_attachment_security_gates": ("run", "file_or_config_read"),
    "start_epoch_subscriber": ("run", "passive_subscribe"),
    "acnr_invalidation_outbox_start": ("skip", "replays_shared_queue"),
    "recover_ai_chat_runs": ("skip", "writes_shared_state"),
    # 有 local-only 违规时经 audit_event 写审计哈希链
    "run_ai_chat_health_check": ("skip", "writes_shared_state"),
    "acnr_catalog_snapshot_gc": ("skip", "writes_shared_state"),
    "sla_worker": _SKIP_WORKER,
    "event_loop_lag_worker": _SKIP_WORKER,
    "capacity_queue_worker": _SKIP_WORKER,
    "import_recover_worker": _SKIP_WORKER,
    "outbox_replay_worker": ("skip", "replays_shared_queue"),
    "audit_log_writer_worker": _SKIP_WORKER,
    "budget_alert_worker": _SKIP_WORKER,
    "dataset_purge_worker": _SKIP_WORKER,
    "staged_orphan_cleaner": _SKIP_WORKER,
    "export_cleanup_worker": _SKIP_WORKER,
    "time_machine_cleanup_worker": _SKIP_WORKER,
    "procedure_dispatcher_worker": ("skip", "replays_shared_queue"),
    "invalidation_dispatcher_worker": ("skip", "replays_shared_queue"),
    "knowledge_ocr_worker": _SKIP_WORKER,
    "ai_task_worker": _SKIP_WORKER,
    "platform_job_worker": _SKIP_WORKER,
    "oo_apply_redrive_worker": _SKIP_WORKER,
    "consol_operation_worker": _SKIP_WORKER,
    "ImportJobRunner.run_forever": _SKIP_WORKER,
    "warm_workpaper_sync_registry": ("skip", "optional_prewarm"),
    "verify_lazy_routes": ("run", "in_process_only"),
    "prewarm_openapi_schema": ("skip", "optional_prewarm"),
    "install_sigterm_handler": ("run", "in_process_only"),
    "print_ready": ("run", "in_process_only"),
}


class CandidateIdentityError(RuntimeError):
    """候选实例身份或启动参数不符 ⇒ 拒绝启动。"""


_state: dict[str, object] = {"checked": False, "expected": None, "actual": None, "dirty": None}


def is_candidate_mode() -> bool:
    return bool(os.environ.get(ENV_EXPECTED_TREE))


def candidate_skip_reason(task_name: str) -> str | None:
    """候选模式下返回跳过原因（``candidate_mode:<理由码>``）；非候选模式或该任务照常运行时返回 None。"""
    if not is_candidate_mode():
        return None
    policy = CANDIDATE_MODE_POLICY.get(task_name)
    if policy is None:
        raise CandidateIdentityError(f"候选模式：启动任务 {task_name!r} 未在 CANDIDATE_MODE_POLICY 登记，拒绝启动")
    action, reason = policy
    return f"candidate_mode:{reason}" if action == "skip" else None


def get_candidate_tree_info() -> dict[str, object] | None:
    """health 用：非候选模式返回 None；候选模式返回启动时缓存的身份（请求期不调用 git）。"""
    if not is_candidate_mode():
        return None
    expected, actual, dirty = _state["expected"], _state["actual"], _state["dirty"]
    return {
        "expected": expected,
        "actual": actual,
        "dirty": dirty,
        "checked": bool(_state["checked"]),
        "match": bool(_state["checked"]) and expected is not None and expected == actual and dirty is False,
    }


def reset_state_for_tests() -> None:
    _state.update(checked=False, expected=None, actual=None, dirty=None)


def _git(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(_BACKEND_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def _option_name(arg: str) -> str:
    return arg.split("=", 1)[0]


def _check_launch_parameters(env: dict[str, str], argv: list[str]) -> list[str]:
    problems: list[str] = []
    if env.get("GT_BOOTSTRAP_DONE") != "1":
        problems.append("候选模式要求 GT_BOOTSTRAP_DONE=1（启动期不得执行迁移）")
    port = env.get("UVICORN_PORT", "")
    if not port.isdigit():
        problems.append(f"候选模式要求经 UVICORN_PORT 传入数字端口，实得 {port!r}")
    elif int(port) == SHARED_BACKEND_PORT:
        problems.append(f"候选端口不得是共享后端端口 {SHARED_BACKEND_PORT}")
    if env.get("UVICORN_HOST") != "127.0.0.1":
        problems.append(f"候选模式要求 UVICORN_HOST=127.0.0.1，实得 {env.get('UVICORN_HOST')!r}")
    problems.extend(f"候选模式不允许设置 {name}" for name in _FORBIDDEN_UVICORN_ENV if env.get(name))
    bad = sorted({_option_name(a) for a in argv if _option_name(a) in _FORBIDDEN_ARGV_OPTIONS})
    if bad:
        problems.append(f"候选模式不允许命令行参数 {bad}（端口与地址只经 UVICORN_PORT / UVICORN_HOST 传入）")
    return problems


def verify_candidate_identity(*, env: dict[str, str] | None = None, argv: list[str] | None = None) -> None:
    """启动任务：非候选模式直接返回（不调用 git）；候选模式下任一不符即抛 ``CandidateIdentityError``。"""
    env = dict(os.environ) if env is None else env
    expected = env.get(ENV_EXPECTED_TREE)
    if not expected:
        _state["checked"] = True
        return
    _state.update(checked=False, expected=expected, actual=None, dirty=None)
    if not _OID_RE.fullmatch(expected):
        raise CandidateIdentityError(f"{ENV_EXPECTED_TREE} 必须是 40 位小写十六进制，实得 {expected!r}")
    problems = _check_launch_parameters(env, list(sys.argv[1:] if argv is None else argv))
    if problems:
        raise CandidateIdentityError("候选实例启动参数不符：" + "；".join(problems))

    rc, actual = _git(["rev-parse", "HEAD^{tree}"])
    if rc != 0 or not _OID_RE.fullmatch(actual):
        raise CandidateIdentityError(f"无法解析候选 worktree 的 HEAD^{{tree}}（rc={rc}）：{actual}")
    rc_status, porcelain = _git(["status", "--porcelain", "--untracked-files=no"])
    dirty = rc_status != 0 or bool(porcelain)
    _state.update(actual=actual, dirty=dirty, checked=True)
    if dirty:
        raise CandidateIdentityError(f"候选 worktree 有受跟踪改动，拒绝启动：\n{porcelain}")
    if actual != expected:
        raise CandidateIdentityError(f"候选树身份不符：期望 {expected}，实际 {actual}")
    logger.info("[candidate_identity] 候选树身份一致：%s", actual)
