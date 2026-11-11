"""S2 Task 3（ADR-CCN-03）：校对目录执行状态。

- 守卫：登记了执行器入口的来源，入口必须存在、可调用，且生产代码（backend/app，排除定义处）真的调用它。
- 功能：每类来源带 ``execution``（wired / display_only / not_executable）；带 ``project_id`` 时带 ``last_run``
  （只读最近一次结果，不新增落库；无落库的来源为 null 并注明「本类结果不落库」）。
- 数据库：SQLite 真 ORM（tests/formula_settings/_env.make_db），不连共享 PG。
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.phase14_models import GateDecision
from app.models.workpaper_models import WorkingPaper, WpQcResult, WpSourceType
from app.models.wp_optimization_models import CrossCheckResult
from app.services import formula_check_catalog as cat
from app.services.formula_check_catalog import (
    SOURCES,
    CheckSource,
    _execution_status,
    build_check_catalog,
    wiring_problems,
)

from .formula_settings._env import add_member, add_project, add_user, make_db

RESULT_MODELS = (CrossCheckResult, GateDecision, WpQcResult, WorkingPaper)
T1 = datetime(2025, 6, 1, 8, 0, 0)
T2 = T1 + timedelta(days=1)
WIRED = [s for s in SOURCES if s.executor_entry is not None]
WIRED_KEYS = {
    "report_builtin", "cross_check_global", "report_audit", "consol_note_checks", "note_preset_checks",
    "wp_cross_account", "a17_consistency", "qc_rules",
}


# ── 执行状态判定 ──────────────────────────────────────────────────────────────


def _src(**kw) -> CheckSource:
    base = dict(key="t", label="", category="", runs_in="", edit_where="", loader=lambda: [])
    base.update(kw)
    return CheckSource(**base)


def test_no_executor_and_no_reason_is_display_only():
    assert _execution_status(_src()) == "display_only"


def test_no_executor_with_reason_is_not_executable():
    assert _execution_status(_src(unexecutable_reason="伪表达式")) == "not_executable"


def test_callable_executor_is_wired():
    src = _src(executor_entry="app.services.formula_check_catalog.build_check_catalog")
    assert _execution_status(src) == "wired"


def test_missing_executor_is_not_executable():
    src = _src(executor_entry="app.services.nonexistent_module.func")
    assert _execution_status(src) == "not_executable"


def test_every_source_says_why_it_is_in_its_state():
    for s in SOURCES:
        assert s.reason.strip(), f"{s.key} 缺执行状态说明（目录页要展示）"
        if _execution_status(s) == "not_executable":
            assert s.unexecutable_reason.strip(), f"{s.key} 不可执行但没写原因"


def test_result_tables_are_the_three_persisted_ones():
    tables = {s.result_table for s in SOURCES} - {None}
    assert tables == {"cross_check_results", "wp_qc_results", "gate_decisions"}


# ── 守卫：wired 入口真实存在且有生产调用 ─────────────────────────────────────────


def test_real_sources_wiring_is_complete():
    assert wiring_problems() == []


@pytest.mark.parametrize("source", WIRED, ids=lambda s: s.key)
def test_wired_entry_exists_and_is_called_by_production(source: CheckSource):
    assert _execution_status(source) == "wired", source.executor_entry
    assert wiring_problems((source,)) == []


def _only(key: str):
    return next(s for s in SOURCES if s.key == key)


def test_mutation_wired_entry_that_does_not_exist_turns_guard_red():
    """变异：某来源错标为有执行器，入口符号不存在 ⇒ 守卫必须报告（只看被改的那一条，不依赖磁盘上的真实登记）。"""
    mutated = dataclasses.replace(_only("a17_consistency"),
                                  executor_entry="app.services.a17_consistency_checker.no_such_entry")
    problems = wiring_problems((mutated,))
    assert len(problems) == 1 and problems[0].startswith("a17_consistency：执行器入口不存在")


def test_mutation_entry_that_exists_but_is_never_called_turns_guard_red():
    """变异：入口存在、可调用，但生产代码从不调用（只有测试在用）⇒ 守卫必须报告。"""
    mutated = dataclasses.replace(_only("qc_rules"),
                                  executor_entry="app.services.formula_check_catalog.registration_problems")
    problems = wiring_problems((mutated,))
    assert len(problems) == 1 and "没有生产代码调用" in problems[0]


# ── 目录响应（不带项目） ──────────────────────────────────────────────────────


async def test_catalog_counts_only_wired_sources():
    out = await build_check_catalog(None)
    assert all(s["execution"] in {"wired", "display_only", "not_executable"} for s in out["sources"])
    wired = [s for s in out["sources"] if s["execution"] == "wired"]
    assert {s["key"] for s in wired} == WIRED_KEYS
    assert out["wired_count"] == len(wired) == len(WIRED_KEYS)
    assert out["wired_rule_count"] == sum(s["rule_count"] for s in wired)
    by_key = {s["key"]: s["execution"] for s in out["sources"]}
    assert by_key["cycle_validation"] == "not_executable"
    assert by_key["cross_check_preset"] == "display_only"


async def test_without_project_no_last_run_and_persisted_sources_say_so():
    out = await build_check_catalog(None)
    for s in out["sources"]:
        assert s["last_run"] is None
        if s["result_table"] is None:
            assert s["last_run_note"] == "本类结果不落库"
        else:
            assert s["last_run_note"] == "未指定项目，未查询执行结果"


async def test_rules_in_a_filtered_response_carry_execution():
    out = await build_check_catalog(None, source="wp_cross_account")
    [src] = out["sources"]
    assert src["execution"] == "wired" and src["rules"]
    assert {r["execution"] for r in src["rules"]} == {"wired"}


# ── 带项目：last_run（SQLite 真 ORM） ───────────────────────────────────────────


def _cc(pid, rule_id, status, at, year=2025):
    return CrossCheckResult(id=uuid.uuid4(), project_id=pid, year=year, rule_id=rule_id, status=status, checked_at=at)


async def _seed(db, pid, other_pid):
    db.add_all([
        _cc(pid, "report-cross-check-1", "failed", T1),
        _cc(pid, "report-cross-check-1", "passed", T2),  # 同一规则取最近一次
        _cc(pid, "report-cross-check-2", "failed", T1),
        _cc(pid, "user:0123456789abcdef", "passed", T1),
        _cc(pid, "XR-01", "pass", T1),
        _cc(pid, "XR-02", "skip", T1),
        _cc(pid, "XR-03", "pass", T1),
        _cc(pid, "XR-99", "rule_definition", T1),  # 规则定义行不是运行结论
        _cc(other_pid, "XR-05", "fail", T2),  # 他项目的结论不计入
    ])
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=uuid.uuid4(), file_path="a.xlsx",
                      source_type=list(WpSourceType)[0])
    wp2 = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=uuid.uuid4(), file_path="b.xlsx",
                       source_type=list(WpSourceType)[0])
    db.add_all([wp, wp2])
    await db.flush()
    db.add_all([
        WpQcResult(id=uuid.uuid4(), working_paper_id=wp.id, check_timestamp=T1, findings={}, passed=True,
                   blocking_count=0),
        WpQcResult(id=uuid.uuid4(), working_paper_id=wp.id, check_timestamp=T2, findings={}, passed=False,
                   blocking_count=2),
        WpQcResult(id=uuid.uuid4(), working_paper_id=wp2.id, check_timestamp=T1, findings={}, passed=True,
                   blocking_count=0),
    ])
    db.add_all([
        GateDecision(id=uuid.uuid4(), project_id=pid, gate_type="sign_off", decision="warn",
                     hit_rules=[{"rule_code": "X"}], actor_id=uuid.uuid4(), trace_id="t1", created_at=T1),
        GateDecision(id=uuid.uuid4(), project_id=pid, gate_type="sign_off", decision="block",
                     hit_rules=[{"rule_code": "A"}, {"rule_code": "B"}], actor_id=uuid.uuid4(), trace_id="t2",
                     created_at=T2),
        GateDecision(id=uuid.uuid4(), project_id=pid, gate_type="export_package", decision="allow",
                     hit_rules=[], actor_id=uuid.uuid4(), trace_id="t3", created_at=T2 + timedelta(days=1)),
    ])
    await db.flush()


async def test_last_run_reads_each_persisted_table_latest_per_rule():
    async with make_db(RESULT_MODELS) as factory, factory() as db:
        pid = await add_project(db, "目录")
        other = await add_project(db, "他项目")
        await _seed(db, pid, other)
        await db.commit()
        out = await build_check_catalog(db, project_id=pid)
    by_key = {s["key"]: s for s in out["sources"]}

    rep = by_key["report_builtin"]["last_run"]
    assert (rep["status"], rep["counts"], rep["at"], rep["year"]) == ("failed", {"passed": 1, "failed": 1},
                                                                      T2.isoformat(), 2025)
    assert by_key["cross_check_global"]["last_run"]["counts"] == {"passed": 1}
    xr = by_key["wp_cross_account"]["last_run"]
    assert (xr["status"], xr["counts"]) == ("not_executed", {"pass": 2, "skip": 1})
    qc = by_key["qc_rules"]["last_run"]
    assert (qc["status"], qc["counts"]) == ("failed", {"working_papers": 2, "passed": 1, "failed": 1, "blocking": 2})
    gate = by_key["cycle_validation"]["last_run"]
    assert (gate["status"], gate["counts"]) == ("block", {"hit_rules": 2})


async def test_last_run_never_run_and_not_persisted_sources():
    async with make_db(RESULT_MODELS) as factory, factory() as db:
        pid = await add_project(db, "空项目")
        await db.commit()
        out = await build_check_catalog(db, project_id=pid)
    by_key = {s["key"]: s for s in out["sources"]}
    for key in ("report_builtin", "cross_check_global", "wp_cross_account", "qc_rules", "cycle_validation"):
        assert by_key[key]["last_run"] == {"at": None, "status": "never_run", "counts": {}}, key
    for key in ("cross_check_preset", "report_audit", "consol_note_checks", "note_preset_checks", "a17_consistency"):
        assert by_key[key]["last_run"] is None and by_key[key]["last_run_note"] == "本类结果不落库", key


# ── 端点（TestClient 真发请求） ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def api():
    async with make_db(RESULT_MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "端点目录")
            other = await add_project(db, "他项目")
            member = await add_user(db, "catalog_member")
            outsider = await add_user(db, "catalog_outsider")
            await add_member(db, pid, member, "edit")
            await _seed(db, pid, other)
            await db.commit()

        from app.routers.formula_catalog import router

        app = FastAPI()
        app.include_router(router)
        state = {"user": member}

        async def _db():
            async with factory() as s:
                yield s

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: state["user"]
        url = "/api/formula-catalog/check-rules"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield {"c": c, "url": url, "pid": pid, "state": state, "outsider": outsider}


async def test_endpoint_without_project_serves_execution_to_any_login(api):
    api["state"]["user"] = api["outsider"]  # 非项目成员也能看目录（无项目数据）
    resp = await api["c"].get(api["url"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["wired_count"] == len(WIRED_KEYS)
    assert all("last_run" in s and s["last_run"] is None for s in body["sources"])


async def test_endpoint_with_project_returns_last_run_for_member(api):
    resp = await api["c"].get(api["url"], params={"project_id": str(api["pid"])})
    assert resp.status_code == 200
    by_key = {s["key"]: s for s in resp.json()["sources"]}
    assert by_key["report_builtin"]["execution"] == "wired"
    assert by_key["report_builtin"]["last_run"]["status"] == "failed"
    assert by_key["wp_cross_account"]["last_run"]["counts"] == {"pass": 2, "skip": 1}
    assert by_key["qc_rules"]["last_run"]["counts"]["working_papers"] == 2
    assert by_key["cycle_validation"]["last_run"]["status"] == "block"
    assert by_key["cross_check_preset"]["last_run"] is None
    assert by_key["cross_check_preset"]["last_run_note"] == "本类结果不落库"
    assert by_key["cycle_validation"]["execution"] == "not_executable"


async def test_endpoint_with_project_rejects_non_member(api):
    api["state"]["user"] = api["outsider"]
    resp = await api["c"].get(api["url"], params={"project_id": str(api["pid"])})
    assert resp.status_code == 403


async def test_endpoint_unknown_source_is_404(api):
    resp = await api["c"].get(api["url"], params={"source": "nope"})
    assert resp.status_code == 404


async def test_persisted_source_read_failure_only_marks_that_source(api, monkeypatch):
    async def boom(db, source, project_id):
        raise RuntimeError("库暂不可读")

    monkeypatch.setattr(cat, "_last_run_qc", boom)
    resp = await api["c"].get(api["url"], params={"project_id": str(api["pid"])})
    by_key = {s["key"]: s for s in resp.json()["sources"]}
    assert by_key["qc_rules"]["last_run"]["status"] == "unavailable"
    assert by_key["report_builtin"]["last_run"]["status"] == "failed"
