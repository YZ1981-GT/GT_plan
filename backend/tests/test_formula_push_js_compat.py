"""`formula_push.js_compat` —— 与 JS 数值语义逐位一致。

期望值取自 ECMAScript 规范行为（Node 实测口径）；另用 hypothesis 验证
「格式化后再按 JS 解析得回原数」（round-trip）。
"""
from __future__ import annotations

import math
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_push.js_compat import (
    js_json_number,
    js_number,
    js_number_to_string,
    js_or_zero,
    parse_num,
    read_number,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12", 12.0), ("  12.5 ", 12.5), ("1e3", 1000.0), (".5", 0.5), ("5.", 5.0),
        ("0x1A", 26.0), ("0b101", 5.0), ("0o17", 15.0), ("", 0.0), ("   ", 0.0),
        ("Infinity", math.inf), ("-Infinity", -math.inf), (None, 0.0), (True, 1.0),
        (Decimal("1.25"), 1.25), (7, 7.0),
    ],
)
def test_js_number(raw, expected):
    assert js_number(raw) == expected


@pytest.mark.parametrize("raw", ["1_000", "nan", "inf", "1,000", "abc", "-0x10", "12abc", {}, [1, 2]])
def test_js_number_nan(raw):
    assert math.isnan(js_number(raw))


def test_js_number_lists_follow_js():
    # Node：Number([]) === 0，Number([5]) === 5，Number(['7']) === 7
    assert js_number([]) == 0.0 and js_number([5]) == 5.0 and js_number(["7"]) == 7.0


def test_parse_num_read_number_or_zero():
    assert parse_num(None) == 0 and parse_num("") == 0 and parse_num("abc") == 0
    assert parse_num("Infinity") == 0 and parse_num("  3 ") == 3
    assert read_number(None) is None and read_number("") is None and read_number("abc") is None
    assert read_number("0") == 0.0 and read_number("  ") == 0.0  # Number('  ') === 0
    assert js_or_zero("abc") == 0 and js_or_zero("5") == 5 and js_or_zero(-0.0) == 0


@pytest.mark.parametrize(
    "value,expected",
    [
        (100.0, "100"), (0.1 + 0.2, "0.30000000000000004"), (1e-7, "1e-7"), (1.5e-5, "0.000015"),
        (1.2345678901234568e20, "123456789012345680000"), (1e21, "1e+21"), (-286.73, "-286.73"),
        (-0.0, "0"), (5e-324, "5e-324"), (123.456, "123.456"), (0.000001, "0.000001"),
        (1e-6 * 0.5, "5e-7"), (4479140.0, "4479140"), (9182572.99, "9182572.99"),
        (Decimal("12.50"), "12.5"),
    ],
)
def test_js_number_to_string(value, expected):
    assert js_number_to_string(value) == expected


def test_js_json_number():
    assert js_json_number(100.0) == 100 and isinstance(js_json_number(100.0), int)
    assert js_json_number(286.73) == 286.73
    assert isinstance(js_json_number(2.0**60), float)


@settings(max_examples=5, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_to_string_round_trips_through_js_number(x):
    assert js_number(js_number_to_string(x)) == (0.0 if x == 0 else x)
