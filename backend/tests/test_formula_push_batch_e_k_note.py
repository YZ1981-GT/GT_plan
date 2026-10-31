"""K 系列附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e · Task 6

覆盖范围：
- K1~K9 / K11 / K13 共 11 个科目的 note.main 规则
- 章节号与前端 *NoteSectionMap.ts + note_workpaper_sync_registry.json 一致性
- table_by_template 变体表名正确
- balance_adj（K2~K7）和 note_direct（K8~K13）binding 的 note_rows 行为
- 损益类科目 ending 取「本期发生额」
- 资产负债类科目 ending 取「期末余额」
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_push.rules import load_rules, PushRule
from app.services.formula_push.bindings.balance_adj import BalanceAdjudicationBinding, binding_for as balance_adj_for
from app.services.formula_push.bindings.note_direct import NoteDirectBinding, note_direct_for
from app.services.formula_push.bindings.k1 import K1Binding


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _k_note_rule(code: str) -> PushRule:
    """从 formula_push_rules.json 加载指定科目的 note.main 规则。"""
    rules = load_rules()
    return next(r for r in rules if r.rule_id == f"{code}.note.main")


# ── 章节号来自前端真源 + registry 双重校验 ──

# 格式: (wp_code, listed_section, soe_section)
K_SECTIONS = [
    ("K1",  "五、8",  "八、9"),
    ("K2",  "五、13", "八、14"),
    ("K3",  "五、42", "八、42"),
    # K4 其他流动负债没有标准科目：不推附注主表（见 test_k4_has_no_account_and_no_note_rules）
    ("K5",  "五、50", "八、55"),
    ("K6",  "五、11", "八、12"),
    ("K7",  "五、51", "八、56"),
    ("K8",  "五、64", "八、65"),
    ("K9",  "五、65", "八、66"),
    ("K11", "五、77", "八、74"),
    ("K13", "五、80", "八、77"),
]


@pytest.mark.parametrize("code,listed,soe", K_SECTIONS, ids=[t[0] for t in K_SECTIONS])
def test_k_note_rule_section_by_template(code: str, listed: str, soe: str):
    """每个 K 科目的 note.main 规则章节号与前端 *NoteSectionMap.ts 一致。"""
    rule = _k_note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ── 全科目字段统一验证 ──


@pytest.mark.parametrize("code", [t[0] for t in K_SECTIONS], ids=[t[0] for t in K_SECTIONS])
def test_k_note_rule_fields_are_end_and_prior(code: str):
    """K 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _k_note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ── table_by_template 变体表名 ──


def test_k6_table_by_template():
    """K6 上市=持有待售资产和持有待售负债 / 国企=持有待售资产。"""
    rule = _k_note_rule("K6")
    assert rule.target.resolve_table("listed") == "持有待售资产和持有待售负债"
    assert rule.target.resolve_table("soe") == "持有待售资产"


def test_k8_table_by_template():
    """K8 上市=销售费用（按费用性质列示）/ 国企=销售费用。"""
    rule = _k_note_rule("K8")
    assert rule.target.resolve_table("listed") == "销售费用（按费用性质列示）"
    assert rule.target.resolve_table("soe") == "销售费用"


def test_k9_table_by_template():
    """K9 上市=管理费用（按费用性质列示）/ 国企=管理费用。"""
    rule = _k_note_rule("K9")
    assert rule.target.resolve_table("listed") == "管理费用（按费用性质列示）"
    assert rule.target.resolve_table("soe") == "管理费用"


def test_k_simple_table_no_variant():
    """K2/K3/K5/K7/K11/K13 上市/国企表名相同，无 table_by_template。"""
    for code, expected_table in [
        ("K2", "其他流动资产"),
        ("K3", "其他应付款"),
        ("K5", "预计负债"),
        ("K7", "递延收益"),
        ("K11", "资产减值损失"),
        ("K13", "营业外支出"),
    ]:
        rule = _k_note_rule(code)
        # resolve_table 应回退到 table 字段
        assert rule.target.resolve_table("listed") == expected_table, f"{code} listed"
        assert rule.target.resolve_table("soe") == expected_table, f"{code} soe"


# ── balance_adj binding note_rows（K2~K7 资产负债类） ──


def _make_tb(code: str, ending: str, opening: str, current: str = "0") -> dict:
    """构造 TB 快照，返回 {code: {列: Decimal}}。"""
    return {
        code: {
            "期末余额": Decimal(ending),
            "年初余额": Decimal(opening),
            "本期发生额": Decimal(current),
        },
    }


