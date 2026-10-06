"""I 循环（I1~I6）+ J 循环（J1、J2）附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e / Task 9

覆盖范围：
- I3 有 note.main 规则（balance_adj binding）：section_by_template / fields / policy / stage / rows naming
  - I3 有 table_by_template（上市=商誉账面原值 / 国企=（1）商誉账面价值）
  - I3 资产负债类 ending 取「期末余额」
- J1、J2 有 note.main 规则（note_direct binding）：section_by_template / fields / policy / stage / rows naming
  - J2 非对称章节号（上市 五、49 / 国企 八、54）
- I1/I2/I4/I5/I6 不存在 note.main 规则的确认
- I6 损益类（6602 研发费用）作为 tier_a 使用 trial_balance_audited_occurrence
- I3 balance_adj note_rows 取数行为（单科目码 1711）
- J1/J2 note_direct note_rows 取数行为（J1: 2211 / J2: 2611）
- sync_registry 章节号与规则章节号一致性
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.formula_push.rules import load_rules, PushRule


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _note_rule(code: str) -> PushRule:
    """从 formula_push_rules.json 加载指定科目的 note.main 规则。"""
    rules = load_rules()
    return next(r for r in rules if r.rule_id == f"{code}.note.main")


def _has_note_main_rule(code: str) -> bool:
    """检查指定科目是否存在 note.main 规则。"""
    rules = load_rules()
    return any(r.rule_id == f"{code}.note.main" for r in rules)


def _make_tb(code: str, ending: str, opening: str, current: str = "0") -> dict:
    """构造 TB 快照。"""
    return {
        code: {
            "期末余额": Decimal(ending),
            "年初余额": Decimal(opening),
            "本期发生额": Decimal(current),
        },
    }


# ── 章节号真源（前端 *NoteSectionMap.ts + sync_registry 逐字提取） ──────────
#
# I3 → 五、28 / 八、29（商誉）— 非对称
# J1 → 五、40 / 八、40（应付职工薪酬）
# J2 → 五、49 / 八、54（长期应付职工薪酬）— 非对称

IJ_NOTE_SECTIONS = [
    ("I3", "五、28", "八、29"),
    ("J1", "五、40", "八、40"),
    ("J2", "五、49", "八、54"),
]

ALL_IJ_NOTE_CODES = [t[0] for t in IJ_NOTE_SECTIONS]

# I/J 系列中没有 note.main 规则的科目
IJ_CODES_WITHOUT_NOTE = ["I1", "I2", "I4", "I5", "I6"]


# ========================================================================
# 章节号冻结映射
# ========================================================================


@pytest.mark.parametrize(
    "code,listed,soe", IJ_NOTE_SECTIONS, ids=[t[0] for t in IJ_NOTE_SECTIONS],
)
def test_ij_note_rule_section_by_template(code: str, listed: str, soe: str):
    """每个有 note.main 的 I/J 科目章节号与前端 *NoteSectionMap.ts 一致。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ========================================================================
# 全科目字段统一验证
# ========================================================================


