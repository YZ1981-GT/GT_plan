"""候选验证实例的身份校验与启动隔离（platform-global-display-settings-closure 13A，design §16 F2·F3）。

候选实例与共享后端连同一 PG / Redis：启动时绝不能跑迁移、重放共享事件、认领他人的作业。
下面的 ``EXPECTED_SKIP`` 是独立于 ``CANDIDATE_MODE_POLICY`` 写死的裁决清单 —— 把任一 skip 改成 run，
「跳过的任务一次也不被调用」就会红（用策略本身推导期望值会让判据恒绿）。
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.core import candidate_identity as ci
from app.core import startup_registry as startup

BACKEND = Path(__file__).resolve().parents[1]
GOOD_OID = "0123456789abcdef0123456789abcdef01234567"

EXPECTED_SKIP = {
    "run_migrations", "replay_startup_events", "run_schema_drift_check", "seed_builtin_template_sets",
    "acnr_invalidation_outbox_start", "recover_ai_chat_runs", "run_ai_chat_health_check",
    "acnr_catalog_snapshot_gc", "warm_workpaper_sync_registry", "prewarm_openapi_schema",
    *startup.WORKER_TASK_NAMES,
}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv(ci.ENV_EXPECTED_TREE, raising=False)
    ci.reset_state_for_tests()
    startup.reset_startup_report()
    yield
    ci.reset_state_for_tests()
    startup.reset_startup_report()


def _candidate_env(**overrides: str) -> dict[str, str]:
    env = {
        ci.ENV_EXPECTED_TREE: GOOD_OID, "GT_BOOTSTRAP_DONE": "1",
        "UVICORN_PORT": "9993", "UVICORN_HOST": "127.0.0.1",
    }
    env.update(overrides)
    return {k: v for k, v in env.items() if v != "<unset>"}


# ── 策略闭集 ───────────────────────────────────────────────────────────────

def test_policy_keys_equal_registry_task_names():
    names = [spec.name for spec in startup.STARTUP_TASKS]
    assert len(names) == len(set(names))
    assert set(ci.CANDIDATE_MODE_POLICY) == set(names)


def test_policy_reason_codes_are_closed_and_match_action():
    for name, (action, reason) in ci.CANDIDATE_MODE_POLICY.items():
        allowed = ci.SKIP_REASONS if action == "skip" else ci.RUN_REASONS
        assert action in ("run", "skip") and reason in allowed, name


def test_policy_skip_set_equals_reviewed_list():
    skipped = {name for name, (action, _r) in ci.CANDIDATE_MODE_POLICY.items() if action == "skip"}
    assert skipped == EXPECTED_SKIP
    assert ci.CANDIDATE_MODE_POLICY[ci.IDENTITY_TASK_NAME][0] == "run"
    assert ci.CANDIDATE_MODE_POLICY["migration_mark_complete"] == ("run", "read_only_sql")


def test_identity_task_runs_right_after_logging_and_before_migrations():
    names = [spec.name for spec in startup.STARTUP_TASKS]
    assert names.index(ci.IDENTITY_TASK_NAME) == names.index("setup_logging") + 1
    assert names.index(ci.IDENTITY_TASK_NAME) < names.index("run_migrations")
    spec = next(s for s in startup.STARTUP_TASKS if s.name == ci.IDENTITY_TASK_NAME)
    assert spec.criticality == "critical"


# ── 执行器按策略跳过 ───────────────────────────────────────────────────────

def _recording_registry(calls: list[str]) -> tuple[startup.StartupTaskSpec, ...]:
    def make(name: str):
        def run(_ctx):
            calls.append(name)
        return run

    return tuple(
        dataclasses.replace(spec, run=make(spec.name), skip_condition=None, singleton=False)
        for spec in startup.STARTUP_TASKS
    )


def test_candidate_mode_never_calls_skipped_tasks(monkeypatch):
    monkeypatch.setenv(ci.ENV_EXPECTED_TREE, GOOD_OID)
    calls: list[str] = []
    results = asyncio.run(startup.run_startup_tasks(_recording_registry(calls)))
    assert set(calls) == {spec.name for spec in startup.STARTUP_TASKS} - EXPECTED_SKIP
    by_name = {r.name: r for r in results}
    for name in EXPECTED_SKIP:
        reason = ci.CANDIDATE_MODE_POLICY[name][1]
        assert (by_name[name].status, by_name[name].detail) == ("skipped", f"candidate_mode:{reason}"), name


def test_normal_mode_runs_every_task():
    calls: list[str] = []
    asyncio.run(startup.run_startup_tasks(_recording_registry(calls)))
    assert calls == [spec.name for spec in startup.STARTUP_TASKS]


def test_unregistered_task_refuses_candidate_start(monkeypatch):
    monkeypatch.setenv(ci.ENV_EXPECTED_TREE, GOOD_OID)
    rogue = startup.StartupTaskSpec(name="rogue_writer", phase="x", criticality="best_effort", run=lambda _c: None)
    with pytest.raises(ci.CandidateIdentityError, match="rogue_writer"):
        asyncio.run(startup.run_startup_tasks((rogue,)))
    report = startup.get_startup_report()
    assert report is not None and [(r.name, r.status) for r in report] == [("rogue_writer", "failed")]


def test_batch_worker_starter_starts_nothing_in_candidate_mode(monkeypatch):
    started: list[str] = []
    fake = tuple(
        dataclasses.replace(spec, run=lambda _ctx, n=spec.name: started.append(n), skip_condition=None)
        for spec in startup._worker_specs()
    )
    monkeypatch.setattr(startup, "_worker_specs", lambda: fake)
    monkeypatch.setenv(ci.ENV_EXPECTED_TREE, GOOD_OID)
    startup.start_all_workers(asyncio.Event())
    assert started == []
    monkeypatch.delenv(ci.ENV_EXPECTED_TREE)
    startup.start_all_workers(asyncio.Event())
    assert started == list(startup.WORKER_TASK_NAMES)


# ── 身份校验 ───────────────────────────────────────────────────────────────

def test_non_candidate_mode_never_calls_git(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("非候选模式不得调用 git")

    monkeypatch.setattr(ci.subprocess, "run", boom)
    ci.verify_candidate_identity(env={}, argv=[])
    assert ci.get_candidate_tree_info() is None
    assert ci.candidate_skip_reason("run_migrations") is None


def _stub_git(monkeypatch, tree: str = GOOD_OID, porcelain: str = "") -> list[list[str]]:
    seen: list[list[str]] = []

    def fake(args):
        seen.append(list(args))
        return (0, tree) if args[0] == "rev-parse" else (0, porcelain)

    monkeypatch.setattr(ci, "_git", fake)
    return seen


def test_matching_clean_tree_passes_and_is_cached(monkeypatch):
    seen = _stub_git(monkeypatch)
    monkeypatch.setenv(ci.ENV_EXPECTED_TREE, GOOD_OID)
    ci.verify_candidate_identity(env=_candidate_env(), argv=["app.main:app"])
    assert seen == [["rev-parse", "HEAD^{tree}"], ["status", "--porcelain", "--untracked-files=no"]]
    info = ci.get_candidate_tree_info()
    assert info == {"expected": GOOD_OID, "actual": GOOD_OID, "dirty": False, "checked": True, "match": True}


@pytest.mark.parametrize(
    ("env_overrides", "argv", "message"),
    [
        ({ci.ENV_EXPECTED_TREE: "ABC"}, [], "40 位小写十六进制"),
        ({"GT_BOOTSTRAP_DONE": "<unset>"}, [], "GT_BOOTSTRAP_DONE=1"),
        ({"UVICORN_PORT": "9980"}, [], "9980"),
        ({"UVICORN_PORT": "<unset>"}, [], "UVICORN_PORT"),
        ({"UVICORN_HOST": "0.0.0.0"}, [], "UVICORN_HOST"),
        ({"UVICORN_RELOAD": "true"}, [], "UVICORN_RELOAD"),
        ({}, ["app.main:app", "--port", "9980"], "--port"),
        ({}, ["app.main:app", "--reload=true"], "--reload"),
    ],
)
def test_bad_launch_parameters_refuse_start(monkeypatch, env_overrides, argv, message):
    seen = _stub_git(monkeypatch)
    with pytest.raises(ci.CandidateIdentityError, match=message):
        ci.verify_candidate_identity(env=_candidate_env(**env_overrides), argv=argv)
    assert seen == [], "启动参数不符时不应再去解析 git"


def test_tree_mismatch_refuses_start(monkeypatch):
    _stub_git(monkeypatch, tree="f" * 40)
    with pytest.raises(ci.CandidateIdentityError, match="身份不符"):
        ci.verify_candidate_identity(env=_candidate_env(), argv=[])


def test_tracked_changes_refuse_start(monkeypatch):
    _stub_git(monkeypatch, porcelain=" M backend/app/main.py")
    with pytest.raises(ci.CandidateIdentityError, match="受跟踪改动"):
        ci.verify_candidate_identity(env=_candidate_env(), argv=[])


def test_git_failure_refuses_start(monkeypatch):
    monkeypatch.setattr(ci, "_git", lambda args: (128, "fatal: not a git repository"))
    with pytest.raises(ci.CandidateIdentityError, match="无法解析"):
        ci.verify_candidate_identity(env=_candidate_env(), argv=[])


def test_git_runs_in_backend_directory(monkeypatch):
    captured: dict[str, object] = {}

    class _Done:
        returncode = 0
        stdout = GOOD_OID
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, cwd=kwargs.get("cwd"))
        return _Done()

    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    assert ci._git(["rev-parse", "HEAD^{tree}"]) == (0, GOOD_OID)
    assert captured["cmd"] == ["git", "rev-parse", "HEAD^{tree}"]
    assert Path(str(captured["cwd"])) == BACKEND


# ── health 暴露 ────────────────────────────────────────────────────────────

def test_health_candidate_block_null_outside_candidate_mode():
    from app.api import health

    assert health._candidate_tree_info(None) is None
    assert health._candidate_tree_headers(None) == {}


def test_health_candidate_block_reports_identity_and_port(monkeypatch):
    from app.api import health

    _stub_git(monkeypatch)
    monkeypatch.setenv(ci.ENV_EXPECTED_TREE, GOOD_OID)
    ci.verify_candidate_identity(env=_candidate_env(), argv=[])

    class _Req:
        scope = {"server": ("127.0.0.1", 9993)}

    info = health._candidate_tree_info(_Req())
    assert info is not None and info["match"] is True and info["server_port"] == 9993
    assert health._candidate_tree_headers(info) == {
        "X-GT-Candidate-Tree-Expected": GOOD_OID, "X-GT-Candidate-Tree-Actual": GOOD_OID,
    }


# ── run_uvicorn 预引导不跑迁移 ─────────────────────────────────────────────

_PROBE = textwrap.dedent(
    """
    import os, runpy, sys
    from pathlib import Path
    sys.path.insert(0, os.environ["PROBE_BACKEND"])
    from app.core import migration_runner

    async def _marker(self):
        Path(os.environ["PROBE_MARKER"]).write_text("ran", encoding="utf-8")
        return migration_runner.RunPendingResult(executed=[], failed=[])

    migration_runner.MigrationRunner.run_pending = _marker
    runpy.run_path(str(Path(os.environ["PROBE_BACKEND"]) / "run_uvicorn.py"), run_name="candidate_probe")
    print("BOOTSTRAP_DONE=" + os.environ.get("GT_BOOTSTRAP_DONE", ""))
    """
)


def _run_probe(tmp_path: Path, **extra_env: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    marker = tmp_path / "migration_ran.txt"
    script = tmp_path / "probe.py"
    script.write_text(_PROBE, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (ci.ENV_EXPECTED_TREE, "GT_BOOTSTRAP_DONE")}
    env.update(
        PROBE_BACKEND=str(BACKEND), PROBE_MARKER=str(marker), PYTHONIOENCODING="utf-8",
        DATABASE_URL=f"sqlite+aiosqlite:///{(tmp_path / 'probe.db').as_posix()}", **extra_env,
    )
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=str(BACKEND), env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    return proc, marker


def test_run_uvicorn_candidate_without_bootstrap_marker_refuses_before_migration(tmp_path):
    proc, marker = _run_probe(tmp_path, **{ci.ENV_EXPECTED_TREE: GOOD_OID})
    assert proc.returncode == 2
    assert "GT_BOOTSTRAP_DONE=1" in proc.stderr
    assert not marker.exists(), "候选模式拒绝启动前执行了迁移"


def test_run_uvicorn_candidate_with_bootstrap_marker_skips_migration(tmp_path):
    proc, marker = _run_probe(tmp_path, **{ci.ENV_EXPECTED_TREE: GOOD_OID, "GT_BOOTSTRAP_DONE": "1"})
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "BOOTSTRAP_DONE=1" in proc.stdout
    assert not marker.exists(), "候选模式下预引导执行了迁移"


def test_run_uvicorn_normal_mode_still_runs_pre_bootstrap_migration(tmp_path):
    """阴性对照：同一探针在非候选模式下确实会执行（证明上一条不是探针本身失效）。"""
    proc, marker = _run_probe(tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert marker.read_text(encoding="utf-8") == "ran"
