"""试算表科目明细 / 表间审核规则（Phase 4）：存储、全局 + 本项目两层、差量写入与 CAS、规则进勾稽 run。"""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import FormulaSetting
from app.models.report_models import FinancialReport
from app.services.formula_settings import cross_check_rules, tb_detail
from app.services.formula_settings.errors import VersionConflict, VersionRequired
from app.services.formula_settings.publish import publish_global

from ._env import BS, STD, add_project, make_db


def _item(code, formula, name=None):
    return {"row_code": code, "row_name": name, "formula": formula, "formula_category": None}


async def test_tb_detail_global_then_project_adaptation_and_removal():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "明细")
        await db.commit()
        await publish_global(db, domain="tb_detail", scope="*", user_id=None, changes=[
            {"slot_key": "1001", "definition": _item("1001", "TB('1001','期末余额')*1", "库存现金")},
            {"slot_key": "added:G1", "definition": _item("G1", "TB('1002','期末余额')", "全局新增行")}])
        await db.commit()
        got = await tb_detail.load(db, pid)
        assert got["overrides"]["1001"]["layer"] == "global" and got["added"][0]["row_code"] == "G1"
        assert got["overrides"]["1001"]["formula_category"] == "auto_calc"
        # 改全局覆盖 + 删全局新增行 + 自加一行
        await tb_detail.save(db, pid, overrides={"1001": _item("1001", "TB('1001','期末余额')*2")},
                             added=[_item("P1", "TB('1012','期末余额')", "本项目行")], loaded=got["loaded"],
                             user_id=None)
        await db.commit()
        again = await tb_detail.load(db, pid)
        assert again["overrides"]["1001"]["formula"] == "TB('1001','期末余额')*2"
        assert again["layers"] == {"1001": "project", "added:P1": "project"}
        assert [a["row_code"] for a in again["added"]] == ["P1"]  # 全局新增行在本项目停用
        other = await add_project(db, "其他")
        await db.commit()
        assert [a["row_code"] for a in (await tb_detail.load(db, other))["added"]] == ["G1"]  # 其他项目不受影响
        rows = (await db.execute(sa.select(FormulaSetting).where(FormulaSetting.project_id == pid))).scalars().all()
        assert {r.slot_key: bool(r.definition.get("disabled")) for r in rows} == {
            "1001": False, "added:G1": True, "added:P1": False}


async def test_tb_detail_requires_loaded_tokens_and_rejects_stale():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "并发")
        await db.commit()
        first = await tb_detail.save(db, pid, overrides={"1001": _item("1001", "A")}, added=[], loaded=None,
                                     user_id=None)
        await db.commit()
        assert first["saved"] == 1
        with pytest.raises(VersionRequired):
            await tb_detail.save(db, pid, overrides={}, added=[], loaded=None, user_id=None)
        await db.rollback()
        stale = (await tb_detail.load(db, pid))["loaded"]
        await tb_detail.save(db, pid, overrides={"1001": _item("1001", "B")}, added=[], loaded=stale, user_id=None)
        await db.commit()
        with pytest.raises(VersionConflict):  # 拿着旧令牌再存
            await tb_detail.save(db, pid, overrides={}, added=[], loaded=stale, user_id=None)
        await db.rollback()
        assert (await tb_detail.load(db, pid))["overrides"]["1001"]["formula"] == "B"


async def test_tb_detail_untouched_concurrent_additions_survive():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "并发新增")
        await db.commit()
        await tb_detail.save(db, pid, overrides={"1001": _item("1001", "A")}, added=[], loaded=None, user_id=None)
        await db.commit()
        mine = (await tb_detail.load(db, pid))["loaded"]
        # 别人在我载入之后新加了 1002
        await tb_detail.save(db, pid, overrides={"1001": _item("1001", "A"), "1002": _item("1002", "X")}, added=[],
                             loaded=mine, user_id=None)
        await db.commit()
        # 我按自己载入时的集合整表保存（不含 1002）：1002 不被删
        await tb_detail.save(db, pid, overrides={"1001": _item("1001", "A2")}, added=[], loaded=mine, user_id=None)
        await db.commit()
        got = (await tb_detail.load(db, pid))["overrides"]
        assert (got["1001"]["formula"], got["1002"]["formula"]) == ("A2", "X")


def _rule(label, left, right, op="=", rule_id=None):
    return {"rule_id": rule_id, "label": label, "left_ref": left, "operator": op, "right_ref": right,
            "description": "", "tolerance": None, "_editing": True}


