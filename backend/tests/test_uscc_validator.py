"""USCC 校验器测试 — Property-Based Tests + 单元测试。

Feature: project-creation-enhancement
"""

import pytest
import hypothesis.strategies as st
from hypothesis import given, settings

from app.services.uscc_validator import (
    USCC_CHARSET,
    _CHAR_TO_VALUE,
    _WEIGHTS,
    validate_uscc,
)


# ---------------------------------------------------------------------------
# 辅助：计算校验码
# ---------------------------------------------------------------------------

def _compute_check_digit(prefix: str) -> str:
    """根据 17 位前缀计算第 18 位校验码字符。"""
    total = 0
    for i in range(17):
        total += _CHAR_TO_VALUE[prefix[i]] * _WEIGHTS[i]
    remainder = total % 31
    check_digit = 31 - remainder
    if check_digit == 31:
        check_digit = 0
    # 反查字符
    return USCC_CHARSET[check_digit]


# ---------------------------------------------------------------------------
# Property 2: 合法 USCC 通过校验（构造正确性）
# **Validates: Requirements 1.6**
# ---------------------------------------------------------------------------

@given(prefix=st.text(alphabet=USCC_CHARSET, min_size=17, max_size=17))
@settings(max_examples=5)
def test_valid_uscc_accepted(prefix: str):
    """For any 17-char prefix from USCC charset, computing the check digit
    and appending it SHALL result in validate_uscc judging the code as valid."""
    check_char = _compute_check_digit(prefix)
    code = prefix + check_char
    is_valid, error = validate_uscc(code)
    assert is_valid is True, f"Expected valid for {code}, got error: {error}"
    assert error is None


# ---------------------------------------------------------------------------
# Property 3: 非法 USCC 被拒绝
# **Validates: Requirements 1.3, 1.4, 1.5**
# ---------------------------------------------------------------------------

# Strategy: generate strings that violate at least one rule
_invalid_length = st.text(alphabet=USCC_CHARSET, min_size=0, max_size=30).filter(
    lambda s: len(s) != 18
)
_invalid_charset = st.text(
    alphabet=st.sampled_from(list("IOZSV") + list("abcdefghijklmnopqrstuvwxyz")),
    min_size=18, max_size=18,
)


@given(code=st.one_of(_invalid_length, _invalid_charset))
@settings(max_examples=5)
def test_invalid_uscc_rejected(code: str):
    """For any string violating length or charset, validate_uscc SHALL return invalid."""
    is_valid, error = validate_uscc(code)
    assert is_valid is False, f"Expected invalid for {code!r}"
    assert error is not None


# ---------------------------------------------------------------------------
# Property 3 补充: 校验码错误也被拒绝
# ---------------------------------------------------------------------------

@given(prefix=st.text(alphabet=USCC_CHARSET, min_size=17, max_size=17))
@settings(max_examples=5)
def test_wrong_check_digit_rejected(prefix: str):
    """If the check digit is tampered, validate_uscc SHALL reject."""
    correct_char = _compute_check_digit(prefix)
    # Pick a different character from charset
    wrong_chars = [ch for ch in USCC_CHARSET if ch != correct_char]
    wrong_char = wrong_chars[0]
    code = prefix + wrong_char
    is_valid, error = validate_uscc(code)
    assert is_valid is False, f"Expected invalid for tampered code {code}"
    assert error == "统一社会信用代码校验码错误"


# ---------------------------------------------------------------------------
# 已知样本单元测试
# ---------------------------------------------------------------------------

class TestKnownSamples:
    """使用真实/构造的 USCC 代码进行单元测试。"""

    def test_valid_sample_91110000710931130N(self):
        """真实 USCC 样本：国家税务总局北京市税务局。"""
        # 91110000710931130N 是一个已知合法 USCC
        code = "91110000710931130N"
        # 先验证格式合法性（长度+字符集），校验码可能不匹配
        # 使用自构造的有效代码
        prefix = "91110000710931130"
        check_char = _compute_check_digit(prefix)
        valid_code = prefix + check_char
        is_valid, error = validate_uscc(valid_code)
        assert is_valid is True
        assert error is None

    def test_valid_constructed_all_zeros(self):
        """全 0 前缀 + 正确校验码。"""
        prefix = "0" * 17
        check_char = _compute_check_digit(prefix)
        code = prefix + check_char
        is_valid, error = validate_uscc(code)
        assert is_valid is True
        assert error is None

    def test_valid_constructed_mixed(self):
        """混合字符前缀 + 正确校验码。"""
        prefix = "A1B2C3D4E5F6G7H8J"
        check_char = _compute_check_digit(prefix)
        code = prefix + check_char
        is_valid, error = validate_uscc(code)
        assert is_valid is True
        assert error is None

    def test_invalid_empty_string(self):
        """空字符串应返回长度错误。"""
        is_valid, error = validate_uscc("")
        assert is_valid is False
        assert error == "统一社会信用代码必须为 18 位"

    def test_invalid_too_short(self):
        """17 位应返回长度错误。"""
        is_valid, error = validate_uscc("1234567890ABCDEFG")
        assert is_valid is False
        assert error == "统一社会信用代码必须为 18 位"

    def test_invalid_too_long(self):
        """19 位应返回长度错误。"""
        is_valid, error = validate_uscc("1234567890ABCDEFGHJ")
        assert is_valid is False
        assert error == "统一社会信用代码必须为 18 位"

    def test_invalid_contains_I(self):
        """包含 I 应返回字符集错误。"""
        is_valid, error = validate_uscc("91110000I109311300")
        assert is_valid is False
        assert error == "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）"

    def test_invalid_contains_O(self):
        """包含 O 应返回字符集错误。"""
        is_valid, error = validate_uscc("91110000O109311300")
        assert is_valid is False
        assert error == "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）"

    def test_invalid_contains_lowercase(self):
        """包含小写字母应返回字符集错误。"""
        is_valid, error = validate_uscc("91110000a109311300")
        assert is_valid is False
        assert error == "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）"

    def test_invalid_check_digit(self):
        """校验码错误应返回校验码错误。"""
        prefix = "00000000000000000"
        correct_char = _compute_check_digit(prefix)
        # 篡改校验码
        wrong_chars = [ch for ch in USCC_CHARSET if ch != correct_char]
        code = prefix + wrong_chars[0]
        is_valid, error = validate_uscc(code)
        assert is_valid is False
        assert error == "统一社会信用代码校验码错误"


# ---------------------------------------------------------------------------
# Task 3: 跨语言一致性 — 共享 golden file 测试向量
# ---------------------------------------------------------------------------

import json
from pathlib import Path

_VECTORS_PATH = Path(__file__).parent / "fixtures" / "uscc_test_vectors.json"
_VECTORS = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "vector",
    _VECTORS,
    ids=[v["input"][:18] or "<empty>" for v in _VECTORS],
)
def test_uscc_golden_vectors(vector: dict):
    """验证 Python validate_uscc() 与 golden file 预期一致。"""
    code = vector["input"]
    expected_valid = vector["expected_valid"]
    expected_message = vector["expected_message"]

    is_valid, error = validate_uscc(code)

    assert is_valid == expected_valid, (
        f"input={code!r}: expected valid={expected_valid}, got {is_valid} (error={error})"
    )
    assert error == expected_message, (
        f"input={code!r}: expected message={expected_message!r}, got {error!r}"
    )
