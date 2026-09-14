"""Unit tests for a17_signoff_self_check helpers."""

from __future__ import annotations

from app.services.a17_signoff_self_check import _is_bare_no, _is_truthy


def test_is_bare_no():
    assert _is_bare_no("否", None) is True
    assert _is_bare_no("否", "") is True
    assert _is_bare_no("否", "已补做") is False
    assert _is_bare_no("是", None) is False
    assert _is_bare_no("X/W", None) is True


def test_is_truthy():
    assert _is_truthy("是") is True
    assert _is_truthy("不适用") is True
    assert _is_truthy("") is False
    assert _is_truthy("否") is False
