"""
PBT P6 (context boost bounded) + unit tests.

Validates: Requirements 7.4
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.knowledge_index_service import (
    _apply_context_boost,
    _matches_cycle,
    _matches_account,
)


# ─── PBT P6: Context boost bounded ───────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    wp_code=st.one_of(st.none(), st.sampled_from(["D1", "E2", "F3", "G4", "H5", "K8", "L1", "M3", "N2", "X9"])),
    account_code=st.one_of(st.none(), st.sampled_from(["1122", "2202", "6601", "9999", "1401"])),
    audit_area=st.one_of(st.none(), st.text(min_size=0, max_size=20)),
    score=st.floats(min_value=0.0, max_value=1.0),
)
def test_context_boost_bounded(wp_code, account_code, audit_area, score):
    """
    **Validates: Requirements 7.4**

    PBT P6: For all combinations of wp_code and account_code inputs,
    the final score must be in [0.0, 1.0] after boost application.
    final_score = 0.7 * vector_similarity + 0.3 * context_boost
    where context_boost in [0.0, 1.0].
    """
    results = [{"content": "应收账款相关的审计准则内容", "score": score}]

    boosted = _apply_context_boost(results, wp_code, account_code, audit_area)

    for r in boosted:
        final_score = r["score"]
        # Final score must be bounded
        assert 0.0 <= final_score <= 1.0, (
            f"Score {final_score} out of bounds [0, 1]. "
            f"wp_code={wp_code}, account_code={account_code}, "
            f"original_score={score}"
        )


# ─── Unit Tests ───────────────────────────────────────────────────────────────


def test_no_context_no_boost():
    """Without context signals, score = 0.7 * original (no boost)."""
    results = [{"content": "测试内容", "score": 0.8}]
    boosted = _apply_context_boost(results, None, None, None)
    # 0.7 * 0.8 + 0.3 * 0.0 = 0.56
    assert boosted[0]["score"] == pytest.approx(0.56, abs=0.001)


def test_wp_code_match_boosts():
    """Matching wp_code cycle keywords increases score."""
    results = [{"content": "应收账款管理和收入确认", "score": 0.5}]
    boosted = _apply_context_boost(results, "D1", None, None)
    # D → ["应收", "收入", "销售"], content has "应收" + "收入" → boost=0.5
    # final = 0.7 * 0.5 + 0.3 * 0.5 = 0.35 + 0.15 = 0.5
    assert boosted[0]["score"] == pytest.approx(0.5, abs=0.001)


def test_account_code_match_boosts():
    """Matching account_code increases score."""
    results = [{"content": "应收账款的计提和核销", "score": 0.6}]
    boosted = _apply_context_boost(results, None, "1122", None)
    # 1122 → "应收账款", content has "应收账款" → boost=0.5
    # final = 0.7 * 0.6 + 0.3 * 0.5 = 0.42 + 0.15 = 0.57
    assert boosted[0]["score"] == pytest.approx(0.57, abs=0.001)


def test_both_match_full_boost():
    """Both wp_code and account_code matching gives boost=1.0."""
    results = [{"content": "应收账款坏账准备和收入确认", "score": 0.5}]
    boosted = _apply_context_boost(results, "D1", "1122", None)
    # D cycle match (应收) + account match (应收账款) → boost=1.0
    # final = 0.7 * 0.5 + 0.3 * 1.0 = 0.35 + 0.3 = 0.65
    assert boosted[0]["score"] == pytest.approx(0.65, abs=0.001)


def test_results_resorted_after_boost():
    """Results are re-sorted by boosted score."""
    results = [
        {"content": "无关内容文档", "score": 0.9},
        {"content": "应收账款相关准则", "score": 0.5},
    ]
    boosted = _apply_context_boost(results, "D1", "1122", None)
    # First: 0.9 * 0.7 + 0 * 0.3 = 0.63
    # Second: 0.5 * 0.7 + 1.0 * 0.3 = 0.65
    # After sort: second should be first
    assert boosted[0]["content"] == "应收账款相关准则"


def test_matches_cycle_positive():
    """_matches_cycle returns True for matching cycle keywords."""
    assert _matches_cycle("应收账款减值", "D1") is True
    assert _matches_cycle("存货采购成本", "F2") is True


def test_matches_cycle_negative():
    """_matches_cycle returns False for non-matching content."""
    assert _matches_cycle("无关内容", "D1") is False
    assert _matches_cycle("应收账款", "Z9") is False  # Z not in map


def test_matches_account_positive():
    """_matches_account returns True for matching account."""
    assert _matches_account("应收账款坏账准备计提", "1122") is True


def test_matches_account_negative():
    """_matches_account returns False for non-matching account."""
    assert _matches_account("固定资产折旧", "1122") is False