@pytest.mark.parametrize("code", ALL_IJ_NOTE_CODES, ids=ALL_IJ_NOTE_CODES)
def test_ij_note_rule_fields_are_end_and_prior(code: str):
    """I/J 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ========================================================================
# policy = editable（附注不进独占集合，需求 E8）
# ========================================================================


@pytest.mark.parametrize("code", ALL_IJ_NOTE_CODES, ids=ALL_IJ_NOTE_CODES)
def test_ij_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _note_rule(code)
    assert rule.policy == "editable"


# ========================================================================
# stage = note
# ========================================================================


@pytest.mark.parametrize("code", ALL_IJ_NOTE_CODES, ids=ALL_IJ_NOTE_CODES)
def test_ij_note_rule_stage_is_note(code: str):
    """note.main 规则的 stage 统一为 note。"""
    rule = _note_rule(code)
    assert rule.stage == "note"


# ========================================================================
# rows 字段一致性
# ========================================================================


@pytest.mark.parametrize("code", ALL_IJ_NOTE_CODES, ids=ALL_IJ_NOTE_CODES)
def test_ij_note_rule_rows_naming(code: str):
    """I/J 科目 note.main 规则 rows 字段格式为 {code}_note_main（小写）。"""
    rule = _note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ========================================================================
# 表名验证
# ========================================================================


IJ_TABLE_EXPECTED = {
    "I3": "商誉",
    "J1": "应付职工薪酬",
    "J2": "长期应付职工薪酬",
}


@pytest.mark.parametrize("code", ALL_IJ_NOTE_CODES, ids=ALL_IJ_NOTE_CODES)
def test_ij_note_rule_table_name(code: str):
    """每个有 note.main 的 I/J 科目表名正确。"""
    rule = _note_rule(code)
    assert rule.target.table == IJ_TABLE_EXPECTED[code]


# ========================================================================
# I3 table_by_template 变体验证
# ========================================================================


def test_i3_has_table_by_template():
    """I3 商誉有 table_by_template：上市=商誉账面原值 / 国企=（1）商誉账面价值。"""
    rule = _note_rule("I3")
    tbt = rule.target.tables_by_template
    assert tbt.get("listed") == "商誉账面原值", "I3 上市表名"
    assert tbt.get("soe") == "（1）商誉账面价值", "I3 国企表名"


def test_i3_resolve_table_by_template_type():
    """I3 resolve_table 按准则变体选表名。"""
    rule = _note_rule("I3")
    assert rule.target.resolve_table("listed") == "商誉账面原值"
    assert rule.target.resolve_table("soe") == "（1）商誉账面价值"


def test_j1_j2_no_table_by_template():
    """J1/J2 无 table_by_template（上市国企表名相同）。"""
    for code in ("J1", "J2"):
        rule = _note_rule(code)
        assert rule.target.tables_by_template == {}, f"{code} 不应有 table_by_template"


# ========================================================================
# J2 非对称章节号验证
# ========================================================================


def test_j2_asymmetric_sections():
    """J2 长期应付职工薪酬：上市 五、49 ≠ 国企 八、54（非对称章节号）。"""
    rule = _note_rule("J2")
    sections = rule.target.sections
    # 上市章节号的数字部分
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num != soe_num, "J2 上市/国企章节号数字部分应不同（非对称）"
    assert sections["listed"] == "五、49"
    assert sections["soe"] == "八、54"


# ========================================================================
# 无 note.main 规则的科目确认
# ========================================================================


@pytest.mark.parametrize("code", IJ_CODES_WITHOUT_NOTE, ids=IJ_CODES_WITHOUT_NOTE)
def test_ij_code_without_note_main(code: str):
    """I1/I2/I4/I5/I6 不存在 note.main 规则。"""
    assert not _has_note_main_rule(code), f"{code} 不应有 note.main 规则"


# ========================================================================
# sync_registry 章节号与规则一致性
# ========================================================================


def _load_sync_registry() -> list[dict]:
    """加载 note_workpaper_sync_registry.json。"""
    path = Path(__file__).resolve().parents[1] / "data" / "note_workpaper_sync_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("entries", data)


@pytest.mark.parametrize(
    "code,listed,soe", IJ_NOTE_SECTIONS, ids=[t[0] for t in IJ_NOTE_SECTIONS],
)
def test_ij_sync_registry_matches_rule(code: str, listed: str, soe: str):
    """sync_registry 中的章节号与 note.main 规则的 section_by_template 一致。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == code), None)
    assert entry is not None, f"{code} 应在 sync_registry 中"
    assert entry.get("listed") == listed, f"{code} sync_registry listed 章节号不一致"
    assert entry.get("soe") == soe, f"{code} sync_registry soe 章节号不一致"


# ========================================================================
# I3 balance_adj binding note_rows 行为
# ========================================================================


def test_i3_balance_adj_note_rows_uses_ending_balance():
    """I3 商誉（资产负债类 1711）: note_rows ending 取「期末余额」，opening 取「年初余额」。"""
    from app.services.formula_push.bindings.balance_adj import binding_for as balance_adj_for

    binding = balance_adj_for("I3")
    binding._last_tb_data = _make_tb("1711", "800000", "600000", "200000")

    rule = _note_rule("I3")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 800000.0, "资产负债类应取期末余额，非本期发生额"
    assert row["opening"] == 600000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == "商誉"


