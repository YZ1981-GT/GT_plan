"""R4 业务回执分类：派发成功不等于业务完成。"""
from __future__ import annotations

import pytest

from app.services.formula_settings.outbox import action_status


@pytest.mark.parametrize("domain, result, expected", [
    ("report", {"marked": 1}, "unknown"),
    ("report", {"recalculated": {"failed_rows": [{"row_code": "BS-001"}]}}, "partial"),
    ("report", {"recalculated": {"failed_count": 1, "recalculated_count": 4}}, "partial"),
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": 2}}, "succeeded"),
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": 0}}, "skipped"),
    ("wp", {"marked": 3, "wp_codes": ["D2"]}, "marked_stale"),
    ("note", {"materialized": 1, "marked": 1}, "marked_stale"),
    ("tb_detail", {"skipped": "no_consumer", "slot_keys": ["1001"]}, "no_consumer"),
    ("cross_check", {"executed": 2, "passed": 1, "failed": 1, "issues": 0}, "check_failed"),
    ("cross_check", {"executed": 2, "passed": 2, "failed": 0, "issues": 1}, "check_failed"),
    ("cross_check", {"executed": 2, "passed": 2, "failed": 0, "issues": 0}, "succeeded"),
    ("consol_note", {"operation_id": "operation", "status": "queued"}, "queued"),
    ("consol_note", {"operation_id": "operation", "status": "running"}, "running"),
    ("consol_note", {"operation_id": "operation", "status": "partial"}, "partial"),
    ("consol_note", {"status": "succeeded"}, "unknown"),
    ("push", {"written": 12, "skipped": 4}, "unknown"),
    ("push", {"status": "succeeded", "written": 12}, "unknown"),
    ("push", {"status": "failed", "run_id": "run", "written": 12}, "failed"),
    ("push", {"status": "partial", "run_id": "run", "written": 12}, "partial"),
    ("push", {"status": "succeeded", "run_id": "run", "workpapers": [{"status": "failed"}]}, "partial"),
    ("push", {"status": "succeeded", "run_id": "run", "blocked_writes": [{"reason": "manual"}]}, "partial"),
    ("push", {"status": "succeeded", "run_id": "run", "written": 0, "skipped": 17}, "succeeded"),
    ("report", {"skipped": "frozen"}, "skipped"),
    ("report", {}, "unknown"),
])
def test_action_status_requires_domain_evidence(domain, result, expected):
    assert action_status(domain, result) == expected


@pytest.mark.parametrize("domain, result", [
    ("report", {"recalculated": {"failed_count": "0", "recalculated_count": 2}}),
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": "2"}}),
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": True}}),
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": -1}}),
    ("report", {"recalculated": {"failed_rows": {}, "failed_count": 0, "recalculated_count": 2}}),
    ("wp", {"marked": "3", "wp_codes": ["D2"]}),
    ("note", {"materialized": None, "marked": 1}),
    ("cross_check", {"executed": "2", "passed": "2", "failed": 0, "issues": 0}),
    ("cross_check", {"executed": None, "passed": None, "failed": None, "issues": None}),
    ("consol_note", {"operation_id": "operation", "status": ["succeeded"]}),
    ("consol_note", {"operation_id": {"id": "operation"}, "status": "succeeded"}),
    ("push", {"status": "succeeded", "run_id": "run", "workpapers": None}),
    ("push", {"status": "succeeded", "run_id": "run", "workpapers": [None]}),
    ("push", {"status": "succeeded", "run_id": "run", "blocked_writes": {}}),
    ("push", {"status": "succeeded", "run_id": {"id": "run"}}),
    ("push", {"status": ["succeeded"], "run_id": "run"}),
    ("report", None),
    ("push", []),
])
def test_malformed_business_evidence_is_unknown(domain, result):
    assert action_status(domain, result) == "unknown"


