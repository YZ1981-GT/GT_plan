"""M 循环（M1~M10）+ N 循环（N1~N5）+ F 循环（F1~F4）附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e / Task 11

覆盖范围：
- M 循环 10 个科目全部有 note.main 规则
  - M3 库存股 section_by_template 只有 listed=五、56（国企无）
  - M1 与 L2/K3 共享章节 五、42 / 八、42（靠 table 名隔离）
  - M2~M10 多个非对称章节号
  - 全部权益类（account_code 4xxx），ending 取「期末余额」
- N 循环 5 个科目有 note.main 规则
  - N4 税金及附加 section_by_template 只有 listed=五、63（国企无）
  - N5 所得税费用上市侧走关键词章节 五、81 / 国企侧 八、78
  - N4/N5 损益类（account_code 6xxx），ending 取「本期发生额」
  - N1/N2 资产负债类，ending 取「期末余额」
- F 循环 4 个科目全部有 note.main 规则
  - F2 存货非对称章节号（listed 五、9 / soe 八、10）
  - F2 按「存货分类」表合计行写账面余额 / 跌价准备 / 账面价值（R6.1；不再逐码出行、把跌价准备当正数相加）
  - F1/F3/F4 对称章节号
  - 全部资产负债类，ending 取「期末余额」
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


def _note_rule(code: str) -> PushRule:
    """从 formula_push_rules.json 加载指定科目的 note.main 规则。"""
    rules = load_rules()
    return next(r for r in rules if r.rule_id == f"{code}.note.main")


def _has_note_main_rule(code: str) -> bool:
    """检查指定科目是否存在 note.main 规则。"""
    rules = load_rules()
    return any(r.rule_id == f"{code}.note.main" for r in rules)


def _make_tb(code: str, ending: str, opening: str, current: str = "0") -> dict:
    """构造单科目 TB 快照。"""
    return {
        code: {
            "期末余额": Decimal(ending),
            "年初余额": Decimal(opening),
            "本期发生额": Decimal(current),
        },
    }


def _make_multi_tb(codes: list[str], ending: str, opening: str, current: str = "0") -> dict:
    """构造多科目 TB 快照（每个科目同值）。"""
    result = {}
    for code in codes:
        result[code] = {
            "期末余额": Decimal(ending),
            "年初余额": Decimal(opening),
            "本期发生额": Decimal(current),
        }
    return result


def _load_sync_registry() -> list[dict]:
    """加载 note_workpaper_sync_registry.json。"""
    path = Path(__file__).resolve().parents[1] / "data" / "note_workpaper_sync_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("entries", data)


# ── 章节号真源（前端 *NoteSectionMap.ts 逐字提取） ───────────────────────────
#
# M 循环（股东权益）：
# M1 → 五、42 / 八、42（应付股利）— 对称，与 L2/K3 共享章节
# M2 → 五、53 / 八、58（实收资本）— 非对称
# M3 → 五、56 / None （库存股）— 只有 listed
# M4 → 五、55 / 八、60（资本公积）— 非对称
# M5 → 五、59 / 八、62（盈余公积）— 非对称
# M6 → 五、61 / 八、63（未分配利润）— 非对称
# M7 → 五、58 / 八、61（专项储备）— 非对称
# M8 → 五、60 / 八、94（一般风险准备）— 非对称
# M9 → 五、57 / 八、79（其他综合收益）— 非对称
# M10→ 五、54 / 八、59（其他权益工具）— 非对称
#
# N 循环（税费）：
# N1 → 五、30 / 八、31（递延所得税资产）— 非对称
# N2 → 五、41 / 八、41（应交税费）— 对称
# N3 → 无附注推送规则（递延所得税负债：注册表无 N3 章节，两版模板也没有同名表；原挂 五、22 / 八、22 固定资产，
#      spec note-pull-followup-closure R2.4 删）
# N4 → 五、63 / None （税金及附加）— 只有 listed，损益类
# N5 → 五、81 / 八、78（所得税费用）— 上市走关键词章节，损益类
#
# F 循环（存货/采购）：
# F1 → 五、7  / 八、7 （预付款项）— 对称
# F2 → 五、9  / 八、10（存货）— 非对称
# F3 → 五、36 / 八、36（应付票据）— 对称
# F4 → 五、37 / 八、37（应付账款）— 对称


# ========================================================================
# M 循环数据表
# ========================================================================

M_NOTE_SECTIONS = [
    ("M1",  "五、42", "八、42"),
    ("M2",  "五、53", "八、58"),
    # M3 只有 listed（单独测试）
    ("M4",  "五、55", "八、60"),
    ("M5",  "五、59", "八、62"),
    ("M6",  "五、61", "八、63"),
    ("M7",  "五、58", "八、61"),
    ("M8",  "五、60", "八、94"),
    ("M9",  "五、57", "八、79"),
    ("M10", "五、54", "八、59"),
]

#: M8 一般风险准备没有标准科目（m_cycle_specs 不给兜底码）⇒ 不取试算表、没有推送规则（原规则取 4301 专项储备，
#: spec formula-fetch-and-wp-generation-defect-closure R1.4 删）。前端同步登记表仍有它（附注同步与推送无关）。
M_NO_ACCOUNT_CODES = ["M8"]

#: 有推送规则的 M 科目（规则类用例的参数）
ALL_M_CODES = [c for c in ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10") if c not in M_NO_ACCOUNT_CODES]

#: 规则类用例的章节号参数（同步登记表用例仍用全量 M_NOTE_SECTIONS）
M_PUSH_NOTE_SECTIONS = [t for t in M_NOTE_SECTIONS if t[0] not in M_NO_ACCOUNT_CODES]

# M3 单独：section_by_template 只有 listed
M3_LISTED_SECTION = "五、56"

M_TABLE_EXPECTED = {
    "M1": "应付股利",
    "M2": "实收资本",
    "M3": "库存股",
    "M4": "资本公积",
    "M5": "盈余公积",
    "M6": "未分配利润",
    "M7": "专项储备",
    "M8": "一般风险准备",
    "M9": "其他综合收益",
    "M10": "其他权益工具",
}

#: 推送取数科目 = 口径单一来源 four_table/m_cycle_specs（真库科目表对账）。原表抄的是 wp_account_mapping.json 的错码，
#: M3~M10 整体错位一格（M3 写 4002 资本公积、M4 写 4101 盈余公积、M5 写 4103 本年利润、M7 写 4201 库存股、
#: M9 写 4401、M10 写不存在的 4501），推送把别的科目的数写进附注（R1.4）。
M_ACCOUNT_CODES = {
    "M1": "2232",
    "M2": "4001",
    "M3": "4201",
    "M4": "4002",
    "M5": "4101",
    "M6": "4104",
    "M7": "4301",
    "M9": "4003",
    "M10": "4401",
}

# M 循环非对称章节号科目（除 M1 对称、M3 只 listed 外全部非对称；M8 无推送规则）
M_ASYMMETRIC_CODES = ["M2", "M4", "M5", "M6", "M7", "M9", "M10"]


# ========================================================================
# N 循环数据表
# ========================================================================

N_NOTE_SECTIONS_DUAL = [
    ("N1", "五、30", "八、31"),
    ("N2", "五、41", "八、41"),
    # N3 无附注推送规则（见文件头）
    # N4 只有 listed（单独测试）
    # N5 上市走关键词（单独测试）
]

ALL_N_CODES = ["N1", "N2", "N4", "N5"]

N4_LISTED_SECTION = "五、63"
N5_LISTED_SECTION = "五、81"
N5_SOE_SECTION = "八、78"

N_TABLE_EXPECTED = {
    "N1": "递延所得税资产",
    "N2": "应交税费",
    "N3": "递延所得税负债",
    "N4": "税金及附加",
    "N5": "所得税费用",
}

N_ACCOUNT_CODES = {
    "N1": "1811",
    "N2": "2221",
    "N3": "2901",
    "N4": "6403",  # 损益类
    "N5": "6801",  # 损益类
}

# N 循环损益类科目（account_code 6 开头）
N_INCOME_CODES = ["N4", "N5"]
# N 循环资产负债类科目（有附注推送规则的）
N_BALANCE_CODES = ["N1", "N2"]


# ========================================================================
# F 循环数据表
# ========================================================================

F_NOTE_SECTIONS = [
    ("F1", "五、7",  "八、7"),
    ("F2", "五、9",  "八、10"),
    ("F3", "五、36", "八、36"),
    ("F4", "五、37", "八、37"),
]

ALL_F_CODES = ["F1", "F2", "F3", "F4"]

F_TABLE_EXPECTED = {
    "F1": "预付款项",
    "F2": "存货",
    "F3": "应付票据",
    "F4": "应付账款",
}

F_ACCOUNT_CODES = {
    "F1": "1123",
    "F2": ["1401", "1402", "1403", "1405", "1408", "1461"],  # 多科目码
    "F3": "2201",
    "F4": "2202",
}

# F2 是非对称章节号
F_ASYMMETRIC_CODES = ["F2"]
# F1/F3/F4 是对称章节号
F_SYMMETRIC_CODES = ["F1", "F3", "F4"]


# ========================================================================
# 合并全科目列表（方便参数化）
# ========================================================================

ALL_MNF_CODES = ALL_M_CODES + ALL_N_CODES + ALL_F_CODES


# ========================================================================
# █ M 循环测试
# ========================================================================


# ── M 章节号冻结映射 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", M_PUSH_NOTE_SECTIONS, ids=[t[0] for t in M_PUSH_NOTE_SECTIONS],
)
def test_m_note_rule_section_by_template(code: str, listed: str, soe: str):
    """M1/M2/M4~M7/M9/M10 章节号与前端 m*NoteSectionMap.ts 一致（双侧）。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


