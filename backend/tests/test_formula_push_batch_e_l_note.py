"""L 循环（L1~L8，含 L6）附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e / Task 10

覆盖范围：
- 8 个科目全部有 note.main 规则：L1/L2/L3/L4/L5/L6/L7/L8
  - section_by_template 冻结（L3/L4/L5/L7/L8 非对称章节号）
  - fields = end_amount / prior_amount
  - policy = editable（需求 E8）
  - stage = note
  - rows 命名 = {code}_note_main（小写）
  - table name 与附注模板一致
- L2 与 K3/M1 共享章节 五、42 / 八、42（靠 table 名隔离：应付利息 vs 其他应付款 vs 应付股利）
- L3/L4/L5/L7/L8 非对称章节号验证（上市 五、N ≠ 国企 八、M，N≠M）
- L8 损益类（account_code='6603'）ending 取「本期发生额」
- L1~L7 资产负债类 ending 取「期末余额」
- L6 不在科目清单中（已有 note.main 规则）
- sync_registry 章节号与规则一致性
- binding note_rows TB 不可用返回空行
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.formula_push.rules import load_rules, PushRule
from app.services.formula_push.bindings.note_direct import note_direct_for


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _l_note_rule(code: str) -> PushRule:
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


# ── 章节号真源（前端 l*NoteSectionMap.ts 逐字提取） ──────────────────────────
#
# L1 → 五、33 / 八、33（短期借款）— 对称
# L2 → 五、42 / 八、42（应付利息）— 对称，与 K3/M1 共享章节
# L3 → 五、45 / 八、49（长期借款）— 非对称
# L4 → 五、46 / 八、50（应付债券）— 非对称
# L5 → 五、48 / 八、53（长期应付款）— 非对称
# L6 → 五、40 / 八、40（专项应付款）— 对称
# L7 → 五、52 / 八、57（其他非流动负债）— 非对称
# L8 → 五、67 / 八、68（财务费用）— 非对称，损益类

L_NOTE_SECTIONS = [
    ("L1", "五、33", "八、33"),
    ("L2", "五、42", "八、42"),
    ("L3", "五、45", "八、49"),
    ("L4", "五、46", "八、50"),
    ("L5", "五、48", "八、53"),
    ("L6", "五、40", "八、40"),
    ("L7", "五、52", "八、57"),
    ("L8", "五、67", "八、68"),
]

ALL_L_NOTE_CODES = [t[0] for t in L_NOTE_SECTIONS]

L_TABLE_EXPECTED = {
    "L1": "短期借款",
    "L2": "应付利息",
    "L3": "长期借款",
    "L4": "应付债券",
    "L5": "长期应付款",
    "L6": "专项应付款",
    "L7": "其他非流动负债",
    "L8": "财务费用",
}

# L 科目的科目码（wp_account_mapping.json 实证）
L_ACCOUNT_CODES = {
    "L1": "2001",
    "L2": "2231",
    "L3": "2501",
    "L4": "2502",
    "L5": "2701",
    "L6": "2711",
    "L7": "2801",
    "L8": "6603",  # 损益类
}

# 非对称章节号科目（上市/国企数字部分不同）
L_ASYMMETRIC_CODES = ["L3", "L4", "L5", "L7", "L8"]


# ========================================================================
# 章节号冻结映射
# ========================================================================


@pytest.mark.parametrize(
    "code,listed,soe", L_NOTE_SECTIONS, ids=[t[0] for t in L_NOTE_SECTIONS],
)
def test_l_note_rule_section_by_template(code: str, listed: str, soe: str):
    """每个 L 科目章节号与前端 l*NoteSectionMap.ts 一致。"""
    rule = _l_note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ========================================================================
# 全科目字段统一验证
# ========================================================================


@pytest.mark.parametrize("code", ALL_L_NOTE_CODES, ids=ALL_L_NOTE_CODES)
def test_l_note_rule_fields_are_end_and_prior(code: str):
    """L 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _l_note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ========================================================================
# policy = editable（附注不进独占集合，需求 E8）
# ========================================================================


@pytest.mark.parametrize("code", ALL_L_NOTE_CODES, ids=ALL_L_NOTE_CODES)
def test_l_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _l_note_rule(code)
    assert rule.policy == "editable"


# ========================================================================
# stage = note
# ========================================================================


@pytest.mark.parametrize("code", ALL_L_NOTE_CODES, ids=ALL_L_NOTE_CODES)
def test_l_note_rule_stage_is_note(code: str):
    """note.main 规则的 stage 统一为 note。"""
    rule = _l_note_rule(code)
    assert rule.stage == "note"


# ========================================================================
# rows 字段一致性
# ========================================================================


@pytest.mark.parametrize("code", ALL_L_NOTE_CODES, ids=ALL_L_NOTE_CODES)
def test_l_note_rule_rows_naming(code: str):
    """L 科目 note.main 规则 rows 字段格式为 {code}_note_main（小写）。"""
    rule = _l_note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ========================================================================
# 表名验证
# ========================================================================


@pytest.mark.parametrize("code", ALL_L_NOTE_CODES, ids=ALL_L_NOTE_CODES)
def test_l_note_rule_table_name(code: str):
    """每个 L 科目表名正确。"""
    rule = _l_note_rule(code)
    assert rule.target.table == L_TABLE_EXPECTED[code]


# ========================================================================
# L2 与 K3/M1 共享章节验证
# ========================================================================


