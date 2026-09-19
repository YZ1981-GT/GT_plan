"""Tests for generic cycle (K/N) reconciliation context injection.

纯函数 + 注册表覆盖测试，不依赖 DB。
"""
from __future__ import annotations

import pytest

from app.services.cycle_review_context import (
    _REGISTRY,
    _fmt,
    _num_from_map,
    _parse_num,
    _sum_rows_field,
    append_reconciliation_to_user_prompt,
    extract_cycle_code,
)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def test_parse_num():
    assert _parse_num("123.45") == 123.45
    assert _parse_num(None) == 0.0
    assert _parse_num("") == 0.0
    assert _parse_num("x") == 0.0
    assert _parse_num(10) == 10.0


def test_fmt():
    assert _fmt(1234567.8) == "1,234,567.80"
    assert _fmt(0) == "0.00"


def test_extract_cycle_code():
    assert extract_cycle_code("K9-1") == "K9"
    assert extract_cycle_code("K9") == "K9"
    assert extract_cycle_code("N2") == "N2"
    assert extract_cycle_code("K11-2") == "K11"
    assert extract_cycle_code("审定表K9-1") is None  # 需以编码开头
    assert extract_cycle_code("") is None
    assert extract_cycle_code(None) is None


def test_num_from_map_prefers_remark_then_conclusion():
    by_id = {
        "a": {"remark": "100", "conclusion": None},
        "b": {"remark": None, "conclusion": "50"},
        "c": {"remark": "", "conclusion": "0"},
    }
    assert _num_from_map(by_id, "a") == 100.0
    assert _num_from_map(by_id, "b") == 50.0
    assert _num_from_map(by_id, "c") == 0.0
    assert _num_from_map(by_id, "missing") == 0.0


def test_sum_rows_field_from_conclusion():
    by_id = {
        "N2-2-rows": {
            "conclusion": '[{"endBalance": 100}, {"endBalance": 50}]',
            "remark": None,
        }
    }
    total, has = _sum_rows_field(by_id, "N2-2-rows", "endBalance", "conclusion")
    assert has is True
    assert total == 150.0


def test_sum_rows_field_missing_or_invalid():
    total, has = _sum_rows_field({}, "N2-2-rows", "endBalance", "conclusion")
    assert (total, has) == (0.0, False)

    by_id = {"N3-2-rows": {"conclusion": "not-json", "remark": None}}
    total, has = _sum_rows_field(by_id, "N3-2-rows", "endDeferredTaxLiability", "conclusion")
    assert (total, has) == (0.0, False)

    by_id2 = {"N3-2-rows": {"conclusion": "[]", "remark": None}}
    total, has = _sum_rows_field(by_id2, "N3-2-rows", "endDeferredTaxLiability", "conclusion")
    assert (total, has) == (0.0, False)


def test_append_recon():
    assert append_reconciliation_to_user_prompt("body", "") == "body"
    assert append_reconciliation_to_user_prompt("body", "   ") == "body"
    out = append_reconciliation_to_user_prompt("body", "## 勾稽\n- x")
    assert out.startswith("body")
    assert "## 勾稽" in out


# ---------------------------------------------------------------------------
# 注册表覆盖 —— 目标循环全部登记
# ---------------------------------------------------------------------------

_EXPECTED_CYCLES = [
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "K10", "K11", "K12", "K13",
    "N1", "N2", "N3", "N4", "N5",
]


@pytest.mark.parametrize("cycle", _EXPECTED_CYCLES)
def test_registry_covers_target_cycle(cycle):
    assert cycle in _REGISTRY, f"{cycle} 未在勾稽注册表中"
    cfg = _REGISTRY[cycle]
    assert cfg.label
    assert cfg.account_codes, f"{cycle} 缺少 TB 科目"
    assert cfg.audited_total_keys, f"{cycle} 缺少审定合计键"
    # 明细来源二选一：合计键 或 行求和
    has_detail_source = bool(cfg.detail_total_keys) or bool(
        cfg.detail_rows_key and cfg.detail_rows_field
    )
    # N5 例外：所得税费用无单一明细合计，通过 N5-4/N5-8 回填审定，勾稽走 TB
    if cycle != "N5":
        assert has_detail_source, f"{cycle} 缺少明细来源配置"


def test_registry_account_codes_are_expected():
    # 抽查关键科目映射正确
    assert _REGISTRY["K1"].account_codes == ("1221",)
    assert _REGISTRY["K8"].account_codes == ("6601",)
    assert _REGISTRY["K8"].is_occurrence is True
    assert _REGISTRY["K1"].is_occurrence is False
    assert _REGISTRY["K6"].account_codes == ("1481", "2605")
    assert _REGISTRY["N2"].account_codes == ("2221",)
    assert _REGISTRY["N5"].audited_total_keys == ("N5-1-current-tax", "N5-1-deferred-tax")


def test_no_unexpected_cycles():
    # 注册表不应包含目标外循环（避免误注入 D/E/F/G/H/I/J/L/M）
    for code in _REGISTRY:
        assert code in _EXPECTED_CYCLES, f"意外登记的循环 {code}"
