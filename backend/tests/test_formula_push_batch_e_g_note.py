"""G 循环（G1~G14）附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e / Task 7

覆盖范围：
- 14 个科目的 note.main 规则 section_by_template 验证（参数化，与前端真源逐字对拍）
- 14 个科目的 fields 统一为 end_amount / prior_amount
- 14 个科目的 policy 统一为 editable（需求 E8：不进独占集合）
- G13/G14 上市侧关键词章节（三、公允价值变动收益 / 三、信用减值损失）
- G2/G3 共用章节 五、8 / 八、9
- G1/G10 主表章节号（trading 侧；derivative 另有子规则不在 note.main 范围）
- balance_adj（G1~G6/G8~G10）与 note_direct（G7/G11~G14）binding note_rows 行为
- 资产负债类 ending 取「期末余额」/ 损益类 ending 取「本期发生额」
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_push.rules import load_rules, PushRule
from app.services.formula_push.bindings.balance_adj import (
    BalanceAdjudicationBinding,
    binding_for as balance_adj_for,
)
from app.services.formula_push.bindings.note_direct import (
    NoteDirectBinding,
    note_direct_for,
)


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _g_note_rule(code: str) -> PushRule:
    """从 formula_push_rules.json 加载指定科目的 note.main 规则。"""
    rules = load_rules()
    return next(r for r in rules if r.rule_id == f"{code}.note.main")


def _make_tb(code: str, ending: str, opening: str, current: str = "0") -> dict:
    """构造 TB 快照。"""
    return {
        code: {
            "期末余额": Decimal(ending),
            "年初余额": Decimal(opening),
            "本期发生额": Decimal(current),
        },
    }


# ── 章节号真源（前端 *NoteSectionMap.ts 逐字提取） ──────────────────────────
#
# G1 / G10 前端有 {trading, derivative} 两级，规则 note.main 只对应 trading 侧。
# G13 / G14 上市侧走关键词章节。
# G2 / G3 共用章节 五、8 / 八、9。

# (wp_code, listed_section, soe_section)
G_SECTIONS = [
    ("G1",  "五、2",                "八、2"),
    ("G2",  "五、8",                "八、9"),
    ("G3",  "五、8",                "八、9"),
    ("G4",  "五、14",               "八、15"),
    ("G5",  "五、16",               "八、17"),
    ("G6",  "五、15",               "八、16"),
    ("G7",  "五、18",               "八、18"),
    ("G8",  "五、19",               "八、19"),
    ("G9",  "五、20",               "八、20"),
    ("G10", "五、34",               "八、34"),
    ("G11", "五、69",               "八、70"),
    ("G12", "五、70",               "八、71"),
    ("G13", "三、公允价值变动收益",  "八、72"),
    ("G14", "三、信用减值损失",      "八、73"),
]

ALL_G_CODES = [t[0] for t in G_SECTIONS]


# ========================================================================
# 章节号冻结映射
# ========================================================================


@pytest.mark.parametrize(
    "code,listed,soe", G_SECTIONS, ids=[t[0] for t in G_SECTIONS],
)
def test_g_note_rule_section_by_template(code: str, listed: str, soe: str):
    """每个 G 科目的 note.main 规则章节号与前端 *NoteSectionMap.ts 一致。"""
    rule = _g_note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ========================================================================
# 全科目字段统一验证
# ========================================================================


@pytest.mark.parametrize("code", ALL_G_CODES, ids=ALL_G_CODES)
def test_g_note_rule_fields_are_end_and_prior(code: str):
    """G 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _g_note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ========================================================================
# policy = editable（附注不进独占集合，需求 E8）
# ========================================================================


@pytest.mark.parametrize("code", ALL_G_CODES, ids=ALL_G_CODES)
def test_g_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _g_note_rule(code)
    assert rule.policy == "editable"


# ========================================================================
# G13 / G14 上市侧关键词章节格式验证
# ========================================================================


def test_g13_listed_section_is_keyword():
    """G13 上市侧章节号是关键词形式「三、公允价值变动收益」，非「五、N」。"""
    rule = _g_note_rule("G13")
    listed = rule.target.sections["listed"]
    assert listed.startswith("三、"), "G13 上市侧属「三、」整章"
    assert "公允价值变动收益" in listed
    assert not listed.startswith("五、"), "不应是 五、N 形式"


def test_g14_listed_section_is_keyword():
    """G14 上市侧章节号是关键词形式「三、信用减值损失」，非「五、N」。"""
    rule = _g_note_rule("G14")
    listed = rule.target.sections["listed"]
    assert listed.startswith("三、"), "G14 上市侧属「三、」整章"
    assert "信用减值损失" in listed
    assert not listed.startswith("五、"), "不应是 五、N 形式"


def test_g13_soe_section_is_standard():
    """G13 国企侧章节号是标准形式「八、72」。"""
    rule = _g_note_rule("G13")
    assert rule.target.sections["soe"] == "八、72"


def test_g14_soe_section_is_standard():
    """G14 国企侧章节号是标准形式「八、73」。"""
    rule = _g_note_rule("G14")
    assert rule.target.sections["soe"] == "八、73"


# ========================================================================
# G2 / G3 共用章节验证
# ========================================================================


