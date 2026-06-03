# Feature: custom-workpaper-formula-binding, Property 10: 自定义条目完备性
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.services.address_registry import _build_custom_wp_cell_entries, extract_custom_cells

_CN_LABELS = ["货币资金", "应收账款", "固定资产", "长期借款"]
_cell_st = st.sampled_from(["B5", "C12", "D10", "Z99"])
_label_st = st.sampled_from(_CN_LABELS)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(cell=_cell_st, label=_label_st)
def test_custom_entry_fields_complete(cell: str, label: str):
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A1": label,
                    cell: 100,
                }
            }
        }
    }
    wp_code = "CUST-10"
    wp_name = "测试自定义"

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [(parsed, wp_code, wp_name)])
    )
    entries = _run(_build_custom_wp_cell_entries(db, str(uuid.uuid4()), 2025))

    recs = extract_custom_cells(parsed)
    rec = next((r for r in recs if r.cell == cell.upper()), None)
    assert rec is not None

    entry = next((e for e in entries if e.cell == cell.upper()), None)
    assert entry is not None
    assert entry.domain == "wp"
    assert entry.wp_code == wp_code
    assert wp_name in entry.label
    assert entry.cell == cell.upper()
    assert entry.formula_ref == f"WP('{wp_code}','{cell.upper()}')"
