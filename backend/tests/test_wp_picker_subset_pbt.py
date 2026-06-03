# Feature: custom-workpaper-formula-binding, Property 4: 弹窗可选项 ⊆ 注册表条目
"""自定义条目 formula_ref 必出现在 build_workpaper_entries 全量 WP 域结果中。"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.services.address_registry import (
    _build_custom_wp_cell_entries,
    build_workpaper_entries,
)

_cell_st = st.sampled_from(["B5", "C12", "D10", "Z99"])
_wp_code_st = st.sampled_from(["CUST-P4", "CUST-中文", "PW-X01"])


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(cell=_cell_st, wp_code=_wp_code_st)
def test_custom_formula_refs_subset_of_full_wp_registry(cell: str, wp_code: str):
    cell_up = cell.upper()
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A1": "行名",
                    cell_up: 42,
                }
            }
        }
    }
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [(parsed, wp_code, f"{wp_code}底稿")])
    )
    pid = str(uuid.uuid4())

    async def _inner():
        full = await build_workpaper_entries(db, pid, 2025)
        custom_only = await _build_custom_wp_cell_entries(db, pid, 2025)
        return full, custom_only

    full_entries, custom_entries = _run(_inner())
    full_refs = {e.formula_ref for e in full_entries if e.formula_ref}
    assert full_refs, "标准 WP 域条目不应为空"

    for e in custom_entries:
        assert e.formula_ref in full_refs, (
            f"自定义条目 {e.formula_ref} 未出现在全量注册表"
        )

    # 空自定义时标准条目仍在（降级场景）
    db_empty = AsyncMock()
    db_empty.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
    only_standard = _run(build_workpaper_entries(db_empty, pid, 2025))
    assert len(only_standard) > 0