def test_l2_k3_m1_share_same_section():
    """L2、K3、M1 共用章节 五、42 / 八、42（互不覆盖由各自 table 名隔离）。"""
    r_l2 = _l_note_rule("L2")
    r_k3 = _l_note_rule("K3")
    r_m1 = _l_note_rule("M1")

    # 三者章节号完全相同
    assert r_l2.target.sections == r_k3.target.sections
    assert r_l2.target.sections == r_m1.target.sections

    # 但表名各不相同
    tables = {r_l2.target.table, r_k3.target.table, r_m1.target.table}
    assert len(tables) == 3, "L2/K3/M1 三者表名应互不相同"
    assert r_l2.target.table == "应付利息"
    assert r_k3.target.table == "其他应付款"
    assert r_m1.target.table == "应付股利"


# ========================================================================
# L3/L4/L5/L7/L8 非对称章节号验证
# ========================================================================


@pytest.mark.parametrize("code", L_ASYMMETRIC_CODES, ids=L_ASYMMETRIC_CODES)
def test_l_asymmetric_sections(code: str):
    """L3/L4/L5/L7/L8 上市/国企章节号数字部分不同（非对称）。"""
    rule = _l_note_rule(code)
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num != soe_num, f"{code} 上市/国企章节号数字部分应不同（非对称）"


def test_l1_l2_l6_symmetric_sections():
    """L1、L2、L6 上市/国企章节号数字部分相同（对称）。"""
    for code in ("L1", "L2", "L6"):
        rule = _l_note_rule(code)
        sections = rule.target.sections
        listed_num = sections["listed"].split("、")[1]
        soe_num = sections["soe"].split("、")[1]
        assert listed_num == soe_num, f"{code} 上市/国企章节号数字部分应相同（对称）"


# ========================================================================
# L6 无 note.main 规则确认
# ========================================================================


def test_l6_has_note_main_rule():
    """L6 专项应付款有 note.main 规则：section/fields/policy/table/rows 正面验证。"""
    rule = _l_note_rule("L6")
    assert rule.target.sections == {"listed": "五、40", "soe": "八、40"}
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}
    assert rule.policy == "editable"
    assert rule.target.table == "专项应付款"
    assert rule.target.rows == "l6_note_main"
    assert rule.stage == "note"


def test_l6_note_direct_note_rows():
    """L6 专项应付款（资产负债类 2711）: ending 取「期末余额」。"""
    binding = note_direct_for("L6")
    binding._last_tb_data = _make_tb("2711", "600000", "400000", "200000")

    rule = _l_note_rule("L6")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 600000.0, "L6 ending 应取期末余额（资产负债类）"
    assert row["opening"] == 400000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == "专项应付款"


def test_l6_symmetric_sections():
    """L6 专项应付款上市/国企章节号数字部分相同（对称）。"""
    rule = _l_note_rule("L6")
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num == soe_num, "L6 上市/国企章节号数字部分应相同（对称）"


# ========================================================================
# sync_registry 章节号与规则一致性
# ========================================================================


def _load_sync_registry() -> list[dict]:
    """加载 note_workpaper_sync_registry.json。"""
    path = Path(__file__).resolve().parents[1] / "data" / "note_workpaper_sync_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("entries", data)


@pytest.mark.parametrize(
    "code,listed,soe", L_NOTE_SECTIONS, ids=[t[0] for t in L_NOTE_SECTIONS],
)
def test_l_sync_registry_matches_rule(code: str, listed: str, soe: str):
    """sync_registry 中的章节号与 note.main 规则的 section_by_template 一致。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == code), None)
    assert entry is not None, f"{code} 应在 sync_registry 中"
    assert entry.get("listed") == listed, f"{code} sync_registry listed 章节号不一致"
    assert entry.get("soe") == soe, f"{code} sync_registry soe 章节号不一致"


# ========================================================================
# note_direct binding note_rows — 资产负债类（L1~L7 除 L8）
# ========================================================================


# (code, account_code, account_name)
L_BALANCE_CODES = [
    ("L1", "2001", "短期借款"),
    ("L2", "2231", "应付利息"),
    ("L3", "2501", "长期借款"),
    ("L4", "2502", "应付债券"),
    ("L5", "2701", "长期应付款"),
    ("L6", "2711", "专项应付款"),
    ("L7", "2801", "其他非流动负债"),
]


@pytest.mark.parametrize(
    "code,account_code,account_name",
    L_BALANCE_CODES,
    ids=[t[0] for t in L_BALANCE_CODES],
)
def test_l_note_direct_note_rows_uses_ending_balance(
    code: str, account_code: str, account_name: str,
):
    """L1~L7 资产负债类 note_rows: ending 取「期末余额」，opening 取「年初余额」。"""
    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "500000", "350000", "150000")

    rule = _l_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 500000.0, f"{code} ending 应取期末余额，非本期发生额"
    assert row["opening"] == 350000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


# ========================================================================
# L8 损益类 binding note_rows（6603 财务费用）
# ========================================================================


def test_l8_is_income_type_uses_current_amount():
    """L8 财务费用（损益类 6603）: ending 取「本期发生额」，opening 取「年初余额」。"""
    binding = note_direct_for("L8")
    binding._last_tb_data = _make_tb("6603", "0", "200000", "300000")

    rule = _l_note_rule("L8")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 300000.0, "损益类应取本期发生额"
    assert row["opening"] == 200000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == "财务费用"


# ========================================================================
# TB 不可用时 note_direct binding 返回空行
# ========================================================================


def test_l_note_direct_tb_unavailable_returns_empty():
    """TB 不可用时 note_direct binding 返回空行。"""
    binding = note_direct_for("L1")
    binding._last_tb_data = None

    rule = _l_note_rule("L1")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []
