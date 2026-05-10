"""F48 / Sprint 8.10: 校验规则目录 catalog 与 validator.py 双向一致性。

不变量（对齐 design §D12.2 + requirements F48）：

1. ``VALIDATION_RULES_CATALOG`` 中的每条 ``ValidationRuleDoc``
   都能在 ``validator.py`` 源码里作为 ``code="..."`` 字面量出现
   （即 validator 真的会 emit 这个 code）。
2. ``validator.py`` 里每个 ``code="..."`` 字面量都在 catalog 中有条目
   （catalog 不能落下任何真实会产生的 finding）。
3. 每条条目的必填元数据（``title_cn`` / ``formula_cn`` / ``why_cn`` /
   ``scope_cn``）非空；带容差的规则 ``tolerance_formula`` + ``tolerance_cn``
   成对出现。
4. ``get_rule_by_code`` 对存在的 code 返回对应条目，未知 code 返回 None。
5. code 全局唯一。
6. ``level`` / ``severity`` 与 validator 里的 level / severity 字段对齐
   （在已知 mapping 里交叉验证）。

不覆盖的 code（已由 ``error_hints.py`` 承担 user-facing 文案，不属本 catalog）：
上传/detect 阶段 fatal 码、F42 规模警告、AI fallback / history mapping info 码。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.ledger_import.validation_rules_catalog import (
    VALIDATION_RULES_CATALOG,
    ValidationRuleDoc,
    get_rule_by_code,
)

VALIDATOR_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "ledger_import"
    / "validator.py"
)


def _extract_codes_from_validator() -> set[str]:
    """从 validator.py 源码里抓所有 ``code="..."`` 字面量。

    只抓 ``ValidationFinding(code=...)`` 风格的字面量，忽略变量拼接。
    """
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    # 匹配 `code="XXX"` 或 `code='XXX'`
    pattern = re.compile(r"\bcode\s*=\s*[\"']([A-Z][A-Z0-9_]+)[\"']")
    return set(pattern.findall(source))


# ---------------------------------------------------------------------------
# 基本形式
# ---------------------------------------------------------------------------


class TestCatalogShape:
    def test_all_entries_are_validation_rule_doc(self):
        assert all(
            isinstance(rule, ValidationRuleDoc) for rule in VALIDATION_RULES_CATALOG
        )

    def test_catalog_is_non_empty(self):
        assert len(VALIDATION_RULES_CATALOG) > 0

    def test_codes_are_unique(self):
        codes = [r.code for r in VALIDATION_RULES_CATALOG]
        assert len(codes) == len(set(codes)), (
            f"catalog 中有重复 code: {[c for c in codes if codes.count(c) > 1]}"
        )

    def test_required_fields_non_empty(self):
        """title_cn / formula_cn / why_cn / scope_cn 必须非空。"""
        for rule in VALIDATION_RULES_CATALOG:
            assert rule.title_cn.strip(), f"{rule.code} title_cn 为空"
            assert rule.formula_cn.strip(), f"{rule.code} formula_cn 为空"
            assert rule.why_cn.strip(), f"{rule.code} why_cn 为空"
            assert rule.scope_cn.strip(), f"{rule.code} scope_cn 为空"

    def test_tolerance_fields_consistency(self):
        """tolerance_formula 与 tolerance_cn 要么同时为 None，要么同时非空。"""
        for rule in VALIDATION_RULES_CATALOG:
            has_formula = bool(rule.tolerance_formula)
            has_cn = bool(rule.tolerance_cn)
            assert has_formula == has_cn, (
                f"{rule.code} tolerance_formula / tolerance_cn "
                f"不一致：({rule.tolerance_formula!r}, {rule.tolerance_cn!r})"
            )

    def test_level_values_valid(self):
        for rule in VALIDATION_RULES_CATALOG:
            assert rule.level in ("L1", "L2", "L3")

    def test_severity_values_valid(self):
        for rule in VALIDATION_RULES_CATALOG:
            assert rule.severity in ("blocking", "warning")


# ---------------------------------------------------------------------------
# 双向一致性（catalog ↔ validator.py）
# ---------------------------------------------------------------------------


class TestBidirectionalConsistency:
    """catalog 与 validator.py 源码双向匹配。"""

    def test_every_catalog_code_appears_in_validator(self):
        """catalog 中每条 code 必须在 validator.py 源码里出现。"""
        catalog_codes = {r.code for r in VALIDATION_RULES_CATALOG}
        validator_codes = _extract_codes_from_validator()
        missing_in_validator = catalog_codes - validator_codes
        assert not missing_in_validator, (
            f"以下 code 在 catalog 但 validator.py 没有对应 emit 位置：\n"
            f"{sorted(missing_in_validator)}"
        )

    def test_every_validator_code_appears_in_catalog(self):
        """validator.py 里每个 emit 的 code 必须在 catalog 有条目。"""
        catalog_codes = {r.code for r in VALIDATION_RULES_CATALOG}
        validator_codes = _extract_codes_from_validator()
        missing_in_catalog = validator_codes - catalog_codes
        assert not missing_in_catalog, (
            f"以下 code 在 validator.py 但 catalog 未登记：\n"
            f"{sorted(missing_in_catalog)}\n"
            f"新增 finding code 时必须同步更新 validation_rules_catalog.py"
        )


# ---------------------------------------------------------------------------
# level / severity 交叉验证（与 validator.py 里已知的分级对齐）
# ---------------------------------------------------------------------------


# 期望的 level 映射（来自 validator.py 源码观察）
_EXPECTED_LEVEL: dict[str, str] = {
    "AMOUNT_NOT_NUMERIC_KEY": "L1",
    "AMOUNT_NOT_NUMERIC_RECOMMENDED": "L1",
    "DATE_INVALID_KEY": "L1",
    "DATE_INVALID_RECOMMENDED": "L1",
    "ROW_SKIPPED_KEY_EMPTY": "L1",
    "BALANCE_UNBALANCED": "L2",
    "L2_LEDGER_YEAR_OUT_OF_RANGE": "L2",
    "ACCOUNT_NOT_IN_CHART": "L2",
    "BALANCE_LEDGER_MISMATCH": "L3",
    "AUX_ACCOUNT_MISMATCH": "L3",
}


# 期望的 severity 映射
_EXPECTED_SEVERITY: dict[str, str] = {
    "AMOUNT_NOT_NUMERIC_KEY": "blocking",
    "AMOUNT_NOT_NUMERIC_RECOMMENDED": "warning",
    "DATE_INVALID_KEY": "blocking",
    "DATE_INVALID_RECOMMENDED": "warning",
    "ROW_SKIPPED_KEY_EMPTY": "warning",
    "BALANCE_UNBALANCED": "blocking",
    "L2_LEDGER_YEAR_OUT_OF_RANGE": "blocking",
    "ACCOUNT_NOT_IN_CHART": "blocking",
    "BALANCE_LEDGER_MISMATCH": "blocking",
    "AUX_ACCOUNT_MISMATCH": "warning",
}


@pytest.mark.parametrize(
    "code,expected_level",
    list(_EXPECTED_LEVEL.items()),
)
def test_catalog_level_matches_validator(code: str, expected_level: str):
    rule = get_rule_by_code(code)
    assert rule is not None, f"catalog 未登记 {code}"
    assert rule.level == expected_level, (
        f"{code} catalog level={rule.level}，期望 {expected_level}"
    )


@pytest.mark.parametrize(
    "code,expected_severity",
    list(_EXPECTED_SEVERITY.items()),
)
def test_catalog_severity_matches_validator(code: str, expected_severity: str):
    rule = get_rule_by_code(code)
    assert rule is not None, f"catalog 未登记 {code}"
    assert rule.severity == expected_severity, (
        f"{code} catalog severity={rule.severity}，期望 {expected_severity}"
    )


# ---------------------------------------------------------------------------
# can_force 语义（L2_LEDGER_YEAR_OUT_OF_RANGE 不可 force，L1 不可 force）
# ---------------------------------------------------------------------------


def test_year_out_of_range_cannot_be_forced():
    rule = get_rule_by_code("L2_LEDGER_YEAR_OUT_OF_RANGE")
    assert rule is not None
    assert rule.can_force is False


def test_all_l1_rules_cannot_be_forced():
    """L1 blocking 全部不可 force（validator.evaluate_activation 语义）。"""
    for rule in VALIDATION_RULES_CATALOG:
        if rule.level == "L1" and rule.severity == "blocking":
            assert rule.can_force is False, (
                f"L1 blocking 规则 {rule.code} 不应允许 force"
            )


# ---------------------------------------------------------------------------
# get_rule_by_code
# ---------------------------------------------------------------------------


def test_get_rule_by_code_returns_correct_entry():
    rule = get_rule_by_code("BALANCE_LEDGER_MISMATCH")
    assert rule is not None
    assert rule.code == "BALANCE_LEDGER_MISMATCH"
    assert rule.level == "L3"
    assert "期末余额" in rule.formula_cn


def test_get_rule_by_code_unknown_returns_none():
    assert get_rule_by_code("NOT_A_REAL_CODE") is None
    assert get_rule_by_code("") is None