@pytest.mark.parametrize("code,account_code,account_name", [
    ("K2", "1901", "其他流动资产"),
    ("K3", "2241", "其他应付款"),
    ("K5", "2801", "预计负债"),
    ("K7", "2401", "递延收益"),
], ids=["K2", "K3", "K5", "K7"])
def test_balance_adj_note_rows_uses_ending_balance(code: str, account_code: str, account_name: str):
    """资产负债类 K 科目 note_rows: ending 取「期末余额」，opening 取「年初余额」。"""
    binding = balance_adj_for(code)
    binding._last_tb_data = _make_tb(account_code, "500000", "350000", "150000")

    rule = _k_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 500000.0  # 期末余额，非本期发生额
    assert row["opening"] == 350000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


def test_k6_note_rows():
    """K6 持有待售资产和负债：balance_adj，资产负债类，双科目码 1481+2245。"""
    binding = balance_adj_for("K6")
    binding._last_tb_data = {
        "1481": {"期末余额": Decimal("220000"), "年初余额": Decimal("180000"), "本期发生额": Decimal("0")},
        "2245": {"期末余额": Decimal("80000"), "年初余额": Decimal("60000"), "本期发生额": Decimal("0")},
    }

    rule = _k_note_rule("K6")
    rows = binding.note_rows({}, "soe", rule)

    # 双科目码 → 2 数据行 + 1 合计行
    assert len(rows) == 3
    data_rows = [r for r in rows if not r["is_total"]]
    total_rows = [r for r in rows if r["is_total"]]
    assert len(data_rows) == 2
    assert len(total_rows) == 1
    # 合计
    assert total_rows[0]["ending"] == 300000.0  # 220000 + 80000
    assert total_rows[0]["opening"] == 240000.0  # 180000 + 60000


# ── note_direct binding note_rows（K8~K13 损益类） ──


@pytest.mark.parametrize("code,account_code,account_name", [
    ("K8",  "6601", "销售费用"),
    ("K9",  "6602", "管理费用"),
    ("K11", "6701", "资产减值损失"),
    ("K13", "6711", "营业外支出"),
], ids=["K8", "K9", "K11", "K13"])
def test_note_direct_note_rows_uses_current_amount(code: str, account_code: str, account_name: str):
    """损益类 K 科目 note_rows: ending 取「本期发生额」（非期末余额），上期取上年试算表发生额（非本年年初余额）。"""
    from app.services.formula_push.sources import PriorPlSnapshot

    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "0", "999", "300000")  # 年初余额不该被当成上期
    binding._last_prior_pl = PriorPlSnapshot(_make_tb(account_code, "0", "0", "200000"))

    rule = _k_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 300000.0  # 本期发生额，非期末余额
    assert row["opening"] == 200000.0  # 上年发生额
    assert row["ending_resolved"] is True
    assert row["label"] == account_name


def test_pl_prior_period_unavailable_is_unresolved_not_zero():
    """损益类上期取不到上年数据 ⇒ 不出值（不推 0），原因随行带给引擎。

    2026-10-31 真库：原来取本年试算表年初余额（损益类恒 0），和平 2025 八、65 等 8 节「上期发生额」被推成 0.00，
    报表上期是上年发生额（销售费用 242,169,736.06）。spec disclosure-note-template-word-realignment Task 34/35。
    """
    from app.services.formula_push.sources import PriorPlSnapshot

    binding = note_direct_for("K8")
    binding._last_tb_data = _make_tb("6601", "0", "0", "300000")
    for prior, reason in ((None, "未取上年数据"), (PriorPlSnapshot(None, "损益类上期发生额取上年试算表：没有上年项目"),
                                                  "没有上年项目")):
        binding._last_prior_pl = prior
        row = binding.note_rows({}, "listed", _k_note_rule("K8"))[0]
        assert row["ending"] == 300000.0 and row["ending_resolved"] is True
        assert row["opening_resolved"] is False and reason in row["opening_reason"]
    # 资产负债类不受影响：期初仍取本年年初余额
    k2 = balance_adj_for("K2")
    k2._last_tb_data = _make_tb("1901", "10", "7", "3")
    k2._last_prior_pl = None
    row = k2.note_rows({}, "listed", _k_note_rule("K2"))[0]
    assert row["opening"] == 7.0 and row["opening_resolved"] is True and "opening_reason" not in row


