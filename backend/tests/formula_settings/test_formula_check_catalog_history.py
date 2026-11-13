"""R3 历史口径：只用隔离 SQLite 内存库与真实 ORM；不连接平台服务或共享 PG。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.phase14_models import GateDecision
from app.models.workpaper_models import WorkingPaper, WpIndex, WpQcResult, WpSourceType
from app.models.wp_optimization_models import CrossCheckResult
from app.services import formula_check_catalog as cat

from ._env import add_project, make_db

STAMP = datetime(2025, 3, 1, 10)


def result(pid, year, rule_id, status, hours=0):
    return CrossCheckResult(project_id=pid, year=year, rule_id=rule_id, status=status,
                            checked_at=STAMP + timedelta(hours=hours))


async def test_requested_year_is_filtered_before_aggregation_and_missing_year_is_never_run():
    async with make_db(extra_models=(CrossCheckResult,)) as factory, factory() as db:
        pid = await add_project(db, "【测试】目录年度")
        other = await add_project(db, "【测试】目录其他项目")
        db.add_all([
            result(pid, 2024, "report-cross-check-1", "fail", 0),
            result(pid, 2024, "report-cross-check-1", "pass", 1),
            result(pid, 2024, "report-cross-check-2", "fail", 2),
            result(pid, 2024, "report-cross-check-definition", "rule_definition", 99),
            result(pid, 2025, "report-cross-check-1", "pass", 3),
            result(pid, 2024, "user:unrelated", "error", 9),
            result(other, 2024, "report-cross-check-3", "error", 10),
        ])
        await db.flush()
        selected = (await cat.build_check_catalog(db, source="report_builtin", project_id=pid, year=2024))["sources"][0]
        assert selected["last_run"] == {"at": (STAMP + timedelta(hours=2)).isoformat(), "status": "failed",
                                        "counts": {"fail": 1, "pass": 1}, "year": 2024}
        assert "逐规则最新" in selected["last_run_note"] and "并非单次运行快照" in selected["last_run_note"]
        missing = (await cat.build_check_catalog(db, source="report_builtin", project_id=pid, year=2023))["sources"][0]
        assert missing["last_run"] == {"at": None, "status": "never_run", "counts": {}, "year": 2023}
        latest = (await cat.build_check_catalog(db, source="report_builtin", project_id=pid))["sources"][0]
        assert latest["last_run"]["year"] == 2025 and latest["last_run"]["counts"] == {"pass": 1}
        assert latest["last_run"]["status"] == "passed"


@pytest.mark.parametrize(("source_key", "own_rule", "foreign_rule"), [
    ("report_builtin", "report-cross-check-1", "XR-1"),
    ("cross_check_global", "user:slot", "report-cross-check-1"),
    ("wp_cross_account", "XR-1", "user:slot"),
])
async def test_shared_result_table_filters_each_source(source_key, own_rule, foreign_rule):
    source = next(s for s in cat.SOURCES if s.key == source_key)
    async with make_db(extra_models=(CrossCheckResult,)) as factory, factory() as db:
        pid = await add_project(db, "【测试】目录来源")
        db.add_all([result(pid, 2025, own_rule, "pass"), result(pid, 2025, foreign_rule, "fail", 1)])
        await db.flush()
        history = await cat._last_run(db, source, pid, 2025)
        assert history["status"] == "passed" and history["counts"] == {"pass": 1}


@pytest.mark.parametrize(("statuses", "expected"), [
    (["pass", "passed"], "passed"), (["pass", "fail"], "failed"),
    (["pass", "error"], "error"), (["pass", "skip"], "not_executed"),
    (["not_executed"], "not_executed"), (["not_applicable"], "not_applicable"),
    (["pass", "unexpected"], "unknown"),
])
async def test_aggregate_never_converts_unknown_or_nonexecution_to_pass(statuses, expected):
    source = next(s for s in cat.SOURCES if s.key == "report_builtin")
    async with make_db(extra_models=(CrossCheckResult,)) as factory, factory() as db:
        pid = await add_project(db, "【测试】目录状态")
        db.add_all([result(pid, 2025, f"report-cross-check-{i}", status, i) for i, status in enumerate(statuses)])
        await db.flush()
        history = await cat._last_run(db, source, pid, 2025)
        assert history["status"] == expected
        assert sum(history["counts"].values()) == len(statuses)


async def add_workpaper(db, pid, code):
    index = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=f"【测试】{code}")
    db.add(index)
    await db.flush()
    wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=index.id,
                      file_path=f"isolated/{code}.xlsx", source_type=WpSourceType.template)
    db.add(wp)
    await db.flush()
    return wp.id


async def test_qc_is_latest_per_workpaper_across_runs_and_not_annual_evidence():
    models = (WpIndex, WorkingPaper, WpQcResult)
    async with make_db(extra_models=models) as factory, factory() as db:
        pid = await add_project(db, "【测试】质控目录")
        other = await add_project(db, "【测试】其他项目质控")
        first = await add_workpaper(db, pid, "E1")
        second = await add_workpaper(db, pid, "F1")
        foreign = await add_workpaper(db, other, "E1")
        for wp_id, passed, blocking, hours in [(first, False, 9, 0), (first, True, 0, 2),
                                               (second, False, 2, 1), (foreign, False, 20, 3)]:
            db.add(WpQcResult(working_paper_id=wp_id, passed=passed, blocking_count=blocking,
                              findings=[], check_timestamp=STAMP + timedelta(hours=hours)))
        await db.flush()
        selected = (await cat.build_check_catalog(db, source="qc_rules", project_id=pid, year=2030))["sources"][0]
        assert selected["last_run"] == {"at": (STAMP + timedelta(hours=2)).isoformat(), "status": "failed",
                                        "counts": {"working_papers": 2, "passed": 1, "failed": 1, "blocking": 2}}
        assert "不按年度过滤" in selected["last_run_note"] and "并非单次运行快照" in selected["last_run_note"]
        assert "不能作为所选年度的执行证据" in selected["last_run_note"]


async def test_signoff_gate_history_is_not_json_execution_or_annual_evidence():
    async with make_db(extra_models=(GateDecision,)) as factory, factory() as db:
        pid = await add_project(db, "【测试】门禁目录")
        other = await add_project(db, "【测试】其他项目门禁")
        for project, gate, decision, hits, hours in [(pid, "sign_off", "allow", [], 0),
                (pid, "sign_off", "warn", [{"rule_code": "QC-1"}], 1),
                (pid, "export_package", "block", [{}, {}], 2), (other, "sign_off", "block", [{}, {}], 3)]:
            db.add(GateDecision(project_id=project, gate_type=gate, decision=decision, hit_rules=hits,
                                actor_id=uuid.uuid4(), trace_id=f"isolated-{hours}",
                                created_at=STAMP + timedelta(hours=hours)))
        await db.flush()
        selected = (await cat.build_check_catalog(db, source="cycle_validation", project_id=pid, year=2030))["sources"][0]
        assert selected["last_run"] == {"at": (STAMP + timedelta(hours=1)).isoformat(), "status": "warn",
                                        "counts": {"hit_rules": 1}}
        assert selected["execution"] == "not_executable"
        assert "不按年度过滤" in selected["last_run_note"] and "不代表循环 JSON 规则执行" in selected["last_run_note"]


async def test_no_project_no_storage_and_unavailable_database_are_distinct():
    pid = uuid.uuid4()
    no_project = (await cat.build_check_catalog(None, source="report_builtin", year=2025))["sources"][0]
    assert no_project["last_run"] is None and no_project["last_run_note"] == "未指定项目，未查询执行结果"
    no_storage = (await cat.build_check_catalog(None, source="report_audit", project_id=pid, year=2025))["sources"][0]
    assert no_storage["last_run"] is None and no_storage["last_run_note"] == "本类结果不落库"
    unavailable = (await cat.build_check_catalog(None, source="report_builtin", project_id=pid, year=2025))["sources"][0]
    assert unavailable["last_run"] == {"at": None, "status": "unavailable", "counts": {}}
    assert "数据库会话不可用" in unavailable["last_run_note"] and "2025" in unavailable["last_run_note"]


async def test_missing_result_table_is_unavailable_and_does_not_abort_other_directory_queries():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "【测试】缺历史表")
        selected = (await cat.build_check_catalog(db, source="report_builtin", project_id=pid, year=2025))["sources"][0]
        assert selected["last_run"] == {"at": None, "status": "unavailable", "counts": {}}
        assert "读取失败" in selected["last_run_note"]
        # 保存点外的真实 ORM 目录读取仍可继续，不能把 SQL 失败伪装成 never_run / passed。
        available = await cat.build_check_catalog(db, source="report_audit", project_id=pid, year=2025)
        assert available["sources"][0]["error"] is None
        assert available["sources"][0]["last_run"] is None
