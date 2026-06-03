# Feature: custom-workpaper-formula-binding, Property 5: 解析异常不崩
"""extract_custom_cells / _build_custom 对坏数据不抛异常。"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.services.address_registry import (
    _build_custom_wp_cell_entries,
    build_workpaper_entries,
    extract_custom_cells,
)

_BAD_PARSED = st.one_of(
    st.none(),
    st.just({}),
    st.just({"html_data": None}),
    st.just({"html_data": "bad"}),
    st.just({"html_data": {"x": {"cells": "not-a-dict"}}}),
    st.just({"乱码表": {"不是单元格": "中文值"}}),
    st.just({"html_data": {"审定表": {"cells": {"A1": {"value": "嵌套", "label": "中文行"}}}}}),
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(parsed=_BAD_PARSED)
def test_extract_custom_cells_never_raises(parsed):
    result = extract_custom_cells(parsed)
    assert isinstance(result, list)


@settings(max_examples=5)
@given(parsed=_BAD_PARSED)
def test_build_custom_wp_cell_entries_never_raises(parsed):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            all=lambda: [(parsed, "CUST-99", "中文底稿名")]
        )
    )

    async def _inner():
        return await _build_custom_wp_cell_entries(db, str(uuid.uuid4()), 2025)

    entries = _run(_inner())
    assert isinstance(entries, list)


@settings(max_examples=3)
@given(parsed=_BAD_PARSED)
def test_build_workpaper_entries_keeps_standard_subset(parsed):
    """标准映射条目在坏自定义数据存在时仍应保留（不抛异常）。"""

    async def _inner():
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(all=lambda: [(parsed, "X", "测")])
        )
        entries = await build_workpaper_entries(db, str(uuid.uuid4()), 2025)
        return entries

    entries = _run(_inner())
    assert len(entries) > 0
    assert any(e.domain == "wp" for e in entries)
