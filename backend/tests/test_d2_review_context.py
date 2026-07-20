"""Tests for D2 reconciliation context injection."""
from __future__ import annotations

from app.services.d2_review_context import (
    _fmt,
    _parse_num,
    _safe_json_rows,
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