def test_g2_g3_share_same_section():
    """G2 和 G3 共用章节 五、8 / 八、9（互不覆盖由各自表名隔离）。"""
    r2 = _g_note_rule("G2")
    r3 = _g_note_rule("G3")
    assert r2.target.sections == r3.target.sections
    # 但表名不同
    assert r2.target.table != r3.target.table
    assert r2.target.table == "应收利息"
    assert r3.target.table == "应收股利"


# ========================================================================
# 表名验证
# ========================================================================


G_TABLE_EXPECTED = {
    "G1": "交易性金融资产",
    "G2": "应收利息",
    "G3": "应收股利",
    "G4": "债权投资",
    "G5": "长期应收款",
    "G6": "其他债权投资",
    "G7": "长期股权投资",
    "G8": "其他权益工具投资",
    "G9": "其他非流动金融资产",
    "G10": "交易性金融负债",
    "G11": "投资收益",
    "G12": "净敞口套期收益",
    "G13": "公允价值变动收益",
    "G14": "信用减值损失",
}


@pytest.mark.parametrize(
    "code", ALL_G_CODES, ids=ALL_G_CODES,
)
def test_g_note_rule_table_name(code: str):
    """每个 G 科目的 note.main 规则表名正确。"""
    rule = _g_note_rule(code)
    assert rule.target.table == G_TABLE_EXPECTED[code]


# ========================================================================
# balance_adj binding note_rows（G1~G6 / G8~G10 资产负债类）
# ========================================================================


# (code, account_code, account_name)
G_BALANCE_ADJ_CODES = [
    ("G1",  "1101", "交易性金融资产"),
    ("G2",  "1132", "应收利息"),
    ("G3",  "1131", "应收股利"),
    ("G4",  "1504", "债权投资"),
    ("G5",  "1531", "长期应收款"),
    ("G6",  "1503", "其他债权投资"),
    ("G8",  "1503", "其他权益工具投资"),
    ("G9",  "1519", "其他非流动金融资产"),
    ("G10", "2101", "交易性金融负债"),
]


@pytest.mark.parametrize(
    "code,account_code,account_name",
    G_BALANCE_ADJ_CODES,
    ids=[t[0] for t in G_BALANCE_ADJ_CODES],
)
def test_balance_adj_note_rows_uses_ending_balance(
    code: str, account_code: str, account_name: str,
):
    """资产负债类 G 科目 note_rows: ending 取「期末余额」，opening 取「年初余额」。"""
    binding = balance_adj_for(code)
    binding._last_tb_data = _make_tb(account_code, "500000", "350000", "150000")

    rule = _g_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 500000.0, "ending 应取期末余额，非本期发生额"
    assert row["opening"] == 350000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


def test_balance_adj_tb_unavailable_returns_empty():
    """TB 不可用时 balance_adj binding 返回空行。"""
    binding = balance_adj_for("G1")
    binding._last_tb_data = None

    rule = _g_note_rule("G1")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []


# ========================================================================
# note_direct binding note_rows（G7 资产负债类 / G11~G14 损益类）
# ========================================================================


def test_g7_note_direct_uses_ending_balance():
    """G7 长期股权投资是资产负债类，note_direct ending 取「期末余额」。"""
    binding = note_direct_for("G7")
    binding._last_tb_data = _make_tb("1511", "800000", "600000", "200000")

    rule = _g_note_rule("G7")
    rows = binding.note_rows({}, "soe", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 800000.0, "G7 资产类应取期末余额"
    assert row["opening"] == 600000.0
    assert row["label"] == "长期股权投资"


# (code, account_code, account_name)
G_INCOME_CODES = [
    ("G11", "6111", "投资收益"),
    ("G12", "6103", "净敞口套期收益"),
    ("G13", "6101", "公允价值变动收益"),
    ("G14", "6702", "信用减值损失"),
]


@pytest.mark.parametrize(
    "code,account_code,account_name",
    G_INCOME_CODES,
    ids=[t[0] for t in G_INCOME_CODES],
)
def test_note_direct_income_uses_current_amount(
    code: str, account_code: str, account_name: str,
):
    """损益类 G 科目 note_rows: ending 取「本期发生额」，opening 取「年初余额」。"""
    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "0", "200000", "300000")

    rule = _g_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 300000.0, "损益类应取本期发生额"
    assert row["opening"] == 200000.0
    assert row["ending_resolved"] is True
    assert row["label"] == account_name


def test_note_direct_tb_unavailable_returns_empty():
    """TB 不可用时 note_direct binding 返回空行。"""
    binding = note_direct_for("G11")
    binding._last_tb_data = None

    rule = _g_note_rule("G11")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []


# ========================================================================
# rows 字段一致性（规则 rows 与 binding derivation 名一致）
# ========================================================================


@pytest.mark.parametrize("code", ALL_G_CODES, ids=ALL_G_CODES)
def test_g_note_rule_rows_naming(code: str):
    """每个 G 科目的 note.main 规则 rows 字段格式为 g{N}_note_main。"""
    rule = _g_note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ========================================================================
# stage = note
# ========================================================================


@pytest.mark.parametrize("code", ALL_G_CODES, ids=ALL_G_CODES)
def test_g_note_rule_stage_is_note(code: str):
    """note.main 规则的 stage 统一为 note。"""
    rule = _g_note_rule(code)
    assert rule.stage == "note"
