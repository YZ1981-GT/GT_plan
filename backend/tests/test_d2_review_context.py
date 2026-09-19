"""Tests for D2 reconciliation context injection."""
from __future__ import annotations

from app.services.d2_review_context import (
    _d2_audited_total,
    _fmt,
    _parse_num,
    _safe_json_rows,
    _sumif_detail,
    append_reconciliation_to_user_prompt,
)


def test_parse_num():
    assert _parse_num("123.45") == 123.45
    assert _parse_num(None) == 0.0
    assert _parse_num("") == 0.0
    assert _parse_num("x") == 0.0


def test_safe_json_rows():
    assert _safe_json_rows('[{"a":1}]') == [{"a": 1}]
    assert _safe_json_rows("not-json") == []
    assert _safe_json_rows(None) == []
    assert _safe_json_rows('{"a":1}') == []  # dict → empty


def test_fmt():
    assert _fmt(1234567.8) == "1,234,567.80"


def test_append_recon_empty():
    base = "hello"
    assert append_reconciliation_to_user_prompt(base, "") == base
    assert append_reconciliation_to_user_prompt(base, "   ") == base


def test_append_recon_nonempty():
    out = append_reconciliation_to_user_prompt("body", "## 勾稽\n- diff")
    assert out.startswith("body")
    assert "## 勾稽" in out


def test_build_context_from_mock_rows():
    """纯函数路径：用手工 by_id 逻辑验证差异文案（经模块内部辅助）。"""
    # 通过 _safe_json_rows + 计算复现核心分支
    detail = _safe_json_rows(
        '[{"currentAudited": 100}, {"currentAudited": 50}]'
    )
    detail_total = sum(float(r["currentAudited"]) for r in detail)
    assert detail_total == 150.0

    bd_rows = _safe_json_rows(
        '[{"isFixed": true, "currentAudited": 10}, {"currentAudited": 99}]'
    )
    bd = next(
        (float(r["currentAudited"]) for r in bd_rows if r.get("isFixed")),
        0.0,
    )
    assert bd == 10.0

    ecl = _safe_json_rows('[{"shouldProvision": 12}]')
    ecl_total = sum(float(r["shouldProvision"]) for r in ecl)
    assert abs(ecl_total - bd) == 2.0


# ── SUMIF 回退修复（审定表分项缺失时回退明细）──────────────────────────


def _detail_fixture():
    return [
        {"creditRiskClassification": "单项计提", "currentUnadjusted": 100,
         "currentAje": 0, "currentRje": 0, "currentAudited": 100},
        {"creditRiskClassification": "账龄组合", "currentUnadjusted": 200,
         "currentAje": 10, "currentRje": 0, "currentAudited": 210},
        {"creditRiskClassification": "客户类型组合", "currentUnadjusted": 50,
         "currentAje": 0, "currentRje": 5, "currentAudited": 55},
    ]


def test_sumif_detail_by_classification():
    rows = _detail_fixture()
    assert _sumif_detail(rows, "单项计提", "currentUnadjusted") == 100
    assert _sumif_detail(rows, "账龄组合", "currentAje") == 10
    assert _sumif_detail(rows, "客户类型组合", "currentRje") == 5
    assert _sumif_detail(rows, "不存在", "currentUnadjusted") == 0


def test_d2_audited_total_falls_back_to_sumif_when_adj_empty():
    """审定表分项全空 → 回退明细 SUMIF（100+210+55=365），不再误报 0。"""
    by_id: dict[str, str] = {}
    rows = _detail_fixture()
    assert _d2_audited_total(by_id, rows) == 365.0


def test_d2_audited_total_prefers_explicit_adj_values():
    """审定表分项已填 → 优先使用，不回退明细。"""
    by_id = {
        "D2-adj-individual-current-unadjusted": "1000",
        "D2-adj-aging-current-unadjusted": "2000",
        "D2-adj-customer-type-current-unadjusted": "500",
    }
    rows = _detail_fixture()
    # 单项/账龄/客户类型各取显式未审 + 明细回退的 aje/rje（明细 aje=10, rje=5）
    assert _d2_audited_total(by_id, rows) == 1000 + 2000 + 10 + 500 + 5
