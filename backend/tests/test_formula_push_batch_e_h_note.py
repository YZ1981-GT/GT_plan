"""H 循环（H1~H10）附注规则验证 + note_rows 行为测试。

spec: formula-push-note-rollout-batch-e / Task 8

覆盖范围：
- H2/H3/H4 三个有 note.main 规则的科目：section_by_template / fields / policy / stage / rows naming / table name
- H2/H4 共用章节 五、23 / 八、23（在建工程 + 工程物资同一附注章节，靠 table 名隔离）
- H5 上市版无独立章节（listed=null / soe=八、25）——无 note.main 规则符合预期（需求 E5）
- H1/H5~H10 不存在 note.main 规则的确认
- H2/H3/H4 均为 balance_adj binding，资产负债类 ending 取「期末余额」
- H10 损益类（account_code='6115'）ending 取「本期发生额」（无 note.main 但 binding 行为正确）
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_push.rules import load_rules, PushRule
from app.services.formula_push.bindings.balance_adj import (
    BalanceAdjudicationBinding,
    binding_for as balance_adj_for,
)


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _h_note_rule(code: str) -> PushRule:
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


# ── 章节号真源（前端 *NoteSectionMap.ts 逐字提取） ──────────────────────────
#
# H2 → 五、23 / 八、23（在建工程）
# H3 → 五、21 / 八、21（投资性房地产）
# H4 → 五、23 / 八、23（工程物资，与 H2 共用章节）

H_NOTE_SECTIONS = [
    ("H2", "五、23", "八、23"),
    ("H3", "五、21", "八、21"),
    ("H4", "五、23", "八、23"),
]

ALL_H_NOTE_CODES = [t[0] for t in H_NOTE_SECTIONS]

# H 系列中没有 note.main 规则的科目
H_CODES_WITHOUT_NOTE = ["H1", "H5", "H6", "H7", "H8", "H9", "H10"]


# ========================================================================
# 章节号冻结映射
# ========================================================================


@pytest.mark.parametrize(
    "code,listed,soe", H_NOTE_SECTIONS, ids=[t[0] for t in H_NOTE_SECTIONS],
)
def test_h_note_rule_section_by_template(code: str, listed: str, soe: str):
    """每个有 note.main 的 H 科目章节号与前端 *NoteSectionMap.ts 一致。"""
    rule = _h_note_rule(code)
    sections = rule.target.sections
    assert sections.get("listed") == listed, f"{code} listed section"
    assert sections.get("soe") == soe, f"{code} soe section"


# ========================================================================
# 全科目字段统一验证
# ========================================================================


@pytest.mark.parametrize("code", ALL_H_NOTE_CODES, ids=ALL_H_NOTE_CODES)
def test_h_note_rule_fields_are_end_and_prior(code: str):
    """H 系列 note.main 一律使用 end_amount / prior_amount 双字段。"""
    rule = _h_note_rule(code)
    assert set(rule.target.fields) == {"end_amount", "prior_amount"}, f"{code} fields"


# ========================================================================
# policy = editable（附注不进独占集合，需求 E8）
# ========================================================================


@pytest.mark.parametrize("code", ALL_H_NOTE_CODES, ids=ALL_H_NOTE_CODES)
def test_h_note_rule_policy_is_editable(code: str):
    """附注规则 policy=editable（需求 E8：不进独占集合）。"""
    rule = _h_note_rule(code)
    assert rule.policy == "editable"


# ========================================================================
# stage = note
# ========================================================================


@pytest.mark.parametrize("code", ALL_H_NOTE_CODES, ids=ALL_H_NOTE_CODES)
def test_h_note_rule_stage_is_note(code: str):
    """note.main 规则的 stage 统一为 note。"""
    rule = _h_note_rule(code)
    assert rule.stage == "note"


# ========================================================================
# rows 字段一致性
# ========================================================================


@pytest.mark.parametrize("code", ALL_H_NOTE_CODES, ids=ALL_H_NOTE_CODES)
def test_h_note_rule_rows_naming(code: str):
    """H 科目 note.main 规则 rows 字段格式为 h{N}_note_main。"""
    rule = _h_note_rule(code)
    expected = f"{code.lower()}_note_main"
    assert rule.target.rows == expected, f"{code} rows should be {expected}"


# ========================================================================
# 表名验证
# ========================================================================


H_TABLE_EXPECTED = {
    "H2": "在建工程",
    "H3": "投资性房地产",
    "H4": "工程物资",
}


@pytest.mark.parametrize("code", ALL_H_NOTE_CODES, ids=ALL_H_NOTE_CODES)
def test_h_note_rule_table_name(code: str):
    """每个有 note.main 的 H 科目表名正确。"""
    rule = _h_note_rule(code)
    assert rule.target.table == H_TABLE_EXPECTED[code]


# ========================================================================
# H2/H4 共用章节验证
# ========================================================================


def test_h2_h4_share_same_section():
    """H2 和 H4 共用章节 五、23 / 八、23（互不覆盖由各自表名隔离）。"""
    r2 = _h_note_rule("H2")
    r4 = _h_note_rule("H4")
    assert r2.target.sections == r4.target.sections
    # 但表名不同
    assert r2.target.table != r4.target.table
    assert r2.target.table == "在建工程"
    assert r4.target.table == "工程物资"


# ========================================================================
# H5 上市版无独立章节（需求 E5）
# ========================================================================


def test_h5_no_note_main_rule():
    """H5 油气资产无 note.main 规则（上市版无独立章节，国企侧不由公式推送覆盖）。"""
    assert not _has_note_main_rule("H5"), "H5 不应有 note.main 规则"


def test_h5_listed_null_in_sync_registry():
    """note_workpaper_sync_registry.json 中 H5 的 listed 为 null，soe 为 八、25。"""
    import json
    from pathlib import Path

    registry_path = Path(__file__).resolve().parents[1] / "data" / "note_workpaper_sync_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry.get("entries", registry)  # 顶层可能是 {"entries": [...]} 或直接列表
    h5_entry = next((e for e in entries if e.get("wp_code") == "H5"), None)
    assert h5_entry is not None, "H5 应在 sync_registry 中"
    assert h5_entry.get("listed") is None, "H5 上市版应为 null（无独立油气资产附注章节）"
    assert h5_entry.get("soe") == "八、25", "H5 国企版章节号应为 八、25"


# ========================================================================
# 无 note.main 规则的 H 科目确认
# ========================================================================


@pytest.mark.parametrize("code", H_CODES_WITHOUT_NOTE, ids=H_CODES_WITHOUT_NOTE)
def test_h_code_without_note_main(code: str):
    """H1/H5~H10 不存在 note.main 规则（这些科目的附注推送不在当前规则集中）。"""
    assert not _has_note_main_rule(code), f"{code} 不应有 note.main 规则"


# ========================================================================
# balance_adj binding note_rows（H2/H3/H4 资产负债类）
# ========================================================================


# (code, account_code, account_name)
H_BALANCE_ADJ_NOTE_CODES = [
    ("H2", "1604", "在建工程"),
    ("H3", "1521", "投资性房地产"),
    ("H4", "1605", "工程物资"),
]


@pytest.mark.parametrize(
    "code,account_code,account_name",
    H_BALANCE_ADJ_NOTE_CODES,
    ids=[t[0] for t in H_BALANCE_ADJ_NOTE_CODES],
)
def test_h_balance_adj_note_rows_uses_ending_balance(
    code: str, account_code: str, account_name: str,
):
    """H2/H3/H4 资产负债类 note_rows: ending 取「期末余额」，opening 取「年初余额」。"""
    binding = balance_adj_for(code)
    binding._last_tb_data = _make_tb(account_code, "500000", "350000", "150000")

    rule = _h_note_rule(code)
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 500000.0, "ending 应取期末余额，非本期发生额"
    assert row["opening"] == 350000.0
    assert row["ending_resolved"] is True
    assert row["opening_resolved"] is True
    assert row["is_total"] is False
    assert row["label"] == account_name


def test_h_balance_adj_tb_unavailable_returns_empty():
    """TB 不可用时 balance_adj binding 返回空行。"""
    binding = balance_adj_for("H2")
    binding._last_tb_data = None

    rule = _h_note_rule("H2")
    rows = binding.note_rows({}, "listed", rule)
    assert rows == []


# ========================================================================
# H10 损益类 binding 行为（无 note.main 但 binding note_rows 可用）
# ========================================================================


def test_h10_is_income_type_uses_current_amount():
    """H10 资产处置损益（损益类 6115）: ending 取「本期发生额」，opening 取「年初余额」。"""
    binding = balance_adj_for("H10")
    binding._last_tb_data = _make_tb("6115", "0", "200000", "300000")

    # H10 无 note.main 规则，直接测 binding 行为（用 G 循环同类损益科目的 note_rows 签名）
    # balance_adj note_rows 需要 rule 参数，但主要用于选行。
    # 这里用 H2 的 rule 做代理（仅测 TB 取数逻辑，不验证章节号）
    rule = _h_note_rule("H2")
    rows = binding.note_rows({}, "listed", rule)

    assert len(rows) == 1
    row = rows[0]
    assert row["ending"] == 300000.0, "损益类应取本期发生额"
    assert row["opening"] == 200000.0
    assert row["ending_resolved"] is True


# ========================================================================
# H1 多科目码 note_rows 行为（1601/1602/1603 → 3 行 + 1 合计行）
# ========================================================================


def test_h1_multi_code_note_rows_produces_total():
    """H1 固定资产有 3 个 account_codes，note_rows 应产生 3 行数据 + 1 行合计。"""
    binding = balance_adj_for("H1")
    binding._last_tb_data = {
        "1601": {"期末余额": Decimal("100000"), "年初余额": Decimal("80000"), "本期发生额": Decimal("20000")},
        "1602": {"期末余额": Decimal("50000"), "年初余额": Decimal("40000"), "本期发生额": Decimal("10000")},
        "1603": {"期末余额": Decimal("30000"), "年初余额": Decimal("20000"), "本期发生额": Decimal("10000")},
    }

    # H1 无 note.main 规则，借 H2 的 rule 做代理（仅测 TB 取数 + 合计逻辑）
    rule = _h_note_rule("H2")
    rows = binding.note_rows({}, "listed", rule)

    # 3 个数据行 + 1 个合计行
    assert len(rows) == 4
    data_rows = [r for r in rows if not r["is_total"]]
    total_rows = [r for r in rows if r["is_total"]]
    assert len(data_rows) == 3
    assert len(total_rows) == 1

    # 合计行 ending = 100000 + 50000 + 30000 = 180000
    assert total_rows[0]["ending"] == 180000.0
    assert total_rows[0]["opening"] == 140000.0  # 80000 + 40000 + 20000
    assert total_rows[0]["label"] == "固定资产"