@pytest.mark.parametrize("code", M_NO_ACCOUNT_CODES, ids=M_NO_ACCOUNT_CODES)
def test_m_no_account_code_has_no_push_rule(code: str):
    """没有标准科目的 M 底稿：binding 不取科目且写明原因，规则清单里没有它的任何规则（取数 / 附注主表）。"""
    from app.services.formula_push.rules import load_rules

    binding = note_direct_for(code)
    assert binding.account_prefixes == ()
    assert binding.no_account_reason
    assert binding.derivations == frozenset()
    assert [r.rule_id for r in load_rules() if r.wp_code == code] == []


def test_m3_only_listed_section():
    """M3 库存股 section_by_template 只有 listed=五、56（国企无）。"""
    rule = _note_rule("M3")
    sections = rule.target.sections
    assert sections.get("listed") == M3_LISTED_SECTION
    assert "soe" not in sections, "M3 库存股国企无独立章节，不应有 soe 键"


# ── M 全科目字段统一验证 ────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_M_CODES, ids=ALL_M_CODES)
def test_m_note_rule_fields_are_end_and_prior(code: str):
    """M 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ── M policy = editable ─────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_M_CODES, ids=ALL_M_CODES)
def test_m_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _note_rule(code)
    assert rule.policy == "editable"


# ── M stage = note ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_M_CODES, ids=ALL_M_CODES)
def test_m_note_rule_stage_is_note(code: str):
    """note.main 规则的 stage 统一为 note。"""
    rule = _note_rule(code)
    assert rule.stage == "note"


# ── M rows 字段一致性 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_M_CODES, ids=ALL_M_CODES)
def test_m_note_rule_rows_naming(code: str):
    """M 科目 note.main 规则 rows 字段格式为 {code}_note_main（小写）。"""
    rule = _note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ── M 表名验证 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_M_CODES, ids=ALL_M_CODES)
def test_m_note_rule_table_name(code: str):
    """每个 M 科目表名正确。"""
    rule = _note_rule(code)
    assert rule.target.table == M_TABLE_EXPECTED[code]


# ── M1 与 L2/K3 共享章节验证 ────────────────────────────────────────────────

def test_m1_l2_k3_share_same_section():
    """M1、L2、K3 共用章节 五、42 / 八、42（互不覆盖由各自 table 名隔离）。"""
    r_m1 = _note_rule("M1")
    r_l2 = _note_rule("L2")
    r_k3 = _note_rule("K3")

    # 三者章节号完全相同
    assert r_m1.target.sections == r_l2.target.sections
    assert r_m1.target.sections == r_k3.target.sections

    # 但表名各不相同
    tables = {r_m1.target.table, r_l2.target.table, r_k3.target.table}
    assert len(tables) == 3, "M1/L2/K3 三者表名应互不相同"
    assert r_m1.target.table == "应付股利"
    assert r_l2.target.table == "应付利息"
    assert r_k3.target.table == "其他应付款"


# ── M 非对称章节号验证 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("code", M_ASYMMETRIC_CODES, ids=M_ASYMMETRIC_CODES)
def test_m_asymmetric_sections(code: str):
    """M2/M4~M10 上市/国企章节号数字部分不同（非对称）。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num != soe_num, f"{code} 上市/国企章节号数字部分应不同（非对称）"


