"""附注中文预设名去处 + 旧生成器不覆盖结构预设 + 覆盖率同口径（spec note-pull-followup-closure R8）。

- 两版单体模板出现的每个中文预设名都是 ``PRESET_TO_RULE`` 的键；生成附注时注入 ``_validation_rules`` 的白名单由它派生
  （原先另写一份 11 项、缺「期间衔接」，未分配利润两章的该项被静默丢弃）。
- 「期间衔接」执行器：本期列期初 = 上期列期末；有上年附注时上期列期末 = 上年本期列期末；空格不比、认不出结构 skip。
- ``section_preset_formulas``：旧生成器只补明细行取数公式，同目标以按结构生成的为准，``_check_presets`` 的英文预设名
  不再传给它（原先不分段的求和覆盖按结构生成的合计）；比例列不取数。
- ``compute_formula_coverage`` 与执行器同一套预设（全部表、金额列）。
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.disclosure_engine import _VALID_VALIDATION_PRESETS, _resolve_check_roles
from app.services.note_formula_generator import compute_formula_coverage
from app.services.note_formula_tables import section_preset_formulas, table_preset_formulas
from app.services.note_validation_engine import (
    PRESET_TO_RULE,
    NoteValidationEngine,
    ValidationContext,
    ValidationRule,
    ValidationType,
)
from app.services.note_validation_executors import EXECUTORS, _execute_period_continuity

DATA = Path(__file__).resolve().parents[1] / "data"
UNAPPROPRIATED = {"soe": "八、63", "listed": "五、61"}


def _template(tt: str) -> dict:
    return json.loads((DATA / f"note_template_{tt}.json").read_text(encoding="utf-8"))


def _section(tt: str, number: str) -> dict:
    return next(s for s in _template(tt)["sections"] if s.get("section_number") == number)


# ── 预设名去处 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_note_preset_names_have_destination(tt):
    names = set()
    for sec in _template(tt)["sections"]:
        for key in ("check_presets", "check_roles"):
            names.update(x.strip() for x in sec.get(key) or [] if isinstance(x, str))
    assert names, "模板里读到了预设名（判据不空转）"
    assert names <= set(PRESET_TO_RULE), f"模板预设名没有去处：{sorted(names - set(PRESET_TO_RULE))}"
    assert "期间衔接" in names


def test_injection_whitelist_is_preset_to_rule():
    assert _VALID_VALIDATION_PRESETS == frozenset(PRESET_TO_RULE)


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_unappropriated_profit_gets_period_continuity(tt):
    roles = _resolve_check_roles(_section(tt, UNAPPROPRIATED[tt]))
    assert "期间衔接" in roles
    rules = NoteValidationEngine().rules_from_inline_presets(UNAPPROPRIATED[tt], ["期间衔接"])
    assert [r.rule_type for r in rules] == [ValidationType.PERIOD_CONTINUITY]
    assert EXECUTORS[ValidationType.PERIOD_CONTINUITY] is _execute_period_continuity


# ── 期间衔接执行器（真模板结构） ─────────────────────────────────────────────


def _table(tt: str, opening_current, closing_prior, closing_current=None) -> dict:
    table = copy.deepcopy(_section(tt, UNAPPROPRIATED[tt])["tables"][0])
    width = len(table["headers"]) - 1
    rows = []
    for i, row in enumerate(table["rows"]):
        values = [None] * width
        if i == 0:
            values[0] = opening_current
        if i == len(table["rows"]) - 1:
            values[0], values[1] = closing_current, closing_prior
        rows.append({"label": row["label"], "values": values})
    return {"headers": table["headers"], "rows": rows}


def _run(tt: str, td: dict, prior: dict | None = None):
    section = UNAPPROPRIATED[tt]
    ctx = ValidationContext(note_data={section: td}, prior_note_data={section: prior} if prior else {})
    rule = ValidationRule(section_code=section, rule_type=ValidationType.PERIOD_CONTINUITY, expression="preset:期间衔接")
    return NoteValidationEngine(None).execute_rule(rule, ctx)


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_period_continuity_within_table(tt):
    ok = _run(tt, _table(tt, 1000, "1,000.00"))
    assert ok.passed and ok.details["compared"] == ["本期期初 = 上期期末"], ok.details
    bad = _run(tt, _table(tt, 1000, 900))
    assert not bad.passed and bad.diff_amount == Decimal("100")
    assert bad.details["issues"][0]["left"] == 1000.0 and bad.details["issues"][0]["right"] == 900.0
    blank = _run(tt, _table(tt, 1000, None))
    assert blank.passed and blank.details.get("skipped") and blank.details["compared"] == [], "空格不比（宁漏报不误报）"


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_period_continuity_against_prior_year_note(tt):
    prior = _table(tt, 800, 700, closing_current=900)
    ok = _run(tt, _table(tt, 900, 900), prior)
    assert ok.passed and ok.details["compared"] == ["本期期初 = 上期期末", "上期期末 = 上年附注本期期末"]
    bad = _run(tt, _table(tt, 950, 950), prior)
    assert not bad.passed and [i["check"] for i in bad.details["issues"]] == ["上期期末 = 上年附注本期期末"]


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_period_continuity_finds_rows_by_label_not_position(tt):
    """期初 / 期末行按行名认（表首多一行说明、期末行后还有「其中」行时不认错行）。"""
    td = _table(tt, 1000, 1000)
    width = len(td["headers"]) - 1
    td["rows"].insert(0, {"label": "未分配利润变动", "values": [5] * width})
    td["rows"].append({"label": "其中：子公司当年提取的盈余公积归属于母公司的金额", "values": [7] * width})
    result = _run(tt, td)
    assert result.passed and result.details["compared"] == ["本期期初 = 上期期末"], result.details
    assert result.details["opening_label"] != "未分配利润变动" and not result.details["closing_label"].startswith("其中")


def test_period_continuity_skips_unknown_structure():
    td = {"headers": ["项目", "期末余额", "期初余额"], "rows": [{"label": "库存现金", "values": [1, 2]}]}
    result = _run("soe", td)
    assert result.passed and result.details["skipped"] and "认不出" in result.details["reason"]


# ── 旧生成器不覆盖结构预设 ────────────────────────────────────────────────────

HEADERS = ["项目", "期末余额", "期初余额"]


def _r(label, **kw):
    return {"label": label, "values": [None, None], **kw}


def test_legacy_sums_no_longer_override_structure_presets():
    td = {"headers": HEADERS, "_check_presets": ["sub_item", "balance", "movement", "book_value"], "rows": [
        _r("1年以内"), _r("1至2年"), _r("小计", row_type="subtotal", is_total=True), _r("减：坏账准备"),
        _r("合计", row_type="total", is_total=True)]}
    formulas, _notes = section_preset_formulas(td)
    structure, _ = table_preset_formulas(td, 0)
    assert formulas == structure, "英文预设名不再生成公式，同目标以结构为准"
    assert formulas["4:0"]["expression"] == "cell(2,0) - cell(3,0)", "合计 = 小计 − 坏账准备（旧求和 = 坏账准备本身）"
    ambiguous = {"headers": HEADERS, "_check_presets": ["sub_item"], "rows": [
        _r("交易性金融负债"), _r("其中：发行的交易性债券"), _r("其他"), _r("合计", is_total=True)]}
    assert section_preset_formulas(ambiguous)[0] == {}, "判不准的合计不由旧生成器补一条不分段的求和"


def test_legacy_detail_fetch_formulas_kept_but_structure_wins_and_ratio_columns_skipped():
    td = {"headers": ["项目", "期末余额", "期末比例(%)"], "rows": [
        _r("库存现金", account_codes=["1001"]), _r("银行存款", account_codes=["1002"]),
        # 只标 row_type 的合计行：旧生成器只认 is_total ⇒ 会给它出一条 TB 取数公式，与结构预设撞目标
        _r("合计", row_type="total", account_codes=["1001", "1002"])]}
    formulas, _ = section_preset_formulas(td)
    assert formulas["0:0"]["expression"] == "TB('1001','期末')" and formulas["0:0"]["source"] == "account_codes"
    assert "0:1" not in formulas and "1:1" not in formulas, "比例列不取数"
    assert formulas["2:0"]["source"] == "preset.total" and formulas["2:0"]["expression"] == "SUM(0:1, 0)", (
        "同一目标以按结构生成的为准")


# ── 覆盖率与执行器同一套预设 ────────────────────────────────────────────────


def test_coverage_counts_presets_of_every_table():
    first = {"name": "甲", "headers": HEADERS, "rows": [_r("库存现金"), _r("银行存款"), _r("合计", is_total=True)]}
    second = {"name": "乙", "headers": HEADERS + ["比例(%)"], "rows": [
        {"label": "保证金", "values": [None] * 3}, {"label": "其中：境外", "values": [None] * 3},
        {"label": "合计", "is_total": True, "values": [None] * 3}]}
    td = {"_tables": [first, second], "_check_presets": ["sub_item"]}
    stats = compute_formula_coverage(td)
    # 甲：3 行 × 2 金额列，合计 2 格；乙：3 行 × 2 金额列（比例列不计），合计判不准（其中）0 格
    assert stats == {"total_cells": 12, "configured_cells": 2, "coverage_pct": round(2 * 100 / 12, 1)}
    formulas, _ = section_preset_formulas(td)
    assert set(formulas) == {"2:0", "2:1"}, "覆盖率数的就是执行器会算的那几格"
