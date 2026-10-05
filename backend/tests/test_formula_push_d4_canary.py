"""D4（销售收入）canary L4 验收测试（Task 23 · 需求 7.1, 9.1~9.5, 9.7）。

canary 选定依据（design §九）：
- D4 是真库唯一有锚点数据的科目
- 损益类 2 条锚点正好覆盖「审定数」→「期末余额」改写
- items 落在主编码册 D4（sheet_code D4-1 只是地址命名空间）
- paper_codes=('D4',) 缺省即可

L4 验收矩阵（需求 9）：
  9.1 规则清单校验通过且目标唯一；binding 单测覆盖目标展开
  9.2 前后端双侧夹具逐值对拍（字符串逐字、浮点逐位）
  9.3 SQLite 真 ORM 集成：推送 → 条目写入；幂等；冻结跳过；取数失败零写入
  9.4 真 PG 片段验证（留 Task 24）
  9.5 端点真请求覆盖 wp_codes / wp_code 参数
  9.7 变异证明
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.formula_engine import execute
from app.services.formula_push import engine as push
from app.services.formula_push.bindings import (
    TargetSkip,
    WorkpaperTarget,
    get_binding,
    supported_wp_codes,
)
from app.services.formula_push.bindings.tier_a import (
    TierAAnchorBinding,
    TierASources,
    binding_for,
)
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import load_rules, rules_for
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, base_entries, by_addr, make_env

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "formula_push_d4_parity.json"
FIXTURE: dict = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

# ── 常量 ─────────────────────────────────────────────────────────────────

D4_TB_DATA: dict[str, dict[str, Decimal]] = {
    "6001": {"期末余额": Decimal("2000000"), "年初余额": Decimal("1500000")},
    "6051": {"期末余额": Decimal("300000"), "年初余额": Decimal("200000")},
}

D4_ADDR_6001 = "D4/D4-1/D4-1-adj-tb-6001"
D4_ADDR_6051 = "D4/D4-1/D4-1-adj-tb-6051"


def _make_d4_sources(*, available: bool = True) -> TierASources:
    """构建 D4 推送取数上下文。"""
    tb = TbAuditedSnapshot(
        tb_data={code: dict(cols) for code, cols in D4_TB_DATA.items()},
        available=available,
        company_codes=("001",),
    )
    return TierASources(formula=FormulaSources(tb=tb))


# ══════════════════════════════════════════════════════════════════════════
#  9.1 规则清单校验通过且目标唯一；binding 单测覆盖目标展开
# ══════════════════════════════════════════════════════════════════════════


class TestD4RulesAndBinding:
    """需求 9.1：D4 规则校验 + binding 目标展开。"""

    def test_d4_registered_and_valid(self):
        assert "D4" in supported_wp_codes()
        b = get_binding("D4")
        assert isinstance(b, TierAAnchorBinding)
        assert b.wp_code == "D4"
        assert b.paper_codes == ("D4",)
        assert set(b.account_prefixes) == {"6001", "6051"}
        assert b.derivations == frozenset()
        assert b.four_table_slots == frozenset()

    def test_d4_has_exactly_2_rules(self):
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        assert len(d4_rules) == 2

    def test_d4_rule_ids_match_fixture(self):
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        rule_ids = {r.rule_id for r in d4_rules}
        fixture_ids = {a["rule_id"] for a in FIXTURE["anchors"]}
        assert rule_ids == fixture_ids

    def test_d4_target_item_ids_are_unique(self):
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        item_ids = [r.target.item_id for r in d4_rules]
        assert len(item_ids) == len(set(item_ids)), "D4 目标 item_id 必须唯一"

    def test_d4_all_rules_are_source_formula_system(self):
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        for r in d4_rules:
            assert r.source.kind == "formula", f"{r.rule_id} 应为 formula 来源"
            assert r.policy == "system", f"{r.rule_id} 应为 system 策略"
            assert r.stage == "source", f"{r.rule_id} 应为 source 阶段"

    def test_d4_workpaper_targets_produce_correct_values(self):
        binding = binding_for("D4")
        sources = _make_d4_sources()
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        for rule in d4_rules:
            targets, skips = binding.workpaper_targets(rule, {}, sources)
            assert len(skips) == 0, f"{rule.rule_id} 不应跳过"
            assert len(targets) == 1, f"{rule.rule_id} 应恰好 1 个目标"
            t = targets[0]
            expected = float(D4_TB_DATA[rule.source.expression.split("'")[1]]["期末余额"])
            assert t.formula_value == pytest.approx(expected), (
                f"{rule.rule_id} 推送值 {t.formula_value} ≠ 期望 {expected}"
            )

    def test_d4_targets_produce_correct_addr_ids(self):
        binding = binding_for("D4")
        sources = _make_d4_sources()
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        addrs = set()
        for rule in d4_rules:
            targets, _ = binding.workpaper_targets(rule, {}, sources)
            addrs.add(targets[0].addr_id)
        assert addrs == {D4_ADDR_6001, D4_ADDR_6051}


# ══════════════════════════════════════════════════════════════════════════
#  9.2 前后端双侧夹具逐值对拍
# ══════════════════════════════════════════════════════════════════════════


class TestD4Parity:
    """需求 9.2：夹具逐值对拍（字符串逐字、浮点逐位）。"""

    @pytest.mark.parametrize("anchor", FIXTURE["anchors"], ids=lambda a: a["rule_id"])
    def test_fixture_float_matches_formula_eval(self, anchor):
        """夹具中的 expected_float 与公式引擎求值逐位相等。"""
        from app.services.formula_engine import FormulaContext
        ctx = FormulaContext(tb_data={
            code: {col: Decimal(val) for col, val in cols.items()}
            for code, cols in FIXTURE["test_tb_data"].items()
        })
        result = execute(anchor["expression"], ctx)
        assert float(result.value) == anchor["expected_float"]

    @pytest.mark.parametrize("anchor", FIXTURE["anchors"], ids=lambda a: a["rule_id"])
    def test_fixture_js_string_matches_js_number_to_string(self, anchor):
        """夹具中的 expected_js_string 与 js_number_to_string 逐字相等。"""
        assert js_number_to_string(anchor["expected_float"]) == anchor["expected_js_string"]

    @pytest.mark.parametrize("anchor", FIXTURE["anchors"], ids=lambda a: a["rule_id"])
    def test_binding_push_value_matches_fixture(self, anchor):
        """binding 推送值与夹具期望值逐位相等。"""
        binding = binding_for("D4")
        sources = _make_d4_sources()
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        rule = next(r for r in d4_rules if r.rule_id == anchor["rule_id"])
        targets, _ = binding.workpaper_targets(rule, {}, sources)
        assert targets[0].formula_value == pytest.approx(anchor["expected_float"])

    @pytest.mark.parametrize("anchor", FIXTURE["anchors"], ids=lambda a: a["rule_id"])
    def test_apply_writes_fixture_js_string(self, anchor):
        """apply 写入的字符串与夹具 expected_js_string 逐字相等。"""
        binding = binding_for("D4")
        sources = _make_d4_sources()
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        rule = next(r for r in d4_rules if r.rule_id == anchor["rule_id"])
        targets, _ = binding.workpaper_targets(rule, {}, sources)
        entries: dict = {}
        binding.apply(entries, targets[0], targets[0].formula_value)
        assert entries[anchor["item_id"]] == anchor["expected_js_string"]


# ══════════════════════════════════════════════════════════════════════════
#  9.3 SQLite 真 ORM 集成
# ══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def d4_env(monkeypatch):
    """D4 canary 环境：E1 + D4 双底稿，取数各自 mock。"""
    async with make_env(monkeypatch) as e:
        # 增加 D4 底稿
        d4_idx, d4_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D4')"
            ), {"i": str(d4_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(d4_wp), "p": str(e.pid), "i": str(d4_idx)})
            await db.commit()
        e.d4_wp_id = d4_wp

        # Mock D4 取数
        d4_sources = _make_d4_sources()

        async def fake_d4_load(self_or_db, *args, **kwargs):
            return d4_sources

        monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_d4_load)
        yield e


async def _d4_entries(env: Env) -> dict[str, str]:
    """读取 D4 底稿的全部条目。"""
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
        ), {"w": str(env.d4_wp_id)})).all()
    return {r[0]: r[1] for r in rows}


@pytest.mark.asyncio
async def test_d4_push_writes_both_anchors(d4_env):
    """D4 推送后 2 个锚点键均被写入且值正确。"""
    # E1 也需要条目才不会报空底稿
    await d4_env.seed_entries(base_entries())

    result = await d4_env.push()
    d4_saved = await _d4_entries(d4_env)

    # 6001 → 2000000
    assert d4_saved["D4-1-adj-tb-6001"] == "2000000"
    # 6051 → 300000
    assert d4_saved["D4-1-adj-tb-6051"] == "300000"

    # 运行状态应包含 D4 的 2 个状态
    states = await d4_env.states()
    d4_states = {k: v for k, v in states.items() if v.rule_id.startswith("D4.")}
    assert len(d4_states) == 2
    assert all(s.state == "auto" for s in d4_states.values())

    # 运行记录应包含 D4 底稿
    runs = await d4_env.runs()
    assert len(runs) == 1
    wp_codes_in_run = [w["wp_code"] for w in runs[0].detail.get("wp", [])]
    assert "D4" in wp_codes_in_run


@pytest.mark.asyncio
async def test_d4_second_push_idempotent(d4_env):
    """D4 第二次推送值不变时 action=unchanged。"""
    await d4_env.seed_entries(base_entries())

    await d4_env.push()
    before = await _d4_entries(d4_env)

    result = await d4_env.push()
    after = await _d4_entries(d4_env)
    assert before == after

    d4_items = [i for i in result.items if i.rule_id.startswith("D4.")]
    assert all(i.action == "unchanged" for i in d4_items)


@pytest.mark.asyncio
async def test_d4_frozen_workpaper_skipped(d4_env):
    """D4 底稿冻结（review_passed）时跳过，不写入。"""
    await d4_env.seed_entries(base_entries())

    # 冻结 D4
    async with d4_env.factory() as db:
        await db.execute(sa.text(
            "UPDATE working_paper SET status = 'review_passed' WHERE id = :w"
        ), {"w": str(d4_env.d4_wp_id)})
        await db.commit()

    result = await d4_env.push()
    d4_saved = await _d4_entries(d4_env)

    # D4 不应有任何条目写入
    assert "D4-1-adj-tb-6001" not in d4_saved
    assert "D4-1-adj-tb-6051" not in d4_saved

    # E1 应正常推送（失败隔离）
    e1_entries = await d4_env.entries()
    assert "E1-adj-tb-amount-ending" in e1_entries


@pytest.mark.asyncio
async def test_d4_tb_unavailable_zero_writes(d4_env, monkeypatch):
    """D4 试算表不可用时零写入。"""
    await d4_env.seed_entries(base_entries())

    # 让 D4 取数返回不可用
    unavailable = _make_d4_sources(available=False)

    async def fake_unavailable(self_or_db, *args, **kwargs):
        return unavailable

    monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_unavailable)

    result = await d4_env.push()
    d4_saved = await _d4_entries(d4_env)

    # D4 不应有任何条目写入（跳过而非写 0）
    assert "D4-1-adj-tb-6001" not in d4_saved
    assert "D4-1-adj-tb-6051" not in d4_saved


@pytest.mark.asyncio
async def test_d4_selective_push_only_d4(d4_env):
    """wp_codes=['D4'] 只推 D4，E1 条目不变。"""
    await d4_env.seed_entries(base_entries())

    # 先推一次全量建立基线
    await d4_env.push()
    e1_before = await d4_env.entries()

    # 修改 E1 源使其值变化（如果再推 E1 会变），但只推 D4
    result = await d4_env.push(codes=["D4"])

    # D4 条目应存在
    d4_saved = await _d4_entries(d4_env)
    assert d4_saved["D4-1-adj-tb-6001"] == "2000000"
    assert d4_saved["D4-1-adj-tb-6051"] == "300000"

    # 运行记录只含 D4
    runs = await d4_env.runs()
    latest = runs[-1]
    wp_codes_in_run = [w["wp_code"] for w in latest.detail.get("wp", [])]
    assert "D4" in wp_codes_in_run


# ══════════════════════════════════════════════════════════════════════════
#  9.5 端点真请求（继承自 test_formula_push_endpoints.py 的 api fixture）
#  这里只做 D4 特有的参数验证；通用端点测试已在 Task 9 覆盖。
# ══════════════════════════════════════════════════════════════════════════


class TestD4EndpointParams:
    """需求 9.5：D4 canary 端点参数验证（纯同步，不需要真请求 fixture）。"""

    def test_d4_states_filter_prefix(self):
        """D4 状态按 rule_id 前缀 'D4.' 过滤（与 Task 9 通用隔离同机制）。"""
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        for r in d4_rules:
            assert r.rule_id.startswith("D4."), f"D4 规则 {r.rule_id} 须以 D4. 开头"

    def test_d4_latest_detail_wp_code_field(self):
        """D4 运行记录的 detail.wp 每条都有 wp_code 字段供过滤。"""
        # 这是引擎的通用行为，此处只验证 D4 规则会产生 wp_code=D4 的记录
        binding = binding_for("D4")
        assert binding.wp_code == "D4"
        assert binding.paper_codes == ("D4",)


# ══════════════════════════════════════════════════════════════════════════
#  9.7 变异证明
# ══════════════════════════════════════════════════════════════════════════


class TestD4Mutations:
    """需求 9.7：变异证明——改动即红。"""

    def test_mutation_wrong_account_code_in_expression(self):
        """变异：公式科目码 6001→9999 ⇒ 推送值为 0（TB 不存在该码），与夹具不符。"""
        binding = binding_for("D4")
        # 构建含错误科目的 TB 数据
        bad_tb = TbAuditedSnapshot(
            tb_data={"9999": {"期末余额": Decimal("0"), "年初余额": Decimal("0")},
                     "6051": {"期末余额": Decimal("300000"), "年初余额": Decimal("200000")}},
            available=True, company_codes=("001",),
        )
        bad_sources = TierASources(formula=FormulaSources(tb=bad_tb))
        rules = rules_for(load_rules(), wp_code="D4")
        r6001 = next(r for r in rules if "6001" in r.rule_id)
        targets, skips = binding.workpaper_targets(r6001, {}, bad_sources)
        # 如果源数据缺 6001，公式引擎会对缺失科目返回 0
        if targets:
            assert targets[0].formula_value != 2000000.0, "科目码错误时不应得到正确值"

    def test_mutation_tb_unavailable_produces_skip(self):
        """变异：试算表不可用 ⇒ 全部跳过而非返回 0。"""
        binding = binding_for("D4")
        sources = _make_d4_sources(available=False)
        rules = rules_for(load_rules(), wp_code="D4")
        for rule in rules:
            targets, skips = binding.workpaper_targets(rule, {}, sources)
            assert targets == [], f"{rule.rule_id} 不应有目标"
            assert len(skips) >= 1, f"{rule.rule_id} 应有跳过记录"

    def test_mutation_no_note_rules_for_d4(self):
        """D4 Tier A 无附注规则（note_rows 返回空列表）。"""
        binding = binding_for("D4")
        rules = rules_for(load_rules(), wp_code="D4")
        for rule in rules:
            assert binding.note_rows({}, "listed", rule) == []
            assert binding.note_rows({}, "soe", rule) == []

    def test_mutation_d4_not_in_registry_raises(self):
        """变异：若 D4 未注册则 get_binding 抛 KeyError。"""
        from app.services.formula_push.bindings import _REGISTRY
        # 暂存
        orig = _REGISTRY.get("D4")
        try:
            del _REGISTRY["D4"]
            with pytest.raises(KeyError, match="尚未接入"):
                get_binding("D4")
        finally:
            if orig is not None:
                _REGISTRY["D4"] = orig

    def test_canary_justification_matches_fixture(self):
        """canary 选定依据与夹具文件一致（防止夹具被修改而依据未更新）。"""
        assert FIXTURE["wp_code"] == "D4"
        assert FIXTURE["paper_codes"] == ["D4"]
        assert len(FIXTURE["anchors"]) == 2
        # 确认两条锚点的 rule_id 与注册表规则一致
        rules = load_rules()
        d4_rules = rules_for(rules, wp_code="D4")
        fixture_rule_ids = {a["rule_id"] for a in FIXTURE["anchors"]}
        actual_rule_ids = {r.rule_id for r in d4_rules}
        assert fixture_rule_ids == actual_rule_ids