def test_m1_symmetric_sections():
    """M1 上市/国企章节号数字部分相同（对称）。"""
    rule = _note_rule("M1")
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num == soe_num, "M1 上市/国企章节号数字部分应相同（对称）"


# ── M binding note_rows 资产负债类（权益类 4xxx） ────────────────────────────

@pytest.mark.parametrize(
    "code", ALL_M_CODES, ids=ALL_M_CODES,
)
def test_m_note_direct_note_rows_uses_ending_balance(code: str):
    """M1~M10 全部权益类: ending 取「期末余额」，opening 取「年初余额」。"""
    binding = note_direct_for(code)
    acct = M_ACCOUNT_CODES[code]
    binding._last_tb_data = _make_tb(acct, "800000", "600000", "200000")

    rule = _note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 800000.0, f"{code} ending 应取期末余额（权益类），非本期发生额"
    assert row["opening"] == 600000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == M_TABLE_EXPECTED[code]


# ========================================================================
# █ N 循环测试
# ========================================================================


# ── N 章节号冻结映射 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", N_NOTE_SECTIONS_DUAL, ids=[t[0] for t in N_NOTE_SECTIONS_DUAL],
)
def test_n_note_rule_section_by_template_dual(code: str, listed: str, soe: str):
    """N1/N2/N3 章节号与前端 n*NoteSectionMap.ts 一致（双侧）。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


def test_n4_only_listed_section():
    """N4 税金及附加 section_by_template 只有 listed=五、63（国企无）。"""
    rule = _note_rule("N4")
    sections = rule.target.sections
    assert sections.get("listed") == N4_LISTED_SECTION
    assert "soe" not in sections, "N4 税金及附加国企无独立章节，不应有 soe 键"


def test_n5_keyword_section_listed():
    """N5 所得税费用上市侧「五、81」：2026-10-16 按四版 Word 从会计政策章改挂到项目附注章
    （spec disclosure-note-template-word-realignment），种子登记的原关键词编号经别名解析到它。"""
    from app.services.note_section_catalog import normalize_section_code, template_json_path

    rule = _note_rule("N5")
    sections = rule.target.sections
    assert sections.get("listed") == N5_LISTED_SECTION == "五、81"
    seed = json.loads(template_json_path("listed").read_text(encoding="utf-8"))["sections"]
    olds = next(s for s in seed if s["section_number"] == "五、81").get("legacy_section_numbers") or []
    assert olds and {normalize_section_code(o, template_type="listed") for o in olds} == {"五、81"}


def test_n5_soe_section():
    """N5 所得税费用国企侧为常规章节 八、78。"""
    rule = _note_rule("N5")
    sections = rule.target.sections
    assert sections.get("soe") == N5_SOE_SECTION


# ── N 全科目字段统一验证 ────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_N_CODES, ids=ALL_N_CODES)
def test_n_note_rule_fields_are_end_and_prior(code: str):
    """N 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ── N policy = editable ─────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_N_CODES, ids=ALL_N_CODES)
