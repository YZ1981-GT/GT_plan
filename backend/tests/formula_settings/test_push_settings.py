"""公式推送规则纳入公式治理内核（spec formula-governance-coverage-closure R2，design §4）。

校验（四类拒绝 + 推送取数上下文）、有效规则叠加（改写 / 停用 / 失效跳过）、引擎读有效规则、
传播（无年度 / 合并 / 归档跳过，触发来源 FORMULA_CONFIG_CHANGED）。规则列表接口见 test_formula_push_endpoints。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.core import Project, ProjectStatus
from app.models.formula_setting_models import FormulaSetting
from app.services.formula_push import engine as push
from app.services.formula_push.rules import rules_for
from app.services.formula_settings import propagation
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.push_settings import (
    effective_push_rules,
    push_context_errors,
    validate_push_definition,
)
from app.services.formula_settings.stores import get_store
from tests._formula_push_env import CASH_OPENING, YEAR, base_entries, by_addr, make_env

TB_RULE = "E1.tb_amount.ending"  # 系统值 · 公式来源（三科目审定数合计）
HALL_RULE = "E1.hall_adj.cash.ending"  # 系统值 · 公式来源（只声明大厅调整口径）
CASH_RULE = "E1.cash_rows.four_table"  # 可编辑值 · 四表明细
DERIVED_RULE = "E1.cash_detail.ending"  # 派生值 · 派生计算
TB_ITEM = "E1-adj-tb-amount-ending"


def _refused(slot: str, definition: dict) -> str:
    with pytest.raises(FormulaSettingError) as exc:
        validate_push_definition(slot, definition, slot)
    return exc.value.message


# ── 校验：与规则清单加载同一套，外加推送取数上下文 ─────────────────────────────


def test_unknown_rule_and_structure_keys_are_refused():
    assert "推送规则不存在" in _refused("E1.no_such_rule", {"expression": "TB('1001','期末余额')"})
    msg = _refused(TB_RULE, {"expression": "TB('1001','期末余额')", "policy": "editable", "target": {}})
    assert "只能改写来源公式或启用 / 停用" in msg and "policy" in msg and "target" in msg


def test_system_and_derived_rules_cannot_be_disabled_editable_can():
    for slot in (TB_RULE, DERIVED_RULE):
        msg = _refused(slot, {"disabled": True})
        assert "不能停用" in msg and "独占键" in msg, msg
    validate_push_definition(CASH_RULE, {"disabled": True})
    validate_push_definition(CASH_RULE, {"disabled": False})


def test_non_formula_rules_cannot_be_rewritten():
    msg = _refused(CASH_RULE, {"expression": "TB('1001','期末余额')"})
    assert "四表明细" in msg and "只能停用或启用" in msg
    msg = _refused(DERIVED_RULE, {"expression": "1"})
    assert "派生计算" in msg and "只读" in msg and "不能停用" in msg
    validate_push_definition(CASH_RULE, {"expression": "", "description": "改个说明"})  # 空公式 = 未改写


def test_formula_rules_need_an_expression_the_rule_list_would_accept():
    assert "来源公式不能为空" in _refused(TB_RULE, {"expression": " = "})
    assert "审定数" in _refused(TB_RULE, {"expression": "TB('1001','审定数')"})  # 语义不唯一的列名
    assert "必须显式写列名" in _refused(TB_RULE, {"expression": "TB('1001')"})
    assert "context" in _refused(HALL_RULE, {"expression": "TB('1001','期末余额')"})  # 规则口径只有大厅调整
    validate_push_definition(TB_RULE, {"expression": "=TB('1001','期末余额') + TB('1002','期末余额')"})
    validate_push_definition(HALL_RULE, {"expression": "ROUND(ADJ('1001','aje_net'), 2)"})


def test_push_context_supplies_only_tb_and_adj_of_the_binding_accounts():
    assert push_context_errors("E1", "TB('1001','期末余额')+MAX(ADJ('1002','aje_net'),0)") == []
    [msg] = push_context_errors("E1", "TB('1001','期末余额')+PREV('1001','期末余额')")
    assert "PREV" in msg and "恒为 0" in msg
    [msg] = push_context_errors("E1", "SUM_TB('1001~1012','期末余额')")
    assert "SUM_TB" in msg
    [msg] = push_context_errors("E1", "TB('1122','期末余额')")
    assert "1122" in msg and "1001、1002、1012" in msg
    [msg] = push_context_errors("E1", "TB(1001,'期末余额')")
    assert "带引号" in msg
    assert push_context_errors("E1", "TB('1001','PREV(x)')") == [], "字符串里的「函数名(」不是调用"
    assert "1122" in _refused(TB_RULE, {"expression": "TB('1122','期末余额')"}), "保存时同样拒收"


#: 规则清单里推送取数给不出数的系统公式（试算表取不到该科目 ⇒ 恒推 0）。
#: 2026-10-23 清零（spec formula-fetch-and-wp-generation-defect-closure R1）：原登记 H6.1_tb_amount（binding 1606B）/
#: I1.1_tb_impair（1703B）/ H9.1_tb_amount（2205 vs 2802）/ I2.1_tb_amount（1717）/ I5.1_tb_amount（1911）五条，binding 与
#: 公式改为同取口径单一来源，I5 无标准科目、规则删除。今后新增一律修，不再登记（集合保持为空）。
KNOWN_PRESET_CONTEXT_GAPS: dict[str, str] = {}


def test_preset_formula_context_gaps_are_frozen():
    gaps = {r.rule_id: push_context_errors(r.wp_code, r.source.expression or "")
            for r in push.load_push_rules() if r.source.kind == "formula"}
    gaps = {k: v for k, v in gaps.items() if v}
    assert set(gaps) == set(KNOWN_PRESET_CONTEXT_GAPS), (
        f"新增 {sorted(set(gaps) - set(KNOWN_PRESET_CONTEXT_GAPS))} / 已修好请删 "
        f"{sorted(set(KNOWN_PRESET_CONTEXT_GAPS) - set(gaps))}")
    for rid, code in KNOWN_PRESET_CONTEXT_GAPS.items():
        assert any(code in e for e in gaps[rid]), (rid, gaps[rid])


# ── 有效规则：清单 ⊕ 内核各层 ─────────────────────────────────────────────────


async def _write(env, slot: str, definition: dict) -> None:
    async with env.factory() as db:
        await get_store("push").write_project(
            db, env.pid, slot, definition=definition, base_definition=None, base_version=None, pinned=False,
            base_origin=None, base_template_id=None, user_id=None)
        await db.commit()


async def _write_unchecked(env, slot: str, definition: dict) -> None:
    """绕过写入校验落一条定义（模拟运行时才失效：binding 换了科目、清单收紧了校验）。"""
    async with env.factory() as db:
        db.add(FormulaSetting(domain="push", layer="project", scope="", project_id=env.pid, slot_key=slot,
                              definition=definition, version=1))
        await db.commit()


async def test_effective_rules_overlay_rewrite_disable_and_skip_invalid(monkeypatch):
    async with make_env(monkeypatch) as env:
        await _write(env, TB_RULE, {"expression": "=TB('1001','期末余额')"})
        await _write(env, CASH_RULE, {"disabled": True})
        await _write_unchecked(env, "E1.tb_amount.opening", {"expression": "TB('1122','年初余额')"})
        async with env.factory() as db:
            rules, issues = await effective_push_rules(db, env.pid)
        preset = {r.rule_id: r for r in push.load_push_rules()}
        by_id = {r.rule_id: r for r in rules}
        assert list(by_id) == list(preset), "有效规则与清单一一对应、顺序不变"
        assert (by_id[TB_RULE].source.expression, by_id[TB_RULE].status) == ("TB('1001','期末余额')", "active")
        assert by_id[TB_RULE].target == preset[TB_RULE].target, "只换来源公式，目标不动"
        assert by_id[CASH_RULE].status == "disabled"
        assert by_id["E1.tb_amount.opening"].status == "invalid"
        [(rid, msg)] = issues
        assert rid == "E1.tb_amount.opening" and "不回退系统预设" in msg and "1122" in msg, msg
        assert by_id[DERIVED_RULE] is preset[DERIVED_RULE], "没有覆盖的规则原样"
        picked = {r.rule_id for r in rules_for(rules, wp_code="E1")}
        assert TB_RULE in picked and CASH_RULE not in picked and "E1.tb_amount.opening" not in picked


async def test_store_refuses_invalid_definitions_on_every_write(monkeypatch):
    async with make_env(monkeypatch) as env:
        with pytest.raises(FormulaSettingError, match="不能停用"):
            await _write(env, TB_RULE, {"disabled": True})
        with pytest.raises(FormulaSettingError, match="不能停用"):  # 「无定义」= 停用（内核口径）
            await _write(env, TB_RULE, {})
        with pytest.raises(FormulaSettingError, match="1122"):
            async with env.factory() as db:
                await get_store("push").write_global(db, "*", TB_RULE, {"expression": "TB('1122','期末余额')"},
                                                     user_id=None)
        await _write(env, TB_RULE, {"expression": "TB('1001','期末余额')", "_structure": {"policy": "editable"}})
        async with env.factory() as db:
            row = (await db.execute(sa.select(FormulaSetting))).scalar_one()
            local = (await get_store("push").list_project(db, env.pid))[TB_RULE]
        assert "_structure" not in row.definition, "结构只认规则清单，不随定义落库"
        assert local.structure["policy"] == "system" and local.structure["target"]["item_id"] == TB_ITEM


# ── 引擎读有效规则 ────────────────────────────────────────────────────────────


async def test_engine_pushes_rewritten_formula_and_skips_disabled_rule(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        await _write(env, TB_RULE, {"expression": "TB('1001','期末余额')"})
        await _write(env, CASH_RULE, {"disabled": True})
        result = await env.push()
        saved = await env.entries()
        assert saved[TB_ITEM] == "476.73", "改写后只取库存现金（清单原式三科目合计是 606.73）"
        assert saved["E1-adj-tb-amount-opening"] == "386.73", "未改写的规则照清单"
        assert CASH_OPENING not in by_addr(result) and all(i.rule_id != CASH_RULE for i in result.items)


async def test_engine_skips_invalid_definition_with_warning_and_keeps_target(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries({**base_entries(), TB_ITEM: "1"})
        await _write_unchecked(env, TB_RULE, {"expression": "TB('1122','期末余额')"})
        result = await env.push()
        assert (await env.entries())[TB_ITEM] == "1", "失效定义不推送，也不回退清单原式"
        assert any(TB_RULE in w and "不回退系统预设" in w for w in result.warnings), result.warnings
        assert all(i.rule_id != TB_RULE for i in result.items)


async def test_formula_config_changed_trigger_selects_like_manual_and_is_recorded(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        result = await env.push(trigger=push.FORMULA_CONFIG_CHANGED, codes=["E1"])
        [run] = await env.runs()
        assert run.trigger_source == "FORMULA_CONFIG_CHANGED" and result.written_count > 0
        assert (await env.entries())[TB_ITEM] == "606.73"
        with pytest.raises(ValueError, match="未知触发来源"):
            await env.push(trigger="FORMULA_CHANGED")


# ── 传播：有效定义变化 → 受影响底稿重推 ────────────────────────────────────────


async def test_propagate_push_repushes_affected_workpapers(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        await _write(env, TB_RULE, {"expression": "TB('1001','期末余额')"})
        propagation.set_session_factory(env.factory)
        try:
            out = await propagation.propagate_push(env.pid, YEAR, [TB_RULE, "E1.no_such_rule"])
        finally:
            propagation.set_session_factory(None)
        [run] = await env.runs()
        assert out["wp_codes"] == ["E1"] and out["run_id"] == str(run.id)
        assert run.trigger_source == push.FORMULA_CONFIG_CHANGED
        assert (await env.entries())[TB_ITEM] == "476.73"


async def test_propagate_push_skips_without_year_rule_or_when_consolidated_or_archived(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        propagation.set_session_factory(env.factory)

        async def project(**values):
            async with env.factory() as db:
                await db.execute(sa.update(Project).where(Project.id == env.pid).values(**values))
                await db.commit()

        try:
            assert (await propagation.propagate_push(env.pid, None, [TB_RULE]))["skipped"] == "no_year"
            assert (await propagation.propagate_push(env.pid, YEAR, ["X9.nope"]))["skipped"] == "no_rule"
            await project(report_scope="consolidated")
            assert (await propagation.propagate_push(env.pid, YEAR, [TB_RULE]))["skipped"] == "consolidated"
            await project(report_scope="standalone", status=ProjectStatus.archived)
            assert (await propagation.propagate_push(env.pid, YEAR, [TB_RULE]))["skipped"] == "frozen"
            await project(status=ProjectStatus.created)
            out = await propagation.propagate_push(env.pid, YEAR - 1, [TB_RULE])  # 非审计年度：引擎只提示不推
            assert out["run_id"] is None and out["written"] == 0
        finally:
            propagation.set_session_factory(None)
        assert await env.runs() == []
        assert propagation.HANDLERS["push"] is propagation.propagate_push
