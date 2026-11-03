"""``realign_project_notes.py --push`` 单事务推送、退出码与 ``--restore`` 后像围栏（spec 49 Phase 8 加固）。

- ``_push``：同一事务里 快照 → 预演 → 备份 → 推送 → 再预演 → 判定 → 补记后像 → 提交，提交后才发通知；
  部分失败 / 冲突 / 不幂等整体回滚；推送不到的目标不挡提交但退出码 2。
- 恢复：默认只预演；``--apply`` 现状须与后像逐行一致，否则在任何写入之前拒绝（``force`` 才继续）。
PostgreSQL 上的真实 SQL 与 REPEATABLE READ 语义由 ``test_note_project_realign_backup_pg.py`` 守护。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.services.formula_push.results import CONFLICT, SKIPPED, PushItem, RunResult

BACKEND = Path(__file__).resolve().parents[1]
PID = uuid.UUID("94a40b23-21a2-4d7a-a38d-9fd059d57717")
YEAR = 2025


def _script():
    spec = importlib.util.spec_from_file_location(
        "_realign_project_notes_under_test", BACKEND / "scripts/fix/realign_project_notes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Session:
    def __init__(self, log: list):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


def _result(*, status: str = "succeeded", writes: int = 0, skipped: int = 0, conflicts: int = 0) -> RunResult:
    r = RunResult(project_id=PID, year=YEAR, trigger="manual", status=status)
    r.items += [PushItem("r", "note", "note", f"note://w{i}", "write") for i in range(writes)]
    r.items += [PushItem("r", "note", "note", f"note://s{i}", SKIPPED, reason="附注表格无法定位") for i in range(skipped)]
    r.items += [PushItem("r", "workpaper", "workpaper", f"wp://c{i}", CONFLICT, reason="并发修改") for i in range(conflicts)]
    return r


@pytest.fixture
def push_env(monkeypatch, tmp_path):
    from app.services import note_project_realign_apply as svc
    from app.services import note_readiness_service as readiness
    from app.services.formula_push import engine as push

    log: list = []
    state: dict[str, Any] = {"results": [], "raise_on_real": None}

    async def fake_run(db, *, project_id, year, trigger, dry_run=False, **_kw):
        log.append(("run", dry_run))
        if not dry_run and state["raise_on_real"] is not None:
            raise state["raise_on_real"]
        return state["results"].pop(0)

    async def fake_notify(result):
        log.append("notify")

    async def fake_snapshot(db):
        log.append("snapshot")

    async def fake_backup(db, project_id, year, path, *, include_workpapers=False):
        log.append(("backup", include_workpapers))
        return {"path": str(path), "counts": {}}

    async def fake_postimage(db, path):
        log.append("postimage")
        return {"counts": {}}

    async def fake_validation(db, project_id, year):
        return {"passed": True}

    monkeypatch.setattr(push, "run", fake_run)
    monkeypatch.setattr(push, "notify_committed", fake_notify)
    monkeypatch.setattr(svc, "begin_snapshot", fake_snapshot)
    monkeypatch.setattr(svc, "write_backup", fake_backup)
    monkeypatch.setattr(svc, "record_postimage", fake_postimage)
    monkeypatch.setattr(readiness, "run_validation_best_effort", fake_validation)
    mod = _script()

    async def go(apply: bool = True) -> dict:
        return await mod._push(lambda: _Session(log), PID, YEAR, apply=apply, backup_dir=tmp_path, stamp="t")

    return mod, log, state, go


async def test_clean_push_is_one_transaction_and_notifies_only_after_commit(push_env):
    mod, log, state, go = push_env
    state["results"] = [_result(writes=3), _result(writes=3), _result()]
    report = await go()
    assert log == ["snapshot", ("run", True), ("backup", True), ("run", False), ("run", True),
                   "postimage", "commit", "notify"]
    assert "error" not in report and report["attention"] is None
    assert report["validation"] == {"passed": True}
    assert mod._exit_code([report]) == 0


@pytest.mark.parametrize("results, needle", [
    ([_result(writes=1), _result(status="partial", writes=1, conflicts=1), _result()], "推送状态 partial"),
    ([_result(writes=1), _result(writes=1), _result(writes=2)], "仍有 2 格要写"),
    ([_result(writes=1), _result(writes=1), _result(status="partial")], "再预演状态 partial"),
])
async def test_partial_or_non_idempotent_push_rolls_back_everything(push_env, results, needle):
    mod, log, state, go = push_env
    state["results"] = results
    report = await go()
    assert log[-1] == "rollback"
    assert "commit" not in log and "notify" not in log and "postimage" not in log
    assert needle in report["error"] and "已回滚" in report["error"]
    assert mod._exit_code([report]) == 1


async def test_exception_during_push_rolls_back_with_type_in_report(push_env):
    mod, log, state, go = push_env
    state["results"] = [_result(writes=1)]
    state["raise_on_real"] = RuntimeError("boom")
    report = await go()
    assert log == ["snapshot", ("run", True), ("backup", True), ("run", False), "rollback"]
    assert report["error"].startswith("RuntimeError: boom")


async def test_unresolved_targets_commit_but_exit_two(push_env):
    mod, log, state, go = push_env
    state["results"] = [_result(writes=1, skipped=2), _result(writes=1, skipped=2), _result(skipped=2)]
    report = await go()
    assert log[-2:] == ["commit", "notify"]
    assert report["attention"]["unresolved"] == 2
    assert report["attention"]["by_reason"] == {"note:附注表格无法定位": 2}
    assert mod._exit_code([report]) == 2
    assert "待人工" in mod._push_report_line(report)


async def test_dry_run_only_previews(push_env):
    mod, log, state, go = push_env
    state["results"] = [_result(writes=4, skipped=1)]
    report = await go(apply=False)
    assert log == [("run", True), "rollback"]
    assert "backup" not in report and report["attention"]["unresolved"] == 1


def test_exit_code_precedence():
    mod = _script()
    assert mod._exit_code([{"attention": {"x": 1}}, {"error": "失败"}]) == 1
    assert mod._exit_code([{"attention": None}, {"attention": {"x": 1}}]) == 2
    assert mod._exit_code([{"attention": None}, {}]) == 0


def test_force_restore_requires_restore_apply(monkeypatch):
    mod = _script()
    monkeypatch.setattr(sys, "argv", ["realign_project_notes.py", "--restore", "x.json", "--force-restore"])
    import asyncio

    with pytest.raises(SystemExit) as exc:
        asyncio.run(mod.main())
    assert exc.value.code == 2


# ── 恢复 CLI 包装 ─────────────────────────────────────────────────────────────


@pytest.fixture
def restore_env(monkeypatch):
    from app.services import note_project_realign_apply as svc

    log: list = []
    state: dict[str, Any] = {}

    async def fake_snapshot(db):
        log.append("snapshot")

    async def fake_plan(db, path):
        log.append("plan")
        return state["plan"]

    async def fake_restore(db, path, *, force=False):
        log.append(("restore", force))
        if "raise" in state:
            raise state["raise"]
        return state["restored"]

    monkeypatch.setattr(svc, "begin_snapshot", fake_snapshot)
    monkeypatch.setattr(svc, "plan_restore", fake_plan)
    monkeypatch.setattr(svc, "restore_backup", fake_restore)
    return _script(), log, state


def _plan(fence: str, drift: dict | None = None) -> dict:
    return {"project_id": str(PID), "year": YEAR, "fence": fence, "drift": drift or {},
            "delta": {"disclosure_notes": {"delete": 1, "insert": 0, "change": 2}}}


async def test_restore_defaults_to_preview_and_flags_unfenced(restore_env, tmp_path):
    mod, log, state = restore_env
    state["plan"] = _plan("mismatch", {"disclosure_notes": ["a", "b"]})
    report = await mod._restore(lambda: _Session(log), tmp_path / "b.json", apply=False, force=False)
    assert log == ["plan", "rollback"]
    assert report["attention"] == {"fence": "mismatch", "drift": {"disclosure_notes": 2}}
    assert mod._exit_code([report]) == 2
    assert "操作后变化 disclosure_notes 2 行" in mod._restore_line(report)


async def test_restore_apply_uses_snapshot_and_commits(restore_env, tmp_path):
    mod, log, state = restore_env
    state["restored"] = {**_plan("ok"), "restored": True, "forced": False, "counts": {"disclosure_notes": 3}}
    report = await mod._restore(lambda: _Session(log), tmp_path / "b.json", apply=True, force=False)
    assert log == ["snapshot", ("restore", False), "commit"]
    assert mod._exit_code([report]) == 0 and mod._restore_line(report).startswith("✓ 已恢复")


async def test_restore_refusal_rolls_back(restore_env, tmp_path):
    from app.services.note_project_realign_apply import RealignError

    mod, log, state = restore_env
    state["raise"] = RealignError("后像围栏不放行（unfenced）")
    report = await mod._restore(lambda: _Session(log), tmp_path / "b.json", apply=True, force=True)
    assert log == ["snapshot", ("restore", True), "rollback"]
    assert mod._exit_code([report]) == 1 and "后像围栏不放行" in mod._restore_line(report)


# ── 服务层围栏判定（export_rows 用内存数据替身；真实 SQL 见 PG 守卫）────────


def _rows(**values: str) -> list[dict[str, Any]]:
    return [{"id": k, "row": json.dumps({"id": k, "v": v}), "json_null": []} for k, v in sorted(values.items())]


@pytest.fixture
def fence_env(monkeypatch, tmp_path):
    from app.services import note_project_realign_apply as svc

    current: dict[str, Any] = {}

    def snapshot(**notes: str) -> dict[str, list]:
        return {t: (_rows(**notes) if t == "disclosure_notes" else []) for t in svc.BACKUP_TABLES}

    async def fake_export(db, project_id, year, *, include_workpapers=False):
        return json.loads(json.dumps(current["tables"]))

    monkeypatch.setattr(svc, "_require_pg", lambda db: None)
    monkeypatch.setattr(svc, "export_rows", fake_export)
    return svc, current, snapshot, tmp_path / "note_push_backup.json"


class _RecordingDb:
    def __init__(self, on_write):
        self.statements: list[str] = []
        self.on_write = on_write

    async def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        self.on_write()


async def test_postimage_round_trip_and_fence_states(fence_env):
    svc, current, snapshot, path = fence_env
    current["tables"] = snapshot(a="原值", b="原值")
    await svc.write_backup(None, PID, YEAR, path)
    current["tables"] = snapshot(a="操作后", b="原值", c="新增")  # 本次操作的结果
    await svc.record_postimage(None, path)
    assert not path.with_name(path.name + ".tmp").exists()
    assert set(json.loads(path.read_text("utf-8"))["postimage"]["rows"]["disclosure_notes"]) == {"a", "b", "c"}

    plan = await svc.plan_restore(None, path)
    assert plan["fence"] == "ok" and plan["drift"] == {}
    assert plan["delta"]["disclosure_notes"] == {"delete": 1, "insert": 0, "change": 1}

    current["tables"] = snapshot(a="操作后", b="别人改了", c="新增")
    plan = await svc.plan_restore(None, path)
    assert plan["fence"] == "mismatch" and plan["drift"] == {"disclosure_notes": ["b"]}

    current["tables"] = snapshot(a="操作后", b="原值")  # 别人删了 c
    assert (await svc.plan_restore(None, path))["drift"] == {"disclosure_notes": ["c"]}

    current["tables"] = snapshot(a="原值", b="原值")
    assert (await svc.plan_restore(None, path))["fence"] == "already_restored"


async def test_unfenced_backup_is_reported(fence_env):
    svc, current, snapshot, path = fence_env
    current["tables"] = snapshot(a="原值")
    await svc.write_backup(None, PID, YEAR, path)
    current["tables"] = snapshot(a="操作后")
    assert (await svc.plan_restore(None, path))["fence"] == "unfenced"


@pytest.mark.parametrize("post_edit, record", [({"a": "操作后", "b": "别人改了"}, True), ({"a": "操作后", "b": "原值"}, False)])
async def test_restore_refuses_before_any_write_unless_forced(fence_env, post_edit, record):
    svc, current, snapshot, path = fence_env
    current["tables"] = snapshot(a="原值", b="原值")
    await svc.write_backup(None, PID, YEAR, path)
    backup_tables = json.loads(path.read_text("utf-8"))["tables"]
    current["tables"] = snapshot(a="操作后", b="原值")
    if record:
        await svc.record_postimage(None, path)
    current["tables"] = snapshot(**post_edit)

    db = _RecordingDb(lambda: current.__setitem__("tables", backup_tables))
    with pytest.raises(svc.RealignError, match="后像围栏不放行"):
        await svc.restore_backup(db, path)
    assert db.statements == []  # 围栏在任何 DELETE / INSERT 之前拒绝

    result = await svc.restore_backup(db, path, force=True)
    assert result["restored"] is True and result["forced"] is True
    assert any(s.startswith("DELETE FROM disclosure_notes") for s in db.statements)


async def test_fenced_restore_runs_and_noop_when_already_restored(fence_env):
    svc, current, snapshot, path = fence_env
    current["tables"] = snapshot(a="原值")
    await svc.write_backup(None, PID, YEAR, path)
    backup_tables = json.loads(path.read_text("utf-8"))["tables"]
    current["tables"] = snapshot(a="操作后")
    await svc.record_postimage(None, path)

    db = _RecordingDb(lambda: current.__setitem__("tables", backup_tables))
    result = await svc.restore_backup(db, path)
    assert result["restored"] is True and result["forced"] is False and result["fence"] == "ok"

    db_again = _RecordingDb(lambda: None)
    again = await svc.restore_backup(db_again, path)
    assert again["restored"] is False and again["fence"] == "already_restored" and db_again.statements == []


async def test_begin_snapshot_refuses_non_postgres():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services.note_project_realign_apply import RealignError, begin_snapshot

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with AsyncSession(engine) as db:
            with pytest.raises(RealignError, match="PostgreSQL"):
                await begin_snapshot(db)
    finally:
        await engine.dispose()
