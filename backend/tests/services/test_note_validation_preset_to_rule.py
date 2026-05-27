"""Sprint 4 Task 4.1 — PRESET_TO_RULE 接入 NoteValidationEngine 单测.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.1
Reqs:   R3.x（check_presets / _validation_rules 接入引擎）

覆盖：
1. PRESET_TO_RULE 字典完整性（11 个枚举全部命中）
2. resolve_rule_from_preset 命中 / 描述 / 未识别 / None / 空串
3. 11 枚举每个走 ``execute_inline_rules`` 至少 2 路径（命中 + 未识别兜底）
4. ``execute_all`` 优先走 inline 路径并不重复执行 preset.md
5. 多表 _tables / 旧 _check_presets 兼容

总用例数 ≥ 22（11 枚举 × 2 + 描述类专项 + 未识别兜底）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.services.note_validation_engine import (
    PRESET_TO_RULE,
    NoteValidationEngine,
    ValidationContext,
    ValidationType,
    resolve_rule_from_preset,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ALL_11_PRESETS: list[str] = [
    "余额",
    "宽表",
    "纵向",
    "交叉",
    "跨科目",
    "其中项",
    "二级明细",
    "完整性",
    "账龄衔接",
    "LLM审核",
    "描述",
]


# ---------------------------------------------------------------------------
# 1. 字典完整性
# ---------------------------------------------------------------------------


class TestPresetToRuleDictCoverage:
    """PRESET_TO_RULE 必须严格覆盖 11 个枚举（CI 卡点）."""

    def test_dict_has_exactly_11_entries(self):
        assert len(PRESET_TO_RULE) == 11, (
            f"PRESET_TO_RULE 必须严格 11 项，当前 {len(PRESET_TO_RULE)} 项"
        )

    def test_all_11_keys_present(self):
        missing = [k for k in ALL_11_PRESETS if k not in PRESET_TO_RULE]
        assert not missing, f"PRESET_TO_RULE 缺枚举: {missing}"

    def test_no_extra_keys(self):
        extra = [k for k in PRESET_TO_RULE if k not in ALL_11_PRESETS]
        assert not extra, f"PRESET_TO_RULE 含未授权枚举: {extra}"

    def test_description_maps_to_skip(self):
        assert PRESET_TO_RULE["描述"] == "SKIP"

    def test_all_codes_are_uppercase_snake(self):
        for code in PRESET_TO_RULE.values():
            assert code.isupper() or code == "SKIP", (
                f"rule code 必须全大写: {code}"
            )

    def test_balance_code(self):
        assert PRESET_TO_RULE["余额"] == "BALANCE_TIE"

    def test_aging_code(self):
        assert PRESET_TO_RULE["账龄衔接"] == "AGING_PROGRESSION"


# ---------------------------------------------------------------------------
# 2. resolve_rule_from_preset 三态语义
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset,expected", [
    ("余额", "BALANCE_TIE"),
    ("宽表", "WIDE_TABLE_HORIZONTAL"),
    ("纵向", "VERTICAL_CARRY"),
    ("交叉", "CROSS_TABLE_TIE"),
    ("跨科目", "CROSS_ACCOUNT_TIE"),
    ("其中项", "WHEREOF_SUM"),
    ("二级明细", "DETAIL_LEVEL2_TIE"),
    ("完整性", "ROW_COMPLETENESS"),
    ("账龄衔接", "AGING_PROGRESSION"),
    ("LLM审核", "LLM_SEMANTIC_REVIEW"),
])
def test_resolve_hits_for_each_executable_preset(preset: str, expected: str):
    """10 个可执行 preset（除"描述"外）的命中路径."""
    assert resolve_rule_from_preset(preset) == expected


def test_resolve_description_returns_none():
    assert resolve_rule_from_preset("描述") is None


def test_resolve_unknown_returns_none():
    assert resolve_rule_from_preset("不存在的预设") is None


def test_resolve_empty_returns_none():
    assert resolve_rule_from_preset("") is None


def test_resolve_none_returns_none():
    assert resolve_rule_from_preset(None) is None  # type: ignore[arg-type]


def test_resolve_strips_whitespace():
    assert resolve_rule_from_preset("  余额  ") == "BALANCE_TIE"


# ---------------------------------------------------------------------------
# 3. 11 枚举 × 2 路径（命中执行 + 未识别兜底）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset", [p for p in ALL_11_PRESETS if p != "描述"])
def test_inline_rule_factory_produces_rule_for_each_executable_preset(preset: str):
    """每个可执行 preset 经 ``rules_from_inline_presets`` 至少产生 1 条规则."""
    engine = NoteValidationEngine(db=None)
    rules = engine.rules_from_inline_presets("八、X1", [preset])
    assert len(rules) == 1, f"{preset} 应产生 1 条规则"
    assert rules[0].section_code == "八、X1"
    assert rules[0].metadata["preset"] == preset
    assert rules[0].metadata["rule_code"] == PRESET_TO_RULE[preset]


@pytest.mark.parametrize("preset", [p for p in ALL_11_PRESETS if p != "描述"])
def test_inline_rule_executes_without_exception(preset: str):
    """每个可执行 preset 走 ``execute_inline_rules`` 全链路必须不抛异常."""
    engine = NoteValidationEngine(db=None)
    table_data = {
        "headers": ["项目", "期末", "期初"],
        "rows": [
            {"label": "库存现金", "amount": 100, "values": [100, 80]},
            {"label": "合计", "amount": 100, "is_total": True, "values": [100, 80]},
        ],
        "_validation_rules": [preset],
    }
    ctx = ValidationContext(
        project_id=uuid4(),
        year=2024,
        note_data={"五、1 货币资金": table_data},
        report_data={"五、1 货币资金": Decimal("100")},
    )
    results = engine.execute_inline_rules("五、1 货币资金", table_data, ctx)
    assert len(results) == 1
    # 引擎对 stub executor / unknown 不阻断（passed=True 默认），但具体结果由各 executor 决定
    assert results[0].rule_type  # 必有 rule_type 字符串


def test_description_preset_skipped_in_inline():
    """"描述" 类不产生规则，``execute_inline_rules`` 返回空列表."""
    engine = NoteValidationEngine(db=None)
    table_data = {"_validation_rules": ["描述"]}
    ctx = ValidationContext(project_id=uuid4(), year=2024)
    results = engine.execute_inline_rules("八、X1", table_data, ctx)
    assert results == []


def test_unknown_preset_skipped_in_inline():
    """未识别 preset 不产生规则，与"描述" 行为一致."""
    engine = NoteValidationEngine(db=None)
    table_data = {"_validation_rules": ["foo_bar_unknown"]}
    ctx = ValidationContext(project_id=uuid4(), year=2024)
    results = engine.execute_inline_rules("八、X1", table_data, ctx)
    assert results == []


def test_mixed_known_and_unknown_keeps_known():
    """混合已知 + 未知：仅已知的产生规则."""
    engine = NoteValidationEngine(db=None)
    table_data = {"_validation_rules": ["余额", "描述", "foo", "纵向"]}
    ctx = ValidationContext(
        project_id=uuid4(),
        year=2024,
        note_data={"八、X1": table_data},
    )
    results = engine.execute_inline_rules("八、X1", table_data, ctx)
    assert len(results) == 2  # 余额 + 纵向（描述/foo 跳过）
    rule_types = {r.rule_type for r in results}
    assert rule_types == {ValidationType.BALANCE.value, ValidationType.VERTICAL.value}


# ---------------------------------------------------------------------------
# 4. 多表 _tables[i]._validation_rules 派发
# ---------------------------------------------------------------------------


def test_collect_rules_from_multi_tables():
    engine = NoteValidationEngine(db=None)
    table_data: dict[str, Any] = {
        "_tables": [
            {"_validation_rules": ["余额", "纵向"]},
            {"_validation_rules": ["其中项"]},
            {"_validation_rules": ["描述"]},  # 整表跳过
        ],
    }
    rules = engine.collect_inline_rules_for_note("八、固定资产", table_data)
    assert len(rules) == 3  # 余额 + 纵向 + 其中项
    table_indexes = sorted(r.metadata["table_index"] for r in rules)
    assert table_indexes == [0, 0, 1]


def test_collect_rules_from_legacy_check_presets_field():
    """兼容旧字段 _check_presets（不带 table_index）."""
    engine = NoteValidationEngine(db=None)
    table_data: dict[str, Any] = {
        "_check_presets": ["余额", "其中项"],
    }
    rules = engine.collect_inline_rules_for_note("五、1 货币资金", table_data)
    assert len(rules) == 2
    rule_types = {r.rule_type for r in rules}
    assert rule_types == {ValidationType.BALANCE.value, ValidationType.SUB_ITEM.value}


def test_collect_rules_combines_all_paths():
    """顶层 + _tables + _check_presets 三路合并."""
    engine = NoteValidationEngine(db=None)
    table_data: dict[str, Any] = {
        "_validation_rules": ["余额"],
        "_tables": [{"_validation_rules": ["纵向"]}],
        "_check_presets": ["完整性"],
    }
    rules = engine.collect_inline_rules_for_note("八、X1", table_data)
    rule_types = sorted(r.rule_type for r in rules)
    assert rule_types == sorted([
        ValidationType.BALANCE.value,
        ValidationType.VERTICAL.value,
        ValidationType.COMPLETENESS.value,
    ])


def test_collect_rules_handles_missing_table_data():
    engine = NoteValidationEngine(db=None)
    assert engine.collect_inline_rules_for_note("X", None) == []
    assert engine.collect_inline_rules_for_note("X", {}) == []
    assert engine.collect_inline_rules_for_note("X", {"foo": "bar"}) == []


def test_collect_rules_ignores_non_list_validation_rules():
    """``_validation_rules`` 非 list 时安全跳过."""
    engine = NoteValidationEngine(db=None)
    rules = engine.collect_inline_rules_for_note(
        "X", {"_validation_rules": "not a list"}
    )
    assert rules == []


# ---------------------------------------------------------------------------
# 5. execute_all 集成路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_all_prefers_inline_over_preset_md():
    """``execute_all`` 在章节含 _validation_rules 时不重复跑 preset.md."""
    engine = NoteValidationEngine(db=None)
    # 强制 cache 为空（确保不读真实 preset 文件）
    engine._rules_cache["soe"] = []  # type: ignore[attr-defined]

    table_data = {
        "headers": ["项目", "期末"],
        "rows": [
            {"label": "现金", "amount": 100, "values": [100]},
            {"label": "合计", "amount": 100, "is_total": True, "values": [100]},
        ],
        "_validation_rules": ["余额", "纵向"],
    }
    ctx = ValidationContext(
        project_id=uuid4(),
        year=2024,
        note_data={"五、1 货币资金": table_data},
    )
    results = await engine.execute_all(uuid4(), 2024, "soe", ctx)
    assert len(results) == 2
    types = sorted(r.rule_type for r in results)
    assert types == sorted([
        ValidationType.BALANCE.value,
        ValidationType.VERTICAL.value,
    ])


@pytest.mark.asyncio
async def test_execute_all_fallback_to_preset_md_when_no_inline():
    """无 _validation_rules 时降级到 preset.md (cache empty → 0 results)."""
    engine = NoteValidationEngine(db=None)
    engine._rules_cache["soe"] = []  # type: ignore[attr-defined]
    ctx = ValidationContext(
        project_id=uuid4(),
        year=2024,
        note_data={"五、1 货币资金": {"headers": [], "rows": []}},
    )
    results = await engine.execute_all(uuid4(), 2024, "soe", ctx)
    assert results == []
