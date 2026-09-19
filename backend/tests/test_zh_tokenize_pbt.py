"""
PBT P5 (audit terms as single tokens) for jieba zh_tokenize.

Validates: Requirements 6.5
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services._zh_tokenize import zh_tokenize


# ─── Load audit dict terms for testing ────────────────────────────────────────

def _load_audit_terms() -> list[str]:
    """Load all terms from jieba_audit_dict.txt."""
    dict_path = Path(__file__).resolve().parent.parent / "data" / "jieba_audit_dict.txt"
    terms = []
    with open(dict_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                terms.append(parts[0])
    return terms


AUDIT_TERMS = _load_audit_terms()


# ─── PBT P5: Audit terms tokenize as single tokens ───────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    idx=st.integers(min_value=0, max_value=len(AUDIT_TERMS) - 1)
)
def test_audit_term_single_token(idx: int):
    """
    **Validates: Requirements 6.5**

    PBT P5: For all terms in jieba_audit_dict.txt, zh_tokenize(term) shall
    produce the full term as a single token.
    E.g. "应收账款" → ["应收账款"] not ["应收", "收账", "账款"]
    """
    term = AUDIT_TERMS[idx]
    tokens = zh_tokenize(term)

    # The term must appear as a single token in the result
    assert term.lower() in tokens, (
        f"Term '{term}' not found as single token.\n"
        f"Got tokens: {tokens}"
    )


# ─── Deterministic test: sample important terms ──────────────────────────────


@pytest.mark.parametrize("term", [
    "应收账款",
    "长期股权投资",
    "重大错报风险",
    "预期信用损失",
    "中国证监会",
    "实质性程序",
    "控制测试",
    "持续经营",
    "资产减值损失",
    "企业会计准则",
    "审计工作底稿",
    "管理层凌驾控制",
    "关联方交易",
    "货币单位抽样",
    "以公允价值计量且其变动计入当期损益的金融资产",
])
def test_key_audit_terms_single_token(term: str):
    """Key audit terms must tokenize as single tokens."""
    tokens = zh_tokenize(term)
    assert term.lower() in tokens, f"'{term}' split into: {tokens}"


def test_audit_dict_has_500_plus_terms():
    """Audit dictionary has at least 500 terms."""
    assert len(AUDIT_TERMS) >= 500, f"Only {len(AUDIT_TERMS)} terms, need 500+"


def test_mixed_text_preserves_audit_terms():
    """In mixed text, audit terms are preserved as whole tokens."""
    text = "根据企业会计准则的规定，应收账款需要计提坏账准备"
    tokens = zh_tokenize(text)

    # These should be single tokens
    assert "企业会计准则" in tokens
    assert "应收账款" in tokens
    assert "坏账准备" in tokens