@pytest.mark.parametrize("domain, result, expected", [
    ("report", {"recalculated": {"failed_rows": [{"row_code": "BS-001"}]}, "skipped": True}, "partial"),
    ("report", {"recalculated": {"failed_count": 1}, "skipped": "frozen"}, "partial"),
    ("cross_check", {"executed": 1, "passed": 0, "failed": 1, "issues": 0,
                     "skipped": "no_consumer"}, "check_failed"),
    ("push", {"status": "failed", "skipped": True}, "failed"),
    ("push", {"status": "partial", "skipped": "no_consumer"}, "partial"),
    ("push", {"status": "succeeded", "run_id": "synthetic-run",
              "workpapers": [{"status": "failed"}], "skipped": True}, "partial"),
    ("push", {"status": "succeeded", "run_id": "synthetic-run",
              "blocked_writes": [{"reason": "manual"}], "skipped": "frozen"}, "partial"),
])
def test_explicit_failure_evidence_has_priority_over_skipped(domain, result, expected):
    assert action_status(domain, result) == expected


@pytest.mark.parametrize("domain, result, expected", [
    ("report", {"recalculated": {"failed_count": 0, "recalculated_count": 2}, "skipped": 3}, "succeeded"),
    ("push", {"status": "succeeded", "run_id": "synthetic-run", "skipped": 9}, "succeeded"),
    ("push", {"written": 12, "skipped": 9}, "unknown"),
])
def test_numeric_skip_count_is_not_a_skipped_business_action(domain, result, expected):
    assert action_status(domain, result) == expected


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("stage", ["substitute", "evaluate"])
async def test_user_rule_technical_failure_respects_strict_mode(monkeypatch, strict, stage):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.formula_settings import cross_check_rules as rules
    from app.services import report_engine
    from ._env import add_project, make_db

    slots = {"报告#r4": SimpleNamespace(definition={"left_ref": "1", "right_ref": "1"})}
    monkeypatch.setattr(rules, "live_slots", AsyncMock(return_value=slots))
    failure = AsyncMock(side_effect=RuntimeError(f"注入用户规则技术异常:{stage}"))
    monkeypatch.setattr(rules if stage == "substitute" else report_engine,
                        "_substitute_strict" if stage == "substitute" else "evaluate_formula_result", failure)
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "用户规则技术异常")
        if strict:
            with pytest.raises(RuntimeError, match=f"注入用户规则技术异常:{stage}"):
                await rules.run_user_rules(db, project_id=pid, year=2025, report_rows=[], strict=True)
        else:
            outcomes, issues = await rules.run_user_rules(db, project_id=pid, year=2025, report_rows=[])
            assert len(outcomes) == len(issues) == 1 and outcomes[0].passed is False
            assert f"注入用户规则技术异常:{stage}" in issues[0].description
    assert failure.await_count == (1 if strict else 2)


async def test_strict_user_rule_missing_value_is_business_failure(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.formula_settings import cross_check_rules as rules
    from ._env import add_project, make_db

    slots = {"报告#missing": SimpleNamespace(definition={"left_ref": "", "right_ref": ""})}
    monkeypatch.setattr(rules, "live_slots", AsyncMock(return_value=slots))
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "用户规则正常缺数")
        outcomes, issues = await rules.run_user_rules(db, project_id=pid, year=2025, report_rows=[], strict=True)
    assert len(outcomes) == len(issues) == 1 and outcomes[0].passed is False
    assert "未填写" in issues[0].description


