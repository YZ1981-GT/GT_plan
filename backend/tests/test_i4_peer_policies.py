"""I4 同业年报摘录库 — 数据与过滤逻辑单测"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.wp_render_strategies import _i4_peer_policies as mod


def test_catalog_has_retail_peers():
    catalog = mod._load_catalog()
    industries = catalog.get("industries") or []
    retail = next((i for i in industries if i.get("id") == "retail"), None)
    assert retail is not None
    assert len(retail.get("peers") or []) >= 1
    peer0 = retail["peers"][0]
    assert peer0.get("name")
    assert peer0.get("policies")
    assert "装修费" in peer0["policies"]


def test_catalog_industries_cover_three_sectors():
    catalog = mod._load_catalog()
    ids = {i.get("id") for i in (catalog.get("industries") or [])}
    assert {"retail", "manufacturing", "property"} <= ids


@pytest.mark.asyncio
async def test_get_policies_handler():
    class _U:
        id = 1

    data = await mod.get_peer_ltpa_policies(industry="manufacturing", year=None, _user=_U())  # type: ignore[arg-type]
    assert data["industry"] == "manufacturing"
    assert len(data["peers"]) >= 1
    assert "disclaimer" in data
    assert data["peers"][0].get("source")


@pytest.mark.asyncio
async def test_year_filter():
    class _U:
        id = 1

    data = await mod.get_peer_ltpa_policies(industry="retail", year=2099, _user=_U())  # type: ignore[arg-type]
    assert data["peers"] == []


@pytest.mark.asyncio
async def test_unknown_industry_404():
    class _U:
        id = 1

    with pytest.raises(HTTPException) as ei:
        await mod.get_peer_ltpa_policies(industry="no-such", year=None, _user=_U())  # type: ignore[arg-type]
    assert ei.value.status_code == 404