async def test_cross_check_rules_layers_and_definition_fields():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "勾稽")
        await db.commit()
        await publish_global(db, domain="cross_check", scope="*", user_id=None, changes=[
            {"slot_key": "cross_report_note#0g", "definition": {"label": "全局规则", "left_ref": "ROW('BS-001')",
                                                             "operator": "=", "right_ref": "ROW('BS-002')"}}])
        await db.commit()
        got = await cross_check_rules.load(db, pid)
        assert [r["layer"] for r in got["rules"]["cross_report_note"]] == ["global"]
        rules = {"cross_report_note": [*got["rules"]["cross_report_note"], _rule("本项目规则", "1", "1")]}
        await cross_check_rules.save(db, pid, rules=rules, loaded=got["loaded"], user_id=None)
        await db.commit()
        again = (await cross_check_rules.load(db, pid))["rules"]["cross_report_note"]
        assert [(r["label"], r["layer"]) for r in again] == [("全局规则", "global"), ("本项目规则", "project")]
        row = (await db.execute(sa.select(FormulaSetting).where(FormulaSetting.layer == "project"))).scalar_one()
        assert set(row.definition) == set(cross_check_rules.RULE_FIELDS)  # 瞬态字段不进定义
        with pytest.raises(VersionRequired):  # 已有生效规则却不带令牌：不许整表覆盖
            await cross_check_rules.save(db, pid, rules={}, loaded=None, user_id=None)
        await db.rollback()
        assert len((await cross_check_rules.load(db, pid))["rules"]["cross_report_note"]) == 2


async def test_cross_check_load_normalizes_unknown_operator_like_execution():
    """V199 原样迁入旧规则的比较符；不认识的值按执行口径（=）展示，避免界面显示一个执行时并不生效的符号。"""
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "旧比较符")
        db.add(FormulaSetting(domain="cross_check", layer="project", scope="", project_id=pid,
                              slot_key="BS-001#00000", slot_label="旧规则",
                              definition={"label": "旧规则", "left_ref": "1", "operator": "~", "right_ref": "1"}))
        await db.commit()
        got = (await cross_check_rules.load(db, pid))["rules"]["BS-001"]
        assert [r["operator"] for r in got] == ["="]
        assert cross_check_rules.compare(Decimal("1"), Decimal("1.5"), "~", cross_check_rules.DEFAULT_TOLERANCE) \
            is cross_check_rules.compare(Decimal("1"), Decimal("1.5"), "=", cross_check_rules.DEFAULT_TOLERANCE)


@pytest.mark.parametrize(("left", "right", "op", "passed"), [
    ("100", "100.005", "=", True), ("100", "100.02", "=", False),
    ("99", "100", "<=", True), ("101", "100", "<=", False), ("100", "100.005", ">=", True),
])
def test_compare_semantics_match_frontend(left, right, op, passed):
    assert cross_check_rules.compare(Decimal(left), Decimal(right), op, cross_check_rules.DEFAULT_TOLERANCE) is passed


async def test_user_rules_run_with_builtin_checks_and_unresolvable_is_failure(monkeypatch):
    from app.models.audit_platform_models import TbAuxBalance, TrialBalance
    from app.models.dataset_models import LedgerDataset
    from app.services.formula_management.logic_check import execute_report_cross_checks

    async with make_db(extra_models=(TrialBalance, TbAuxBalance, LedgerDataset)) as factory, factory() as db:
        pid = await add_project(db, "执行")
        for code, amt in (("BS-001", "100"), ("BS-002", "100"), ("BS-003", "7")):
            db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code=code, row_name=code,
                                   current_period_amount=Decimal(amt)))
        await db.commit()
        await cross_check_rules.save(db, pid, loaded=None, user_id=None, rules={"cross_report_wp": [
            _rule("相等", "ROW('BS-001')", "ROW('BS-002')"),
            _rule("不等", "ROW('BS-001')", "ROW('BS-003')"),
            _rule("取不到", "AUX('1122','客户','A','期末余额')", "ROW('BS-001')"),
        ]})
        await db.commit()
        result = await execute_report_cross_checks(db, project_id=pid, year=2025, persist=False)
        user = {o.description: o.passed for o in result.outcomes if o.formula_id.startswith("user:")}
        assert user == {"相等": True, "不等": False, "取不到": False}
        builtin = [o for o in result.outcomes if o.formula_id.startswith("report-cross-check-")]
        assert len(builtin) == 7
        msgs = {i.description for i in result.issues if i.formula_id.startswith("user:")}
        # AUX 已进表间审核支持矩阵（原断言「不支持」随之过时）；核心语义不变：取不到数写明原因、判不通过，
        # 不代入 0 —— 修复前这里得到的是「左侧 0 = 右侧 100.00 不成立」（spec formula-governance-coverage-closure R7a）
        assert any("无法取数" in m and "1122" in m and "无辅助核算余额" in m for m in msgs), msgs
        assert any(m.startswith("不等：") for m in msgs)


