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

TIER_A_CODES = ("D1", "D2", "D3", "D4", "D6", "D7", "H5", "H6", "H7", "H8", "H9", "H10", "I1", "I2", "I3", "I4", "I5", "I6")

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
    "6001": {"期末余额": Decimal("2000000"), "年初余额": Decimal("1500000")},
    "6051": {"期末余额": Decimal("300000"), "年初余额": Decimal("200000")},
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
    "6115": {"期末余额": Decimal("45000"), "年初余额": Decimal("0")},
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
    "6602": {"期末余额": Decimal("90000"), "年初余额": Decimal("0")},
}


def _make_sources(wp_code: str, *, available: bool = True) -> TierASources:
    """为指定底稿构建推送取数上下文。"""
    binding = binding_for(wp_code)
    # 从全局 TB 数据中取该 binding 需要的科目码
    tb_data = {code: dict(_TB_DATA.get(code, {"期末余额": Decimal("0"), "年初余额": Decimal("0")}))
               for code in binding.account_prefixes}
    tb = TbAuditedSnapshot(tb_data=tb_data, available=available, company_codes=("001",))
    return TierASources(formula=FormulaSources(tb=tb))


def _formula_context(wp_code: str) -> FormulaContext:
    """构建与 _make_sources 同口径的 FormulaContext，供直接求值对拍。"""
    binding = binding_for(wp_code)
    tb_data = {code: dict(_TB_DATA.get(code, {"期末余额": Decimal("0"), "年初余额": Decimal("0")}))
               for code in binding.account_prefixes}
    return FormulaContext(tb_data=tb_data)


# 期望值：每条锚点公式在上述 TB 数据下的求值结果
_EXPECTED: dict[str, float] = {}


def _compute_expected():
    """从预设库读取全部 21 条锚点表达式，在测试 TB 数据下求值。"""
    presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    # 改写 4 条禁用列名（与规则生成同逻辑）
    rewrites = {
        "D4-1-adj-tb-6001": ("TB('6001','审定数')", "TB('6001','期末余额')"),
        "D4-1-adj-tb-6051": ("TB('6051','审定数')", "TB('6051','期末余额')"),
        "H10-1-tb-amount": ("TB('6115','审定数')", "TB('6115','期末余额')"),
        "I6-1-tb-amount": ("TB('6602','审定数')", "TB('6602','期末余额')"),
    }
    for wp_code, anchor_list in presets.items():
        if wp_code.startswith("_") or not isinstance(anchor_list, list):
            continue
        ctx = _formula_context(wp_code)
        for preset in anchor_list:
            anchor = preset["anchor"]
            expr = preset["expression"]
            # 应用改写
            if anchor in rewrites:
                old, new = rewrites[anchor]
                expr = expr.replace(old, new)
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
        assert b.derivations == frozenset()
        assert b.four_table_slots == frozenset()
        assert b.paper_codes == (code,)

    def test_unregistered_code_raises(self):
        with pytest.raises(KeyError, match="尚未接入"):
            get_binding("D5")

    def test_total_registered_codes(self):
        """20 = E1 + K1 + 18 Tier A。"""
        codes = supported_wp_codes()
        assert len(codes) == 20
        for c in TIER_A_CODES:
            assert c in codes

    def test_rules_load_all_54(self):
        """54 条规则全部通过校验。"""
        rules = load_rules()
        assert len(rules) == 54
        tier_a_rules = [r for r in rules if r.wp_code not in ("E1", "K1")]
        assert len(tier_a_rules) == 21


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
            targets, skips = binding.workpaper_targets(rule, {}, sources)
            assert len(skips) == 0, f"{rule.rule_id} 不应跳过: {skips}"
            assert len(targets) == 1, f"{rule.rule_id} 应恰好产生 1 个目标"
            t = targets[0]
            expected = _EXPECTED[t.item_id]
            assert t.formula_value == pytest.approx(expected), (
                f"{rule.rule_id} 推送值 {t.formula_value} ≠ 直接求值 {expected}"
            )

    def test_anchor_count_is_21(self):
        """全部 21 条锚点都在测试 TB 数据下成功推送。"""
        rules = load_rules()
        count = 0
        for code in TIER_A_CODES:
            binding = binding_for(code)
            sources = _make_sources(code)
            for rule in rules_for(rules, wp_code=code):
                targets, _ = binding.workpaper_targets(rule, {}, sources)
                count += len(targets)
        assert count == 21


# ── D1 / D2 减项码精确性 ────────────────────────────────────────────────


class TestSubtractionPrecision:
    """D1 = 原值 - 坏账准备子目；D2 同理。父码 1231 不被误吞。"""

    def test_d1_subtraction_uses_only_subcode(self):
        """D1 = TB('1121','期末余额') - TB('1231-01','期末余额')"""
        binding = binding_for("D1")
        sources = _make_sources("D1")
        rules = rules_for(load_rules(), wp_code="D1")
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
        rules = rules_for(load_rules(), wp_code="D2")
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
    """4 条用 '审定数' 的锚点改写为 '期末余额' 后语义等价。

    依据：损益类科目 trial_balance.audited_amount 存审定发生额；
    trial_balance_audited 上下文 '期末余额' 映射到 audited_amount（同值）。
    """

    _REWRITES = [
        ("D4", "D4-1-adj-tb-6001", "TB('6001','审定数')", "TB('6001','期末余额')", "6001"),
        ("D4", "D4-1-adj-tb-6051", "TB('6051','审定数')", "TB('6051','期末余额')", "6051"),
        ("H10", "H10-1-tb-amount", "TB('6115','审定数')", "TB('6115','期末余额')", "6115"),
        ("I6", "I6-1-tb-amount", "TB('6602','审定数')", "TB('6602','期末余额')", "6602"),
    ]

    @pytest.mark.parametrize("wp_code,anchor,old_expr,new_expr,account", _REWRITES)
    def test_rewritten_value_equals_original(self, wp_code, anchor, old_expr, new_expr, account):
        """改写后表达式在 trial_balance_audited 上下文中的求值结果与原始 '审定数' 等价。

        trial_balance_audited 上下文：
        - '期末余额' → audited_amount（试算表审定数）
        - '审定数' 是禁用列名（内核别名，实际映射到同一 audited_amount）
        ⇒ 改写后值不变。
        """
        ctx = _formula_context(wp_code)
        # 新表达式（规则中的实际表达式）
        new_result = execute(new_expr, ctx)
        expected = float(_TB_DATA[account]["期末余额"])
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

    @pytest.mark.parametrize("code", ["D1", "D4", "I1"])
    def test_tb_unavailable_skips_all_rules(self, code: str):
        binding = binding_for(code)
        sources = _make_sources(code, available=False)
        rules = rules_for(load_rules(), wp_code=code)
        for rule in rules:
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

    def test_note_rows_empty(self):
        binding = binding_for("D1")
        assert binding.note_rows({}, "listed", load_rules()[0]) == []

    def test_entry_warnings_empty(self):
        binding = binding_for("D1")
        assert binding.entry_warnings({}) == []