def test_n_note_rule_policy_is_editable(code: str):
    rule = _note_rule(code)
    assert rule.policy == "editable"


# ── N stage = note ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_N_CODES, ids=ALL_N_CODES)
def test_n_note_rule_stage_is_note(code: str):
    rule = _note_rule(code)
    assert rule.stage == "note"


# ── N rows 字段一致性 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_N_CODES, ids=ALL_N_CODES)
def test_n_note_rule_rows_naming(code: str):
    rule = _note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ── N 表名验证 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_N_CODES, ids=ALL_N_CODES)
def test_n_note_rule_table_name(code: str):
    rule = _note_rule(code)
    assert rule.target.table == N_TABLE_EXPECTED[code]


# ── N1 非对称章节号验证 ─────────────────────────────────────────────────────

def test_n1_asymmetric_sections():
    """N1 递延所得税资产上市/国企章节号数字部分不同（非对称）。"""
    rule = _note_rule("N1")
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num != soe_num, "N1 上市/国企章节号数字部分应不同（非对称）"


def test_n2_symmetric_sections():
    """N2 应交税费上市/国企章节号数字部分相同（对称）。"""
    rule = _note_rule("N2")
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num == soe_num, "N2 上市/国企章节号数字部分应相同（对称）"


# ── N3 无附注推送规则 ────────────────────────────────────────────────────────