@pytest.mark.parametrize("failure", ["flush", "short_write"])
async def test_durable_cross_check_rejects_persistence_failure(monkeypatch, failure):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    import sqlalchemy as sa
    from app.models.wp_optimization_models import CrossCheckResult as ResultRow
    from app.services.formula_management import logic_check as logic
    from app.services.formula_settings import cross_check_rules as rules, propagation
    from ._env import add_project, make_db

    # 只缩小规则输入；执行、用户规则、持久化及耐久处理器均调用生产函数。
    monkeypatch.setattr(logic, "build_cross_check_formulas", lambda: [])
    slots = {"报告#persist": SimpleNamespace(definition={"left_ref": "", "right_ref": ""})}
    monkeypatch.setattr(rules, "live_slots", AsyncMock(return_value=slots))
    degraded = Mock()
    monkeypatch.setattr(propagation, "_degraded", degraded)
    short_write = AsyncMock(return_value=0)
    if failure == "short_write":
        monkeypatch.setattr(logic, "persist_cross_check_results", short_write)
    async with make_db(extra_models=(ResultRow,)) as factory:
        async with factory() as db:
            pid = await add_project(db, "耐久勾稽落库失败")
            await db.commit()

        @asynccontextmanager
        async def writing():
            async with factory() as db:
                original_flush = db.flush

                async def flush(*args, **kwargs):
                    if failure == "flush" and any(isinstance(row, ResultRow) for row in db.new):
                        raise RuntimeError("注入勾稽刷盘失败")
                    return await original_flush(*args, **kwargs)

                monkeypatch.setattr(db, "flush", flush)
                yield db

        monkeypatch.setattr(propagation, "_session_factory", writing)
        message = "注入勾稽刷盘失败" if failure == "flush" else "勾稽结论未完整持久化"
        with pytest.raises(propagation.PropagationIncomplete, match=message):
            await propagation.propagate_cross_check(pid, 2025, ["报告#persist"])
        async with factory() as db:
            assert (await db.execute(sa.select(sa.func.count()).select_from(ResultRow))).scalar_one() == 0
    degraded.assert_called_once()
    if failure == "short_write":
        assert short_write.await_args.kwargs["strict"] is True
        assert len(short_write.await_args.kwargs["result"].outcomes) == 1


@pytest.mark.parametrize("strict", [False, True])
async def test_report_cross_check_propagates_user_rule_technical_failure(monkeypatch, strict):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.formula_management import logic_check as logic
    from app.services.formula_settings import cross_check_rules as rules
    from ._env import add_project, make_db

    monkeypatch.setattr(logic, "build_cross_check_formulas", lambda: [])
    slots = {"报告#strict": SimpleNamespace(definition={"left_ref": "1", "right_ref": "1"})}
    monkeypatch.setattr(rules, "live_slots", AsyncMock(return_value=slots))
    failure = AsyncMock(side_effect=RuntimeError("注入勾稽用户规则异常"))
    monkeypatch.setattr(rules, "_substitute_strict", failure)
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "真实勾稽严格贯通")
        if strict:
            with pytest.raises(RuntimeError, match="注入勾稽用户规则异常"):
                await logic.execute_report_cross_checks(db, project_id=pid, year=2025, persist=False, strict=True)
        else:
            result = await logic.execute_report_cross_checks(db, project_id=pid, year=2025, persist=False)
            assert len(result.outcomes) == len(result.issues) == 1
            assert result.outcomes[0].passed is False
    assert failure.await_count == (1 if strict else 2)


@pytest.mark.parametrize("strict", [False, True])
async def test_persist_cross_check_flush_failure_is_visible_in_strict_mode(monkeypatch, strict):
    from unittest.mock import AsyncMock
    from app.models.wp_optimization_models import CrossCheckResult as ResultRow
    from app.services.formula_management import logic_check as logic
    from ._env import add_project, make_db

    async with make_db(extra_models=(ResultRow,)) as factory, factory() as db:
        pid = await add_project(db, "严格落库失败")
        await db.commit()
        result = logic.CrossCheckResult(issues=[], outcomes=[logic.CrossCheckOutcome("r4", "验证", "1", True)])
        failure = AsyncMock(side_effect=RuntimeError("注入直接刷盘失败"))
        monkeypatch.setattr(db, "flush", failure)
        if strict:
            with pytest.raises(RuntimeError, match="注入直接刷盘失败"):
                await logic.persist_cross_check_results(db, project_id=pid, year=2025, result=result, strict=True)
        else:
            assert await logic.persist_cross_check_results(db, project_id=pid, year=2025, result=result) == 0
        failure.assert_awaited_once()
        await db.rollback()