def test_note_direct_tb_unavailable_returns_empty():
    """TB 不可用时 note_direct binding 返回空行。"""
    binding = note_direct_for("K8")
    binding._last_tb_data = None

    rule = _k_note_rule("K8")
    rows = binding.note_rows({}, "listed", rule)

    assert rows == []


# ── K1 专用 binding note_rows ──


def test_k1_binding_note_rows_from_entries():
    """K1 note_rows 从 entries 取审定净值（receivable − baddebt）。"""
    binding = K1Binding()
    binding._last_tb_data = {
        "1221": {"年初余额": Decimal("500000")},
        # 其他应收款坏账准备（试算表正数口径；原替身写负数、键用前缀 1231，R1.4）
        "1231-03": {"年初余额": Decimal("50000")},
        # 别的应收款项的坏账准备不进 K1
        "1231-02": {"年初余额": Decimal("70000")},
    }

    entries = {
        "K1-1-receivable-r0-unadj": "100",
        "K1-1-receivable-r0-aje": "20",
        "K1-1-receivable-r0-rje": "0",
        "K1-1-baddebt-r0-unadj": "30",
        "K1-1-baddebt-r0-aje": "0",
        "K1-1-baddebt-r0-rje": "0",
    }
    rule = _k_note_rule("K1")
    rows = binding.note_rows(entries, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    # ending = audited_net = (100+20+0) − (30+0+0) = 90
    assert row["ending"] == 90
    # opening = TB('1221','年初余额') − TB('1231-03','年初余额') = 500000 − 50000 = 450000
    assert row["opening"] == 450000.0
    assert row["note_label"] == "其他应收款"


def test_k1_binding_note_rows_tb_unavailable():
    """K1 TB 不可用时 opening_resolved=False，ending 仍可从 entries 计算。"""
    binding = K1Binding()
    binding._last_tb_data = None

    entries = {"K1-1-receivable-r0-unadj": "200", "K1-1-baddebt-r0-unadj": "50"}
    rule = _k_note_rule("K1")
    rows = binding.note_rows(entries, "soe", rule)

    assert len(rows) == 1
    assert rows[0]["ending"] == 150  # 200 - 50
    assert rows[0]["ending_resolved"] is True
    assert rows[0]["opening"] == 0.0
    assert rows[0]["opening_resolved"] is False


# ── K4 其他流动负债：没有标准科目 ──


def test_k4_has_no_account_and_no_note_rules():
    """K4 原规则取 TB('2261')，2261 在各项目科目表与试算表里都不存在 ⇒ 试算平衡表数与附注主表恒推 0。
    改为无科目声明：只推审定表固定行的审定合计（spec formula-fetch-followup-defect-closure R6.2）。"""
    binding = balance_adj_for("K4")
    assert binding.account_prefixes == ()
    assert "2261" in binding.no_account_reason
    assert binding.derivations == frozenset({"k4_audited_total"})
    k4_rules = sorted(r.rule_id for r in load_rules() if r.wp_code == "K4")
    assert k4_rules == ["K4.audited_total.net", "K4.audited_total.receivable"]


# ── K11 / K13 上市侧章节号截断形态 ──


def _assert_realigned(listed: str, expected: str) -> None:
    """2026-10-16 按四版 Word 把利润表科目节从会计政策章「三、」改挂到项目附注章「五、」
    （spec disclosure-note-template-word-realignment）；种子登记的旧截断编号经别名解析到新编号。"""
    import json

    from app.services.note_section_catalog import normalize_section_code, template_json_path

    assert listed == expected
    sections = json.loads(template_json_path("listed").read_text(encoding="utf-8"))["sections"]
    olds = next(s for s in sections if s["section_number"] == expected).get("legacy_section_numbers") or []
    assert olds and all(o.startswith("三、") for o in olds), olds
    assert {normalize_section_code(o, template_type="listed") for o in olds} == {expected}


def test_k11_listed_section_truncated_form():
    """K11 上市侧章节号「五、77」资产减值损失（原会计政策章截断编号现为别名）。"""
    _assert_realigned(_k_note_rule("K11").target.sections["listed"], "五、77")


def test_k13_listed_section_truncated_form():
    """K13 上市侧章节号「五、80」营业外支出（原会计政策章截断编号现为别名）。"""
    _assert_realigned(_k_note_rule("K13").target.sections["listed"], "五、80")


# ── policy = editable（附注不进独占集合） ──


@pytest.mark.parametrize("code", [t[0] for t in K_SECTIONS], ids=[t[0] for t in K_SECTIONS])
def test_k_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _k_note_rule(code)
    assert rule.policy == "editable"
