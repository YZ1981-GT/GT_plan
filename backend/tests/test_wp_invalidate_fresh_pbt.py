# Feature: custom-workpaper-formula-binding, Property 9: 缓存失效后读到最新
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings, strategies as st

from app.services.address_registry import AddressEntry, AddressRegistryService, _CacheSlot

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(
    old_label=st.text(min_size=1, max_size=20),
    new_label=st.text(min_size=1, max_size=20),
)
def test_p9_invalidate_refreshes_domain_cache(old_label: str, new_label: str):
    new_label = new_label if new_label != old_label else new_label + "_新"

    pid = str(uuid.uuid4())
    year = 2025
    tpl = "soe"
    domain = "wp"

    old_entries = [
        AddressEntry(
            uri="wp://X/B5",
            domain="wp",
            source="X",
            path="B5",
            cell="B5",
            label=old_label,
            formula_ref="WP('X','B5')",
            wp_code="X",
        )
    ]
    new_entries = [
        AddressEntry(
            uri="wp://X/B5",
            domain="wp",
            source="X",
            path="B5",
            cell="B5",
            label=new_label,
            formula_ref="WP('X','B5')",
            wp_code="X",
        )
    ]

    svc = AddressRegistryService()
    key = svc._slot_key(pid, year, tpl, domain)
    svc._slots[key] = _CacheSlot(entries=old_entries, built_at=0, domain=domain)

    async def _inner():
        with patch.object(svc, "_redis_get", new_callable=AsyncMock, return_value=None):
            with patch.object(svc, "_redis_set", new_callable=AsyncMock):
                with patch.object(svc, "_redis_delete_many", new_callable=AsyncMock):
                    await svc.invalidate_async(pid, year=year, domain=domain)
                    assert key not in svc._slots
                    with patch.object(
                        svc,
                        "_get_domain",
                        new_callable=AsyncMock,
                        return_value=new_entries,
                    ):
                        return await svc._get_domain(None, pid, year, tpl, domain)

    fresh = _run(_inner())
    assert fresh[0].label == new_label