def test_i3_balance_adj_tb_unavailable_returns_empty():
    """I3 TB 不可用时 balance_adj binding 返回空行。"""
    from app.services.formula_push.bindings.balance_adj import binding_for as balance_adj_for

    binding = balance_adj_for("I3")
    binding._last_tb_data = None

    rule = _note_rule("I3")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []


# ========================================================================
# I1 多科目码 balance_adj note_rows（1701/1702/1703B → 3 行 + 1 合计行）
# ========================================================================


def test_i1_multi_code_note_rows_produces_total():
    """I1 无形资产有 3 个 account_codes（1701/1702/1703B），note_rows 应产生 3 行数据 + 1 行合计。"""
    from app.services.formula_push.bindings.balance_adj import binding_for as balance_adj_for

    binding = balance_adj_for("I1")
    binding._last_tb_data = {
        "1701": {"期末余额": Decimal("200000"), "年初余额": Decimal("150000"), "本期发生额": Decimal("50000")},
        "1702": {"期末余额": Decimal("100000"), "年初余额": Decimal("80000"), "本期发生额": Decimal("20000")},
        "1703B": {"期末余额": Decimal("50000"), "年初余额": Decimal("30000"), "本期发生额": Decimal("20000")},
    }

    # I1 无 note.main 规则，借 I3 的 rule 做代理（仅测 TB 取数 + 合计逻辑）
    rule = _note_rule("I3")
    rows = binding.note_rows({}, "listed", rule)

    # 3 个数据行 + 1 个合计行
    assert len(rows) == 4
    data_rows = [r for r in rows if not r["is_total"]]
    total_rows = [r for r in rows if r["is_total"]]
    assert len(data_rows) == 3
    assert len(total_rows) == 1

    # 合计行 ending = 200000 + 100000 + 50000 = 350000
    assert total_rows[0]["ending"] == 350000.0
    assert total_rows[0]["opening"] == 260000.0  # 150000 + 80000 + 30000
    assert total_rows[0]["label"] == "无形资产"


# ========================================================================
# J1/J2 note_direct binding note_rows 行为
# ========================================================================


def test_j1_note_direct_note_rows():
    """J1 应付职工薪酬（资产负债类 2211）: ending 取「期末余额」，opening 取「年初余额」。"""
    from app.services.formula_push.bindings.note_direct import note_direct_for

    binding = note_direct_for("J1")
    binding._last_tb_data = _make_tb("2211", "500000", "300000", "200000")

    rule = _note_rule("J1")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 500000.0, "J1 资产负债类应取期末余额"
    assert row["opening"] == 300000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == "应付职工薪酬"


def test_j2_note_direct_note_rows():
    """J2 长期应付职工薪酬（资产负债类 2611）: ending 取「期末余额」，opening 取「年初余额」。"""
    from app.services.formula_push.bindings.note_direct import note_direct_for

    binding = note_direct_for("J2")
    binding._last_tb_data = _make_tb("2611", "1200000", "900000", "300000")

    rule = _note_rule("J2")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 1200000.0, "J2 资产负债类应取期末余额"
    assert row["opening"] == 900000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == "长期应付职工薪酬"


def test_j1_note_direct_tb_unavailable_returns_empty():
    """J1 TB 不可用时 note_direct binding 返回空行。"""
    from app.services.formula_push.bindings.note_direct import note_direct_for

    binding = note_direct_for("J1")
    binding._last_tb_data = None

    rule = _note_rule("J1")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []


# ========================================================================
# I6 损益类验证（tier_a，无 note.main，但确认其 source 规则用 occurrence 上下文）
# ========================================================================


def test_i6_source_rule_uses_occurrence_context():
    """I6 研发费用（损益类 6602）source 规则使用 trial_balance_audited_occurrence 上下文。"""
    rules = load_rules()
    i6_source = next(r for r in rules if r.rule_id == "I6.1_tb_amount")
    assert i6_source.source.context_map.get("tb") == "trial_balance_audited_occurrence", \
        "I6 损益类应使用 occurrence 上下文"
    assert "本期发生额" in i6_source.source.expression, \
        "I6 表达式应包含「本期发生额」"


def test_i6_no_note_main_rule():
    """I6 研发费用无 note.main 规则（损益类走 tier_a，附注推送不在当前规则集中）。"""
    assert not _has_note_main_rule("I6"), "I6 不应有 note.main 规则"
