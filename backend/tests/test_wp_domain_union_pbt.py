# Feature: custom-workpaper-formula-binding, Property 1: WP 域并集不丢失
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.services.address_registry import build_workpaper_entries

_MAPPING = (
    Path(__file__).resolve().parent.parent / "data" / "wp_account_mapping.json"
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _standard_refs() -> set[str]:
    if not _MAPPING.is_file():
        return set()
    data = json.loads(_MAPPING.read_text(encoding="utf-8-sig"))
    refs = set()
    for m in data.get("mappings", [])[:5]:
        code = m.get("wp_code", "")
        if code:
            refs.add(f"WP('{code}','审定数')")
    return refs


@settings(max_examples=3)
@given(custom_cell=st.sampled_from(["B5", "C12", "D3"]))
def test_p1_standard_entries_subset_after_custom_append(custom_cell: str):
    standard_refs = _standard_refs()
    if not standard_refs:
        return

    parsed = {"html_data": {"审定表": {"cells": {custom_cell: 100}}}}
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [(parsed, "CUST-U", "自定义")])
    )

    async def _inner():
        return await build_workpaper_entries(db, str(uuid.uuid4()), 2025)

    entries = _run(_inner())
    built_refs = {e.formula_ref for e in entries if e.formula_ref}
    assert standard_refs.issubset(built_refs)
    assert any("CUST-U" in (e.wp_code or "") for e in entries)
