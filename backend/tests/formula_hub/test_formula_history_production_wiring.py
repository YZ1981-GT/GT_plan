"""公式历史与一致性门禁的「生产调用方 / 注册」一层（阶段 D 缺陷 D-1 / D-2 / D-4 的回归守卫）。

``test_formula_audit_log_year.py`` 直接给 ``audit_project`` 传 ``year``，``test_consistency_gate_enforcement.py``
直接调规则 —— 都看不到：生产调用方从不传 year（D-1）、历史条目没有当前版本可带（D-2）、
``gate_rules_chain`` 从未被启动注册（D-4）。本文件走生产函数本身：SQLite 真 ORM，项目审计年度 2025。
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.routers.formula_audit_log import get_audit_log
from app.services.formula_settings import project_ops
from app.services.formula_settings.errors import VersionConflict
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.rollback import rollback_from_log

from tests.formula_settings._env import STD, add_global_row, add_project, make_db

OLD, MINE, NEW = "TB('1001','期末余额')", "ROW('BS-009')", "TB('1001','期末余额')*2"
SLOT = "balance_sheet:BS-001"


async def _history(db, pid, year=2025):
    return await get_audit_log(str(pid), year, module="", row_code="", legacy_without_year=False,
                               limit=100, db=db, current_user=None)


async def test_production_writers_record_project_year_so_history_is_not_empty():
    """D-1：本项目适配 / 同步全局 / 恢复为全局都不传 year，历史页按 2025 查仍能查到，且条目都带 2025。"""
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        await add_global_row(db, "BS-002", "TB('1002','期末余额')", row_number=2)
        pid = await add_project(db, "本项目")
        await db.commit()
        await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                         items=[{"slot_key": "balance_sheet:BS-002",
                                                 "definition": {"formula": MINE}}])
        await db.commit()
        await publish_global(db, domain="report", scope=STD, user_id=None,
                             changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
        await db.commit()
        await project_ops.restore_global(db, domain="report", project_id=pid,
                                         slot_keys=["balance_sheet:BS-002"], user_id=None)
        await db.commit()
        items = await _history(db, pid)
        ops = {i["operation"] for i in items}
        assert {"adapt", "sync_global", "restore"} <= ops, ops
        assert await _history(db, pid, year=2024) == []


async def test_history_entry_carries_current_version_and_rollback_uses_it():
    """D-2：可回滚条目带当前修订号；界面拿它作 expected_version 回滚成功，旧版本号 409。"""
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "本项目")
        await db.commit()
        out = await project_ops.save_overrides(db, domain="report", project_id=pid, user_id=None,
                                               items=[{"slot_key": SLOT, "definition": {"formula": MINE}}])
        await db.commit()
        version = out["saved"][0]["version"]
        [entry] = [i for i in await _history(db, pid) if i["operation"] == "adapt"]
        assert entry["rollbackable"] is True
        assert entry["current_version"] == version
        with pytest.raises(VersionConflict):
            await rollback_from_log(db, project_id=pid, source_log_id=entry["id"],
                                    expected_version=version + 1, user_id=None)
        await db.rollback()
        result = await rollback_from_log(db, project_id=pid, source_log_id=entry["id"],
                                         expected_version=entry["current_version"], user_id=None)
        await db.commit()
        assert result["restored_formula"] == OLD
        rolled = [i for i in await _history(db, pid) if i["operation"] == "rollback"]
        assert rolled and rolled[0]["current_version"] == version + 1


async def test_entry_without_local_adaptation_reports_version_zero():
    """同步全局写入的条目在本项目无适配 ⇒ 当前版本 0（与 save_overrides 新建口径一致）。"""
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", OLD)
        pid = await add_project(db, "本项目")
        await db.commit()
        await publish_global(db, domain="report", scope=STD, user_id=None,
                             changes=[{"slot_key": SLOT, "definition": {"formula": NEW}, "expected_version": 1}])
        await db.commit()
        [entry] = [i for i in await _history(db, pid) if i["operation"] == "sync_global"]
        assert (entry["rollbackable"], entry["current_version"]) == (True, 0)


async def _rule_hit(monkeypatch, mode: str, *, raise_exc: bool = False):
    """经真实 ConsistencyPassedRule.check：年度与一致性结果打桩（一项阻断级未执行），模式按参数。"""
    from app.services import gate_rules_chain
    from app.services.consistency_gate import ConsistencyResult, _models

    async def fake_year(_db, _pid):
        return 2025

    async def fake_run(self, project_id, year):
        if raise_exc:
            raise RuntimeError("boom")
        return ConsistencyResult(overall="fail", checks=[
            _models._not_executed("试算平衡", branch_id="t.1", reason="负债与权益合计均为 0", severity="blocking"),
            _models._ok("报表平衡", severity="blocking"),
        ])

    monkeypatch.setattr("app.services.project_audit_year.fetch_project_audit_year", fake_year)
    monkeypatch.setattr("app.services.consistency_gate.ConsistencyGate.run_all_checks", fake_run)
    monkeypatch.setattr("app.services.consistency_gate._decision._load_mode", lambda: mode)
    from app.core.config import settings
    monkeypatch.setattr(settings, "CONSISTENCY_GATE_ENFORCEMENT", mode)
    return await gate_rules_chain.ConsistencyPassedRule().check(None, {"project_id": "p1"})


async def test_consistency_rule_observe_gives_hint_not_block(monkeypatch):
    """需求 16.4：observe 下 warning 级提示「…（当前为只提示模式）」，带检查项五态与原因。"""
    from app.models.phase14_enums import GateSeverity
    hit = await _rule_hit(monkeypatch, "observe")
    assert hit is not None and hit.severity == GateSeverity.warning
    assert "当前为只提示模式" in hit.message
    assert hit.location["items"] == [{"check_name": "试算平衡", "status": "not_executed",
                                      "reason": "负债与权益合计均为 0"}]


async def test_consistency_rule_enforce_blocks(monkeypatch):
    from app.models.phase14_enums import GateSeverity
    hit = await _rule_hit(monkeypatch, "enforce")
    assert hit is not None and hit.severity == GateSeverity.blocking
    assert "请补齐数据后重新检查" in hit.message


async def test_consistency_rule_exception_is_not_silent_pass(monkeypatch):
    """检查异常不得静默返回 None（变异 #38 的形态）：observe 给提示、写明未能运行。"""
    from app.models.phase14_enums import GateSeverity
    hit = await _rule_hit(monkeypatch, "observe", raise_exc=True)
    assert hit is not None and hit.severity == GateSeverity.warning
    assert "一致性检查未能运行" in hit.message


def test_startup_registers_consistency_gate_rule():
    """D-4：启动任务调用 register_consistency_gate_rule（AST，生产注册点）。"""
    from app.core import startup_registry
    tree = ast.parse(inspect.getsource(startup_registry._task_register_phase_handlers))
    names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "register_consistency_gate_rule" in names


def test_consistency_rule_registered_once_and_blocking_chain_rules_not_registered(monkeypatch):
    """注册后 sign_off / export_package 各恰一条 CHAIN-CONSISTENCY；重复注册不叠加；
    blocking 级的报表 / 附注已生成规则不随之注册（注册即新增阻断，不属本 spec）。"""
    from app.models.phase14_enums import GateType
    from app.services import gate_rules_chain
    from app.services.gate_engine import RuleRegistry

    registry = RuleRegistry()
    monkeypatch.setattr(gate_rules_chain, "rule_registry", registry)
    gate_rules_chain.register_consistency_gate_rule()
    gate_rules_chain.register_consistency_gate_rule()
    for gate in (GateType.sign_off, GateType.export_package):
        codes = [r.rule_code for r in registry.get_rules(gate)]
        assert codes == ["CHAIN-CONSISTENCY"], (gate, codes)