def test_n3_has_no_note_rule():
    """N3 递延所得税负债没有附注推送规则：注册表无 N3 章节、两版模板没有同名表；原规则挂 五、22 / 八、22（固定资产），
    标题校验永远不过（spec note-pull-followup-closure R2.4 删；判据 test_formula_push_note_rule_targets）。"""
    from app.services.formula_push.rules import load_rules

    assert [r.rule_id for r in load_rules() if r.wp_code == "N3" and r.stage == "note"] == []


# ── N1/N2 资产负债类 binding note_rows ──────────────────────────────────────

@pytest.mark.parametrize(
    "code,account_code,account_name",
    [("N1", "1811", "递延所得税资产"), ("N2", "2221", "应交税费")],
    ids=["N1", "N2"],
)
def test_n_balance_note_rows_uses_ending_balance(
    code: str, account_code: str, account_name: str,
):
    """N1/N2 资产负债类 note_rows: ending 取「期末余额」。"""
    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "450000", "300000", "150000")

    rule = _note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 450000.0, f"{code} ending 应取期末余额"
    assert row["opening"] == 300000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


# ── N4/N5 损益类 binding note_rows ──────────────────────────────────────────

@pytest.mark.parametrize(
    "code,account_code,account_name",
    [("N4", "6403", "税金及附加"), ("N5", "6801", "所得税费用")],
    ids=["N4", "N5"],
)
def test_n_income_note_rows_uses_current_amount(
    code: str, account_code: str, account_name: str,
):
    """N4/N5 损益类（6xxx）: ending 取「本期发生额」，opening 取「年初余额」。"""
    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "0", "200000", "350000")

    rule = _note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 350000.0, f"{code} 损益类应取本期发生额"
    assert row["opening"] == 200000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


# ========================================================================
# █ F 循环测试
# ========================================================================


