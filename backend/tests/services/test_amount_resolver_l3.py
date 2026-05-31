"""L3 取数适配层补全 — NoteResolver / WPResolver / DisplayResolver 测试。

验证三个新 Resolver 均实现 AmountResolver Protocol，
且取数逻辑正确（全程 Decimal，无 float 中转）。

Validates: Requirements 3.2
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st

from app.services.amount_resolver import (
    AmountResolver,
    DisplayResolver,
    NoteResolver,
    WPResolver,
)


PBT_SETTINGS = settings(max_examples=15, deadline=None)


# ---------------------------------------------------------------------------
# Protocol 合规性测试（runtime_checkable）
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """验证三个新 Resolver 均满足 AmountResolver Protocol。"""

    def test_note_resolver_is_amount_resolver(self):
        """NoteResolver 实现 AmountResolver Protocol。"""
        # NoteResolver 需要 db/project_id/year，用 None 占位验证 Protocol
        resolver = NoteResolver(db=None, project_id=None, year=2025)  # type: ignore
        assert isinstance(resolver, AmountResolver)

    def test_wp_resolver_is_amount_resolver(self):
        """WPResolver 实现 AmountResolver Protocol。"""
        resolver = WPResolver(db=None, project_id=None, year=2025)  # type: ignore
        assert isinstance(resolver, AmountResolver)

    def test_display_resolver_is_amount_resolver(self):
        """DisplayResolver 实现 AmountResolver Protocol。"""
        resolver = DisplayResolver()
        assert isinstance(resolver, AmountResolver)


# ---------------------------------------------------------------------------
# DisplayResolver 单元测试（纯 mock，不需 DB）
# ---------------------------------------------------------------------------


def _run(coro):
    """每测试独立 event loop。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestDisplayResolver:
    """DisplayResolver 预览模式：所有取数返回 Decimal("0")。"""

    def test_resolve_tb_returns_zero(self):
        resolver = DisplayResolver()
        result = _run(resolver.resolve_tb("1001", "期末余额"))
        assert result == Decimal("0")
        assert isinstance(result, Decimal)

    def test_resolve_sum_returns_zero(self):
        resolver = DisplayResolver()
        result = _run(resolver.resolve_sum("1000~1999", "期末余额"))
        assert result == Decimal("0")
        assert isinstance(result, Decimal)

    def test_resolve_tb_any_code_returns_zero(self):
        resolver = DisplayResolver()
        result = _run(resolver.resolve_tb("ANY_CODE", "任意列"))
        assert result == Decimal("0")

    def test_resolve_sum_invalid_range_returns_zero(self):
        resolver = DisplayResolver()
        result = _run(resolver.resolve_sum("no_tilde", "期末余额"))
        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# PBT: DisplayResolver 对任意输入恒返回 Decimal("0")（Q1 语义一致基础）
# ---------------------------------------------------------------------------


@PBT_SETTINGS
@given(
    account_code=st.text(min_size=1, max_size=20),
    column_name=st.text(min_size=1, max_size=20),
)
def test_display_resolver_resolve_tb_always_zero(account_code: str, column_name: str):
    """**Validates: Requirements 3.2**

    DisplayResolver.resolve_tb 对任意 account_code/column_name 恒返回 Decimal("0")。
    """
    resolver = DisplayResolver()
    result = _run(resolver.resolve_tb(account_code, column_name))
    assert result == Decimal("0")
    assert isinstance(result, Decimal)


@PBT_SETTINGS
@given(
    code_range=st.text(min_size=1, max_size=30),
    column_name=st.text(min_size=1, max_size=20),
)
def test_display_resolver_resolve_sum_always_zero(code_range: str, column_name: str):
    """**Validates: Requirements 3.2**

    DisplayResolver.resolve_sum 对任意 code_range/column_name 恒返回 Decimal("0")。
    """
    resolver = DisplayResolver()
    result = _run(resolver.resolve_sum(code_range, column_name))
    assert result == Decimal("0")
    assert isinstance(result, Decimal)
