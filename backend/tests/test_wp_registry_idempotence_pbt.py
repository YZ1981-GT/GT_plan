# Feature: custom-workpaper-formula-binding, Property 3: 注册幂等
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.services.address_registry import _build_custom_wp_cell_entries

_PARSED = st.fixed_dictionaries(
    {},
    optional={
        "html_data": st.fixed_dictionaries(
            {"审定表": st.fixed_dictionaries({"cells": st.just({"B5": 1, "A5": "行"})})}
        )
    },
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(parsed=_PARSED)
def test_p3_custom_entries_build_idempotent(parsed):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [(parsed, "C1", "底稿")])
    )
    pid = str(uuid.uuid4())

    async def _build():
        return await _build_custom_wp_cell_entries(db, pid, 2025)

    a = _run(_build())
    b = _run(_build())
    assert len(a) == len(b)
    assert {(e.wp_code, e.cell, e.formula_ref) for e in a} == {
        (e.wp_code, e.cell, e.formula_ref) for e in b
    }