# ── F 章节号冻结映射 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", F_NOTE_SECTIONS, ids=[t[0] for t in F_NOTE_SECTIONS],
)
def test_f_note_rule_section_by_template(code: str, listed: str, soe: str):
    """F1~F4 章节号与前端 f*NoteSectionMap.ts 一致。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ── F2 非对称章节号验证 ─────────────────────────────────────────────────────

def test_f2_asymmetric_sections():
    """F2 存货上市 五、9 / 国企 八、10（非对称章节号）。"""
    rule = _note_rule("F2")
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num != soe_num, "F2 上市/国企章节号数字部分应不同（非对称）"


# ── F1/F3/F4 对称章节号验证 ─────────────────────────────────────────────────

@pytest.mark.parametrize("code", F_SYMMETRIC_CODES, ids=F_SYMMETRIC_CODES)
def test_f_symmetric_sections(code: str):
    """F1/F3/F4 上市/国企章节号数字部分相同（对称）。"""
    rule = _note_rule(code)
    sections = rule.target.sections
    listed_num = sections["listed"].split("、")[1]
    soe_num = sections["soe"].split("、")[1]
    assert listed_num == soe_num, f"{code} 上市/国企章节号数字部分应相同（对称）"


# ── F 全科目字段统一验证 ────────────────────────────────────────────────────

@pytest.mark.parametrize("code", F_SYMMETRIC_CODES, ids=F_SYMMETRIC_CODES)
def test_f_note_rule_fields_are_end_and_prior(code: str):
    rule = _note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


def test_f2_note_rule_writes_book_value_columns_of_classification_table():
    """F2 主表规则写「存货分类」表合计行的六列（与底稿同步写入的列键一致），章节标题仍按「存货」校验。

    spec formula-fetch-followup-defect-closure R6.1：原规则只有期末 / 期初两个字段，三列分组表（账面余额 / 跌价准备 /
    账面价值）认不出列；国企、上市两个模板该表都叫「存货分类」，原表名「存货」建骨架找不到表。
    """
    from app.services.formula_push.bindings.note_direct import BOOK_VALUE_FIELDS

    rule = _note_rule("F2")
    assert rule.target.fields == BOOK_VALUE_FIELDS
    assert rule.target.table == "存货"
    assert rule.target.tables_by_template == {"listed": "存货分类", "soe": "存货分类"}
    # 原 subtable_0 与主表同表同字段、行源相同 ⇒ 已删，不得重复推送同一张表
    assert not [r for r in load_rules() if r.rule_id == "F2.note.subtable_0"]


# ── F policy = editable ─────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_F_CODES, ids=ALL_F_CODES)
def test_f_note_rule_policy_is_editable(code: str):
    rule = _note_rule(code)
    assert rule.policy == "editable"


# ── F stage = note ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_F_CODES, ids=ALL_F_CODES)
def test_f_note_rule_stage_is_note(code: str):
    rule = _note_rule(code)
    assert rule.stage == "note"


# ── F rows 字段一致性 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_F_CODES, ids=ALL_F_CODES)
def test_f_note_rule_rows_naming(code: str):
    rule = _note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ── F 表名验证 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_F_CODES, ids=ALL_F_CODES)
def test_f_note_rule_table_name(code: str):
    rule = _note_rule(code)
    assert rule.target.table == F_TABLE_EXPECTED[code]


# ── F1/F3/F4 资产负债类 binding note_rows（单科目码） ────────────────────────

@pytest.mark.parametrize(
    "code,account_code,account_name",
    [("F1", "1123", "预付款项"), ("F3", "2201", "应付票据"), ("F4", "2202", "应付账款")],
    ids=["F1", "F3", "F4"],
)
def test_f_single_code_note_rows_uses_ending_balance(
    code: str, account_code: str, account_name: str,
):
    """F1/F3/F4 单科目码资产负债类: ending 取「期末余额」。"""
    binding = note_direct_for(code)
    binding._last_tb_data = _make_tb(account_code, "700000", "500000", "200000")

    rule = _note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 700000.0, f"{code} ending 应取期末余额"
    assert row["opening"] == 500000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


# ── F2 账面价值口径 binding note_rows（只出合计行） ──────────────────────────
#
# 🔴 原两条用例断言「合计 = 6 个科目码之和」（含 1461 存货跌价准备按正数相加）——那正是要修的缺陷
# （spec formula-fetch-followup-defect-closure R6.1）。取数 / 归类的端到端见 test_formula_push_f2_note_book_value.py。

_F2_VALUES = {"found": True, "end_gross": 300.0, "end_impairment": 20.0, "end_net": 280.0,
              "prior_gross": 200.0, "prior_impairment": 10.0, "prior_net": 190.0}


def test_f2_note_rows_are_one_book_value_total_row():
    from app.services.formula_push.bindings.note_direct import BOOK_VALUE_FIELDS

    binding = note_direct_for("F2")
    binding._last_tb_data = _make_multi_tb(["1401", "1461"], "100000", "80000")
    binding._last_book_values = dict(_F2_VALUES)
    rows = binding.note_rows({}, "listed", _note_rule("F2"))
    assert len(rows) == 1
    row = rows[0]
    assert (row["note_label"], row["match_total"], row["is_total"]) == ("合计", True, False)
    assert {f: row[f] for f in BOOK_VALUE_FIELDS} == {f: _F2_VALUES[f] for f in BOOK_VALUE_FIELDS}
    assert all(row[f"{f}_resolved"] is True for f in BOOK_VALUE_FIELDS)
    # 子表规则不取试算表：不出行（原先逐码行的合计会被兜底写进子表合计行）
    for rule in (r for r in load_rules() if r.rule_id.startswith("F2.note.subtable_")):
        assert binding.note_rows({}, "listed", rule) == [], rule.rule_id


def test_f2_without_inventory_accounts_marks_all_fields_unresolved():
    binding = note_direct_for("F2")
    binding._last_tb_data = {}
    binding._last_book_values = {**_F2_VALUES, "found": False}
    row = binding.note_rows({}, "soe", _note_rule("F2"))[0]
    assert not any(v for k, v in row.items() if k.endswith("_resolved"))
    # 试算表不可用 ⇒ 不出行（与其他科目同）
    binding._last_tb_data = None
    assert binding.note_rows({}, "soe", _note_rule("F2")) == []


# ========================================================================
# █ 跨循环共性测试
# ========================================================================


# ── sync_registry 一致性（M 循环） ──────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", M_NOTE_SECTIONS, ids=[t[0] for t in M_NOTE_SECTIONS],
)
def test_m_sync_registry_matches_rule(code: str, listed: str, soe: str):
    """sync_registry 中 M 科目章节号与 note.main 规则一致。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == code), None)
    assert entry is not None, f"{code} 应在 sync_registry 中"
    assert entry.get("listed") == listed, f"{code} sync_registry listed"
    assert entry.get("soe") == soe, f"{code} sync_registry soe"


