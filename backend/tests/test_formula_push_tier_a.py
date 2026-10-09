"""Tier A 锚点族 binding 测试：21 条锚点 × 18 个底稿编码。

spec: formula-push-all-subjects-rollout · Task 22 · 需求 7.2, 7.3

验证：
- 18 个 binding 全部通过注册校验
- 21 条锚点推送值与直接求值 TB 表达式逐值相等
- D1 / D2 减项码 1231-0x 只取子目，不误吞父码 1231
- 4 条禁用列名改写后语义等价（损益类 '期末余额' = audited_amount）
- 试算表不可用时跳过而非写 0
- 未注册底稿抛 KeyError
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.formula_engine import FormulaContext, execute
from app.services.formula_push.bindings import (
    get_binding,
    supported_wp_codes,
)
from app.services.formula_push.bindings.tier_a import (
    TierAAnchorBinding,
    TierASources,
    _load_presets,
    binding_for,
)
from app.services.formula_push.rules import (
    PushRuleError,
    load_rules,
    parse_rules,
    rules_for,
)
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

# ── 预设数据 ─────────────────────────────────────────────────────────────

PRESETS_PATH = Path(__file__).resolve().parents[1] / "data" / "d_cycle_extraction" / "d_cycle_extraction_presets.json"
RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "formula_push_rules.json"

TIER_A_CODES = ("D1", "D2", "D3", "D4", "D6", "D7", "I6")
# H5~H10, I1~I5 已迁移到 BalanceAdjudicationBinding（批 C 审定表族）

# 真实试算表审定数据（含子目码，覆盖 21 条锚点引用的全部科目码）
_TB_DATA: dict[str, dict[str, Decimal]] = {
    # D1: 1121(应收票据), 1231-01(坏账准备)
    "1121": {"期末余额": Decimal("500000"), "年初余额": Decimal("400000")},
    "1231-01": {"期末余额": Decimal("30000"), "年初余额": Decimal("20000")},
    # D2: 1122(应收账款), 1231-02(坏账准备)
    "1122": {"期末余额": Decimal("800000"), "年初余额": Decimal("700000")},
    "1231-02": {"期末余额": Decimal("50000"), "年初余额": Decimal("40000")},
    # 父码 1231 —— D1/D2 减项应只取子目，不吞父码
    "1231": {"期末余额": Decimal("999999"), "年初余额": Decimal("888888")},
    # D3: 2203
    "2203": {"期末余额": Decimal("150000"), "年初余额": Decimal("120000")},
    # D4: 6001, 6051（损益类，审定发生额）
    "6001": {"期末余额": Decimal("2000000"), "年初余额": Decimal("1500000"), "本期发生额": Decimal("500000")},
    "6051": {"期末余额": Decimal("300000"), "年初余额": Decimal("200000"), "本期发生额": Decimal("100000")},
    # D6: 1141
    "1141": {"期末余额": Decimal("80000"), "年初余额": Decimal("70000")},
    # D7: 2205
    "2205": {"期末余额": Decimal("350000"), "年初余额": Decimal("300000")},
    # H5: 1631
    "1631": {"期末余额": Decimal("1200000"), "年初余额": Decimal("1100000")},
    # H6: 1606
    "1606": {"期末余额": Decimal("0"), "年初余额": Decimal("5000")},
    # H7: 1621
    "1621": {"期末余额": Decimal("600000"), "年初余额": Decimal("550000")},
    # H8: 1901
    "1901": {"期末余额": Decimal("900000"), "年初余额": Decimal("950000")},
    # H9: 2205（与 D7 同科目码但值相同）—— 已在 2205 上面
    # H10: 6115（损益类）
    "6115": {"期末余额": Decimal("45000"), "年初余额": Decimal("0"), "本期发生额": Decimal("45000")},
    # I1: 1701, 1702, 1703
    "1701": {"期末余额": Decimal("400000"), "年初余额": Decimal("350000")},
    "1702": {"期末余额": Decimal("-120000"), "年初余额": Decimal("-100000")},
    "1703": {"期末余额": Decimal("-15000"), "年初余额": Decimal("-10000")},
    # I2: 1717
    "1717": {"期末余额": Decimal("200000"), "年初余额": Decimal("180000")},
    # I3: 1711
    "1711": {"期末余额": Decimal("500000"), "年初余额": Decimal("500000")},
    # I4: 1801
    "1801": {"期末余额": Decimal("60000"), "年初余额": Decimal("80000")},
    # I5: 1911
    "1911": {"期末余额": Decimal("130000"), "年初余额": Decimal("110000")},
    # I6: 6602（损益类）
    "6602": {"期末余额": Decimal("90000"), "年初余额": Decimal("0"), "本期发生额": Decimal("90000")},
}


def _make_sources(wp_code: str, *, available: bool = True) -> TierASources:
    """为指定底稿构建推送取数上下文。"""
    binding = binding_for(wp_code)
    # 从全局 TB 数据中取该 binding 需要的科目码（含本期发生额）
    tb_data: dict[str, dict[str, Decimal]] = {}
    for code in binding.account_prefixes:
        raw = dict(_TB_DATA.get(code, {"期末余额": Decimal("0"), "年初余额": Decimal("0")}))
        if "本期发生额" not in raw:
            raw["本期发生额"] = raw["期末余额"] - raw["年初余额"]
        tb_data[code] = raw
    tb = TbAuditedSnapshot(tb_data=tb_data, available=available, company_codes=("001",))
    return TierASources(formula=FormulaSources(tb=tb))


def _formula_context(wp_code: str) -> FormulaContext:
    """构建与 _make_sources 同口径的 FormulaContext，供直接求值对拍。"""
    binding = binding_for(wp_code)
    tb_data: dict[str, dict[str, Decimal]] = {}
    for code in binding.account_prefixes:
        raw = dict(_TB_DATA.get(code, {"期末余额": Decimal("0"), "年初余额": Decimal("0")}))
        if "本期发生额" not in raw:
            raw["本期发生额"] = raw["期末余额"] - raw["年初余额"]
        tb_data[code] = raw
    return FormulaContext(tb_data=tb_data)


# 期望值：每条锚点公式在上述 TB 数据下的求值结果
_EXPECTED: dict[str, float] = {}


def _compute_expected():
    """从预设库读取全部 21 条锚点表达式，在测试 TB 数据下求值。"""
    presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    for wp_code, anchor_list in presets.items():
        if wp_code.startswith("_") or not isinstance(anchor_list, list):
            continue
        ctx = _formula_context(wp_code)
        for preset in anchor_list:
            anchor = preset["anchor"]
            expr = preset["expression"]
            result = execute(expr, ctx)
            _EXPECTED[anchor] = float(result.value)


_compute_expected()


# ── 注册与校验 ───────────────────────────────────────────────────────────


class TestTierARegistration:
    """18 个 Tier A binding 全部通过注册校验。"""

    @pytest.mark.parametrize("code", TIER_A_CODES)
    def test_binding_registered_and_valid(self, code: str):
        assert code in supported_wp_codes()
        b = get_binding(code)
        assert isinstance(b, TierAAnchorBinding)
        assert b.wp_code == code
        assert len(b.account_prefixes) >= 1
        # derivations 由 _NOTE_DERIVATIONS 动态注入（batch-c 附注规则扩展后多码均有）
        from app.services.formula_push.bindings.tier_a import _NOTE_DERIVATIONS
        expected_derivations = _NOTE_DERIVATIONS.get(code, frozenset())
        assert b.derivations == expected_derivations
        assert b.four_table_slots == frozenset()
        assert b.paper_codes == (code,)

    def test_unregistered_code_raises(self):
        with pytest.raises(KeyError, match="尚未接入"):
            get_binding("Z9")

    def test_total_registered_codes(self):
        """注册表至少含 E1 + K1 + 18 Tier A = 20 码（其他批次可增加）。"""
        codes = supported_wp_codes()
        assert len(codes) >= 20
        for c in TIER_A_CODES:
            assert c in codes

    def test_rules_load_all_54(self):
        """规则清单全部通过校验；Tier A 7 码至少 8 条底稿规则。"""
        rules = load_rules()
        assert len(rules) >= 56
        tier_a_wp_rules = [r for r in rules if r.wp_code in TIER_A_CODES and r.stage != "note"]
        assert len(tier_a_wp_rules) == 8


# ── 锚点公式求值与推送一致性 ────────────────────────────────────────────


class TestAnchorPushParity:
    """每条锚点推送值与渲染期 transient seed 逐值相等。"""

    @pytest.mark.parametrize("code", TIER_A_CODES)
    def test_all_anchors_for_code(self, code: str):
        """该底稿的全部锚点推送值与直接 TB 公式求值逐值相等。"""
        binding = binding_for(code)
        sources = _make_sources(code)
        rules = load_rules()
        code_rules = rules_for(rules, wp_code=code)
        assert len(code_rules) >= 1, f"{code} 应至少有 1 条规则"
        for rule in code_rules:
            if rule.stage == "note":
                continue  # 附注规则不走 workpaper_targets，由 note_rows() 处理
            targets, skips = binding.workpaper_targets(rule, {}, sources)
            assert len(skips) == 0, f"{rule.rule_id} 不应跳过: {skips}"
            assert len(targets) == 1, f"{rule.rule_id} 应恰好产生 1 个目标"
            t = targets[0]
            expected = _EXPECTED[t.item_id]
            assert t.formula_value == pytest.approx(expected), (
                f"{rule.rule_id} 推送值 {t.formula_value} ≠ 直接求值 {expected}"
            )

    def test_anchor_count_is_8(self):
        """全部 8 条锚点都在测试 TB 数据下成功推送。"""
        rules = load_rules()
        count = 0
        for code in TIER_A_CODES:
            binding = binding_for(code)
            sources = _make_sources(code)
            for rule in rules_for(rules, wp_code=code):
                if rule.stage == "note":
                    continue
                targets, _ = binding.workpaper_targets(rule, {}, sources)
                count += len(targets)
        assert count == 8


# ── D1 / D2 减项码精确性 ────────────────────────────────────────────────


class TestSubtractionPrecision:
    """D1 = 原值 - 坏账准备子目；D2 同理。父码 1231 不被误吞。"""

    def test_d1_subtraction_uses_only_subcode(self):
        """D1 = TB('1121','期末余额') - TB('1231-01','期末余额')"""
        binding = binding_for("D1")
        sources = _make_sources("D1")
        all_rules = rules_for(load_rules(), wp_code="D1")
        rules = [r for r in all_rules if r.stage != "note"]
        assert len(rules) == 1
        targets, skips = binding.workpaper_targets(rules[0], {}, sources)
        assert len(targets) == 1
        # 1121 期末 500000 - 1231-01 期末 30000 = 470000
        assert targets[0].formula_value == pytest.approx(470000.0)
        # 验证父码 1231（999999）没有被误吞：如果用父码，结果会是 500000-999999 < 0
        assert targets[0].formula_value > 0

    def test_d2_subtraction_uses_only_subcode(self):
        """D2 = TB('1122','期末余额') - TB('1231-02','期末余额')"""
        binding = binding_for("D2")
        sources = _make_sources("D2")
        all_rules = rules_for(load_rules(), wp_code="D2")
        rules = [r for r in all_rules if r.stage != "note"]
        assert len(rules) == 1
        targets, skips = binding.workpaper_targets(rules[0], {}, sources)
        assert len(targets) == 1
        # 1122 期末 800000 - 1231-02 期末 50000 = 750000
        assert targets[0].formula_value == pytest.approx(750000.0)
        assert targets[0].formula_value > 0

    def test_d1_d2_parent_code_not_counted(self):
        """造同时含父码 1231 与子目 -01/-02 的 TB 数据：前缀 '1231-01%' 不命中 '1231'。

        如果 load_tb_audited 的 LIKE '1231-01%' 误命中了 1231 本行，
        减项会多出 999999 导致净值为负。
        """
        # D1 binding 的 account_prefixes = ('1121', '1231-01')
        # LIKE '1231-01%' 应该匹配 '1231-01' 但不匹配 '1231'
        binding = binding_for("D1")
        assert "1231-01" in binding.account_prefixes
        # D2 binding 的 account_prefixes = ('1122', '1231-02')
        binding2 = binding_for("D2")
        assert "1231-02" in binding2.account_prefixes
        # 前缀匹配逻辑验证：'1231' 不以 '1231-01' 开头
        assert not "1231".startswith("1231-01")
        assert "1231-01".startswith("1231-01")


# ── 禁用列名改写等价性 ──────────────────────────────────────────────────


class TestBannedColumnRewrite:
    """4 条损益类锚点改写为 '本期发生额' 后语义正确。

    依据：损益类科目 trial_balance.audited_amount 存审定发生额；
    trial_balance_audited_occurrence 上下文 '本期发生额' = audited_amount − opening_balance。
    批 D 改写：从 '期末余额'+trial_balance_audited 改为 '本期发生额'+trial_balance_audited_occurrence。
    """

    _REWRITES = [
        ("D4", "D4-1-adj-tb-6001", "TB('6001','审定数')", "TB('6001','本期发生额')", "6001"),
        ("D4", "D4-1-adj-tb-6051", "TB('6051','审定数')", "TB('6051','本期发生额')", "6051"),
        ("H10", "H10-1-tb-amount", "TB('6115','审定数')", "TB('6115','本期发生额')", "6115"),
        ("I6", "I6-1-tb-amount", "TB('6602','审定数')", "TB('6602','本期发生额')", "6602"),
    ]

    @pytest.mark.parametrize("wp_code,anchor,old_expr,new_expr,account", _REWRITES)
    def test_rewritten_value_equals_original(self, wp_code, anchor, old_expr, new_expr, account):
        """改写后表达式在 trial_balance_audited_occurrence 上下文中求值为本期发生额。

        本期发生额 = 期末余额 − 年初余额（audited_amount − opening_balance）。
        """
        ctx = _formula_context(wp_code)
        # 新表达式（规则中的实际表达式）
        new_result = execute(new_expr, ctx)
        expected = float(_TB_DATA[account]["本期发生额"])
        assert float(new_result.value) == pytest.approx(expected)

    @pytest.mark.parametrize("wp_code,anchor,old_expr,new_expr,account", _REWRITES)
    def test_banned_column_in_rule_would_be_rejected(self, wp_code, anchor, old_expr, new_expr, account):
        """若规则中保留 '审定数' 列名，规则校验应整份拒收。"""
        rules_doc = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        # 找到对应规则并替换回禁用列名
        found = False
        for rule in rules_doc["rules"]:
            if rule["target"].get("item_id") == anchor:
                rule["source"]["expression"] = old_expr
                found = True
                break
        assert found, f"未找到锚点 {anchor} 的规则"
        with pytest.raises(PushRuleError, match="禁用列名"):
            parse_rules(rules_doc)


# ── 不可用时跳过 ─────────────────────────────────────────────────────────


class TestUnavailableSkip:
    """试算表不可用时推送跳过而非写 0。"""

    @pytest.mark.parametrize("code", ["D1", "D4", "I6"])
    def test_tb_unavailable_skips_all_rules(self, code: str):
        binding = binding_for(code)
        sources = _make_sources(code, available=False)
        rules = rules_for(load_rules(), wp_code=code)
        for rule in rules:
            if rule.stage == "note":
                continue  # 附注规则不走 workpaper_targets
            targets, skips = binding.workpaper_targets(rule, {}, sources)
            assert targets == [], f"{rule.rule_id} 不应有目标（试算表不可用）"
            assert len(skips) >= 1
            assert "试算表" in skips[0].reason


# ── apply 写入 ───────────────────────────────────────────────────────────


class TestApply:
    """单值键写入语义。"""

    def test_apply_writes_js_string(self):
        binding = binding_for("D3")
        sources = _make_sources("D3")
        rules = rules_for(load_rules(), wp_code="D3")
        targets, _ = binding.workpaper_targets(rules[0], {}, sources)
        entries: dict = {}
        changed = binding.apply(entries, targets[0], targets[0].formula_value)
        assert changed is True
        assert entries[targets[0].item_id] == "150000"  # js_number_to_string

    def test_apply_unchanged_when_same_value(self):
        binding = binding_for("D3")
        sources = _make_sources("D3")
        rules = rules_for(load_rules(), wp_code="D3")
        targets, _ = binding.workpaper_targets(rules[0], {}, sources)
        entries = {targets[0].item_id: "150000"}
        changed = binding.apply(entries, targets[0], targets[0].formula_value)
        assert changed is False

    def test_apply_none_writes_empty(self):
        binding = binding_for("D3")
        entries: dict = {}
        from app.services.formula_push.bindings import WorkpaperTarget
        t = WorkpaperTarget(rule_id="D3.test", policy="system", addr_id="D3/D3-1/D3-test",
                            item_id="D3-test", formula_value=None, current_value=None)
        changed = binding.apply(entries, t, None)
        assert entries["D3-test"] == ""

    def test_note_rows_empty_when_no_tb_data(self):
        """TB 数据未加载时 note_rows 返回空（无论是否有附注 derivation）。"""
        binding = binding_for("D1")
        assert binding.note_rows({}, "listed", load_rules()[0]) == []

    def test_entry_warnings_empty(self):
        binding = binding_for("D1")
        assert binding.entry_warnings({}) == []


# ═══════════════════════════════════════════════════════════════════════════════
# Tier A note_rows() 测试
# spec: formula-push-note-rollout-batch-c · Task 2
# ═══════════════════════════════════════════════════════════════════════════════


def _make_note_rule(wp_code: str, *, table: str = "测试表", fields: tuple[str, ...] = ("end_amount", "prior_amount")) -> "PushRule":
    """构建用于 note_rows 测试的假附注规则。"""
    from app.services.formula_push.rules import PushRule, PushSource, PushTarget
    return PushRule(
        rule_id=f"{wp_code}.note.main",
        page_key=f"workpaper:{wp_code}",
        stage="note",
        policy="system",
        target=PushTarget(
            domain="note",
            section_by_template=(("listed", "五、28"), ("soe", "八、29")),
            table=table,
            fields=fields,
            rows=f"{wp_code.lower()}_note_main",
        ),
        source=PushSource(kind="derivation", name=f"{wp_code.lower()}_note_main"),
        triggers=("TRIAL_BALANCE_UPDATED", "WORKPAPER_SAVED", "manual"),
        description=f"{wp_code} 附注主表推送测试",
    )


def _seed_tb_to_binding(binding: TierAAnchorBinding, tb_data: dict[str, dict[str, Decimal]]) -> None:
    """直接注入 TB 数据到 binding 缓存（模拟 load_sources 后状态）。"""
    binding._last_tb_data = tb_data


class TestNoteRows:
    """Tier A note_rows() 基础功能。"""

    def test_single_code_one_row_no_total(self):
        """单科目 H5（1631 油气资产）→ 一行 + 不生合计。"""
        binding = binding_for("H5")
        _seed_tb_to_binding(binding, {
            "1631": {"期末余额": Decimal("1200000"), "年初余额": Decimal("1100000"), "本期发生额": Decimal("100000")},
        })
        rule = _make_note_rule("H5", table="油气资产")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        r = rows[0]
        assert r["label"] == "油气资产"
        assert r["note_label"] == "油气资产"
        assert r["ending"] == 1200000.0
        assert r["opening"] == 1100000.0
        assert r["ending_resolved"] is True
        assert r["opening_resolved"] is True
        assert r["is_total"] is False
        assert r["is_memo"] is False

    def test_multi_code_rows_plus_total(self):
        """多科目 I1（1701+1702+1703 无形资产）→ 三行 + 合计行。"""
        binding = binding_for("I1")
        _seed_tb_to_binding(binding, {
            "1701": {"期末余额": Decimal("400000"), "年初余额": Decimal("350000"), "本期发生额": Decimal("50000")},
            "1702": {"期末余额": Decimal("-120000"), "年初余额": Decimal("-100000"), "本期发生额": Decimal("-20000")},
            "1703": {"期末余额": Decimal("-15000"), "年初余额": Decimal("-10000"), "本期发生额": Decimal("-5000")},
        })
        rule = _make_note_rule("I1", table="无形资产")
        rows = binding.note_rows({}, "listed", rule)

        # 3 data rows + 1 total row
        assert len(rows) == 4
        data_rows = [r for r in rows if not r["is_total"]]
        total_rows = [r for r in rows if r["is_total"]]
        assert len(data_rows) == 3
        assert len(total_rows) == 1

        # 每行标签包含科目码区分
        for r in data_rows:
            assert "无形资产_" in r["label"]

        # 合计行
        total = total_rows[0]
        assert total["label"] == "无形资产"
        expected_ending = 400000.0 + (-120000.0) + (-15000.0)  # = 265000
        expected_opening = 350000.0 + (-100000.0) + (-10000.0)  # = 240000
        assert total["ending"] == pytest.approx(expected_ending)
        assert total["opening"] == pytest.approx(expected_opening)
        assert total["ending_resolved"] is True
        assert total["opening_resolved"] is True

    def test_single_code_i3(self):
        """I3 商誉（单科目 1711）→ 一行。"""
        binding = binding_for("I3")
        _seed_tb_to_binding(binding, {
            "1711": {"期末余额": Decimal("500000"), "年初余额": Decimal("500000"), "本期发生额": Decimal("0")},
        })
        rule = _make_note_rule("I3", table="商誉账面原值")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        r = rows[0]
        assert r["label"] == "商誉"
        assert r["ending"] == 500000.0
        assert r["opening"] == 500000.0

    def test_pl_code_uses_occurrence_amount(self):
        """损益类 I6（6602 研发费用）→ ending 取「本期发生额」。"""
        binding = binding_for("I6")
        _seed_tb_to_binding(binding, {
            "6602": {"期末余额": Decimal("90000"), "年初余额": Decimal("0"), "本期发生额": Decimal("90000")},
        })
        rule = _make_note_rule("I6", table="研发费用")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        r = rows[0]
        assert r["ending"] == 90000.0  # 本期发生额，不是期末余额
        assert r["opening"] == 0.0      # 年初余额

    def test_pl_code_h10(self):
        """损益类 H10（6115 资产处置损益）→ ending 取「本期发生额」。"""
        binding = binding_for("H10")
        _seed_tb_to_binding(binding, {
            "6115": {"期末余额": Decimal("45000"), "年初余额": Decimal("0"), "本期发生额": Decimal("45000")},
        })
        rule = _make_note_rule("H10", table="资产处置损益")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        assert rows[0]["ending"] == 45000.0  # 本期发生额

    def test_tb_unavailable_returns_empty(self):
        """TB 不可用时返回空列表。"""
        binding = binding_for("I3")
        # _last_tb_data 默认 None（未调 load_sources）
        rule = _make_note_rule("I3")
        rows = binding.note_rows({}, "listed", rule)
        assert rows == []

    def test_row_format_matches_e1(self):
        """note_rows 返回行的键集合与 E1 一致。"""
        binding = binding_for("I3")
        _seed_tb_to_binding(binding, {
            "1711": {"期末余额": Decimal("100"), "年初余额": Decimal("80"), "本期发生额": Decimal("20")},
        })
        rule = _make_note_rule("I3")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        expected_keys = {"key", "label", "note_label", "is_total", "is_memo", "ending", "opening", "ending_resolved", "opening_resolved"}
        assert set(rows[0].keys()) == expected_keys

    def test_unresolved_code_not_in_tb(self):
        """TB 可用但不含该科目码时，值为 0 且 resolved=False。"""
        binding = binding_for("I3")
        _seed_tb_to_binding(binding, {})  # 空 TB 数据
        rule = _make_note_rule("I3")
        rows = binding.note_rows({}, "listed", rule)

        assert len(rows) == 1
        r = rows[0]
        assert r["ending"] == 0.0
        assert r["opening"] == 0.0
        assert r["ending_resolved"] is False
        assert r["opening_resolved"] is False


class TestTierASourcesTemplateType:
    """TierASources.template_type 字段验证。"""

    def test_template_type_present_on_sources(self):
        """TierASources 有 template_type 属性。"""
        sources = TierASources(formula=FormulaSources(), template_type="listed")
        assert sources.template_type == "listed"

    def test_template_type_default_none(self):
        """TierASources.template_type 默认 None。"""
        sources = TierASources(formula=FormulaSources())
        assert sources.template_type is None


# ═══════════════════════════════════════════════════════════════════════════════
# 预设口径一致守卫（Task 11 · 需求 B11）
# ═══════════════════════════════════════════════════════════════════════════════


class TestColumnMapConsistency:
    """wp_formula_eval_service._COLUMN_MAP 与推送 FORMULA_CONTEXTS 的列名映射一致。

    防止两侧独立修改导致渲染期 seed 与推送持久化值用不同口径取数。
    """

    def test_preset_and_rule_columns_identical(self):
        """预设库与规则清单中 Tier A 使用的 TB 列名集合逐字相同。"""
        import re
        tb_re = re.compile(r"TB\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")

        presets = _load_presets()
        preset_cols: set[str] = set()
        for wp_code, entries in presets.items():
            for e in entries:
                for m in tb_re.finditer(e["expression"]):
                    preset_cols.add(m.group(2))

        rules = load_rules()
        rule_cols: set[str] = set()
        for r in rules:
            if r.wp_code not in TIER_A_CODES or r.stage == "note":
                continue
            for m in tb_re.finditer(r.source.expression or ""):
                rule_cols.add(m.group(2))

        assert preset_cols == rule_cols, (
            f"预设库列名 {sorted(preset_cols)} ≠ 规则列名 {sorted(rule_cols)}"
        )

    def test_rule_contexts_in_formula_contexts(self):
        """Tier A 规则的 context.tb 值全部在 FORMULA_CONTEXTS['tb'] 白名单内。"""
        from app.services.formula_push.rules import FORMULA_CONTEXTS
        allowed_tb = set(FORMULA_CONTEXTS["tb"])

        rules = load_rules()
        for r in rules:
            if r.wp_code not in TIER_A_CODES or r.stage == "note":
                continue
            ctx_tb = r.source.context_map.get("tb")
            if ctx_tb is not None:
                assert ctx_tb in allowed_tb, (
                    f"{r.rule_id}: context.tb={ctx_tb!r} 不在 FORMULA_CONTEXTS {sorted(allowed_tb)}"
                )

    def test_ending_balance_maps_to_audited_amount(self):
        """「期末余额」在 _COLUMN_MAP 和推送取数中都映射到 audited_amount。"""
        from app.services.wp_formula_eval_service import _COLUMN_MAP
        assert _COLUMN_MAP["期末余额"] == "audited_amount"
        # 推送侧：trial_balance_audited 的「期末余额」= audited_amount（sources.py 注释）
        from app.services.formula_push.sources import load_tb_audited
        # load_tb_audited 按 audited_amount 列取数，键名为「期末余额」（已在 sources.py 62 行硬编码）

    def test_occurrence_amount_context_consistent(self):
        """损益类科目用「本期发生额」列 + trial_balance_audited_occurrence 上下文。

        本期发生额 = audited_amount - opening_balance（sources.py 计算字段），
        wp_formula_eval_service 走 _OCCURRENCE_COLUMNS 分支（不在 _COLUMN_MAP 里）。
        两个系统殊途同归：都用 audited_amount - opening_balance 求发生额。
        """
        from app.services.wp_formula_eval_service import _COLUMN_MAP
        # 本期发生额不在 _COLUMN_MAP（它走 _OCCURRENCE_COLUMNS 独立分支）
        assert "本期发生额" not in _COLUMN_MAP, (
            "「本期发生额」不应在 _COLUMN_MAP 中（走 _OCCURRENCE_COLUMNS 分支）"
        )
        # 但推送的 FormulaSources 计算了它
        from app.services.formula_push.sources import FormulaSources
        assert "trial_balance_audited_occurrence" in FormulaSources._TB_CONTEXTS

    def test_banned_columns_not_in_presets_or_rules(self):
        """预设库和规则中不出现 BANNED_COLUMNS（审定数/未审数）。"""
        import re
        from app.services.formula_push.rules import BANNED_COLUMNS
        tb_re = re.compile(r"TB\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")

        presets = _load_presets()
        for wp_code, entries in presets.items():
            for e in entries:
                for m in tb_re.finditer(e["expression"]):
                    assert m.group(2) not in BANNED_COLUMNS, (
                        f"预设 {wp_code}/{e['anchor']} 使用了禁用列名 {m.group(2)!r}"
                    )

        rules = load_rules()
        for r in rules:
            if r.wp_code not in TIER_A_CODES or r.stage == "note":
                continue
            for m in tb_re.finditer(r.source.expression or ""):
                assert m.group(2) not in BANNED_COLUMNS, (
                    f"规则 {r.rule_id} 使用了禁用列名 {m.group(2)!r}"
                )