async def test_tb_detail_conflict_surfaces_pending_marker():
    """R1.4：本项目改过某科目后全局再改 → 冲突生成待确认事项，load 的该项带 pending=True + 顶层 pending 列出。"""
    from app.services.formula_settings.project_ops import save_overrides

    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "待确认")
        await db.commit()
        await publish_global(db, domain="tb_detail", scope="*", user_id=None, changes=[
            {"slot_key": "1001", "definition": _item("1001", "G1", "库存现金")}])
        await db.commit()
        # 本项目改过 1001（无本项目行 ⇒ 不带版本，基线取当时全局），再发布新全局 ⇒ 冲突默认交项目确认
        await save_overrides(db, domain="tb_detail", project_id=pid, user_id=None, items=[
            {"slot_key": "1001", "definition": _item("1001", "L1")}])
        await db.commit()
        await publish_global(db, domain="tb_detail", scope="*", user_id=None, changes=[
            {"slot_key": "1001", "definition": _item("1001", "G2", "库存现金"), "expected_version": 1}])
        await db.commit()
        got = await tb_detail.load(db, pid)
        assert got["pending"] == ["1001"] and got["overrides"]["1001"]["pending"] is True
        assert got["overrides"]["1001"]["formula"] == "L1"  # 本项目保留自己的，等用户确认


async def test_cross_check_disabled_global_rule_excluded_from_execution(monkeypatch):
    """全局规则在本项目被停用后不参与执行；执行只认本项目生效（全局 + 本项目 − 停用）的规则。"""
    from app.services.formula_settings.cross_check_rules import run_user_rules

    async with make_db(extra_models=(_cross_row_model(),)) as factory, factory() as db:
        pid = await add_project(db, "停用全局规则")
        for code, amt in (("BS-001", "100"), ("BS-002", "100")):
            db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code=code, row_name=code,
                                   current_period_amount=Decimal(amt)))
        await db.commit()
        await publish_global(db, domain="cross_check", scope="*", user_id=None, changes=[
            {"slot_key": "cross_report_note#g1", "definition": {"label": "全局A", "left_ref": "ROW('BS-001')",
                                                             "operator": "=", "right_ref": "ROW('BS-002')"}},
            {"slot_key": "cross_report_note#g2", "definition": {"label": "全局B", "left_ref": "ROW('BS-001')",
                                                             "operator": "=", "right_ref": "ROW('BS-002')"}}])
        await db.commit()
        got = await cross_check_rules.load(db, pid)
        # 本项目保存时去掉 g2（载入过、本次不在 ⇒ 本项目停用），只留 g1
        keep = [r for r in got["rules"]["cross_report_note"] if r["label"] == "全局A"]
        await cross_check_rules.save(db, pid, rules={"cross_report_note": keep}, loaded=got["loaded"], user_id=None)
        await db.commit()
        outcomes, _ = await run_user_rules(db, project_id=pid, year=2025)
        assert {o.description for o in outcomes} == {"全局A"}


def _cross_row_model():
    from app.models.wp_optimization_models import CrossCheckResult as _Row

    return _Row


async def test_user_rules_persist_to_cross_check_results_without_rule_id_collision():
    """R10.2：用户规则与 7 条内置勾稽同一 run 落库 cross_check_results；
    不同节点同规则号（迁入旧数据）不得撞 rule_id —— 修复前都成 `user:00000`，先删后插会丢一条。"""
    import sqlalchemy as sa

    from app.models.wp_optimization_models import CrossCheckResult as Row
    from app.services.formula_management.logic_check import execute_report_cross_checks

    async with make_db(extra_models=(Row,)) as factory, factory() as db:
        pid = await add_project(db, "落库")
        for code, amt in (("BS-001", "100"), ("BS-002", "100"), ("BS-003", "7")):
            db.add(FinancialReport(project_id=pid, year=2025, report_type=BS, row_code=code, row_name=code,
                                   current_period_amount=Decimal(amt)))
        # 两个不同节点、规则号都是 00000（模拟 V199 迁入的旧数据各节点独立编号）
        for node in ("groupA", "groupB"):
            db.add(FormulaSetting(domain="cross_check", layer="project", scope="", project_id=pid,
                                  slot_key=f"{node}#00000", slot_label=f"{node}规则",
                                  definition={"label": f"{node}规则", "left_ref": "ROW('BS-001')",
                                              "operator": "=", "right_ref": "ROW('BS-002')"}))
        await db.commit()
        await execute_report_cross_checks(db, project_id=pid, year=2025, persist=True)
        await db.commit()
        rows = (await db.execute(sa.select(Row).where(Row.project_id == pid))).scalars().all()
        rule_ids = [r.rule_id for r in rows]
        assert len(rule_ids) == len(set(rule_ids)), f"rule_id 撞号：{rule_ids}"
        user_ids = [r for r in rule_ids if r.startswith("user:")]
        assert len(user_ids) == 2  # 两条用户规则各一行，没有被先删后插吃掉
        assert len([r for r in rule_ids if r.startswith("report-cross-check-")]) == 7