def test_m3_sync_registry_soe_is_none():
    """sync_registry 中 M3 soe 为 None。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == "M3"), None)
    assert entry is not None, "M3 应在 sync_registry 中"
    assert entry.get("listed") == M3_LISTED_SECTION
    assert entry.get("soe") is None, "M3 sync_registry soe 应为 None"


# ── sync_registry 一致性（N 循环） ──────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", N_NOTE_SECTIONS_DUAL, ids=[t[0] for t in N_NOTE_SECTIONS_DUAL],
)
def test_n_sync_registry_matches_rule(code: str, listed: str, soe: str):
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == code), None)
    assert entry is not None, f"{code} 应在 sync_registry 中"
    assert entry.get("listed") == listed
    assert entry.get("soe") == soe


def test_n4_sync_registry_soe_is_none():
    """sync_registry 中 N4 soe 为 None。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == "N4"), None)
    assert entry is not None, "N4 应在 sync_registry 中"
    assert entry.get("listed") == N4_LISTED_SECTION
    assert entry.get("soe") is None, "N4 sync_registry soe 应为 None"


def test_n5_sync_registry_keyword_section():
    """sync_registry 中 N5 listed 为关键词章节、soe 为常规章节。"""
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == "N5"), None)
    assert entry is not None, "N5 应在 sync_registry 中"
    assert entry.get("listed") == N5_LISTED_SECTION
    assert entry.get("soe") == N5_SOE_SECTION


# ── sync_registry 一致性（F 循环） ──────────────────────────────────────────

@pytest.mark.parametrize(
    "code,listed,soe", F_NOTE_SECTIONS, ids=[t[0] for t in F_NOTE_SECTIONS],
)
def test_f_sync_registry_matches_rule(code: str, listed: str, soe: str):
    entries = _load_sync_registry()
    entry = next((e for e in entries if e.get("wp_code") == code), None)
    assert entry is not None, f"{code} 应在 sync_registry 中"
    assert entry.get("listed") == listed
    assert entry.get("soe") == soe


# ── TB 不可用时全科目返回空行 ───────────────────────────────────────────────

@pytest.mark.parametrize("code", ALL_MNF_CODES, ids=ALL_MNF_CODES)
def test_mnf_note_direct_tb_unavailable_returns_empty(code: str):
    """TB 不可用时 note_direct binding 返回空行。"""
    binding = note_direct_for(code)
    binding._last_tb_data = None

    rule = _note_rule(code)
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []
