"""Tests for checklist_responses router — V085 CRUD endpoints

Validates: Requirements 2.2, 2.3
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.main import app


def _make_engine():
    return create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)


@pytest_asyncio.fixture
async def client():
    """In-process ASGI test client"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token():
    """Create a valid JWT token for admin user directly (bypassing Redis-dependent login)"""
    from app.core.security import create_access_token

    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text(
                "SELECT id FROM users WHERE username = 'admin' AND is_active = true LIMIT 1"
            ))
            row = r.fetchone()
    finally:
        await engine.dispose()

    if row is None:
        pytest.skip("No admin user in DB")
    return create_access_token({"sub": str(row.id), "type": "access"})


@pytest_asyncio.fixture
async def wp_info():
    """Get a real working_paper id from the database"""
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text(
                "SELECT id, project_id FROM working_paper LIMIT 1"
            ))
            row = r.fetchone()
    finally:
        await engine.dispose()

    if row is None:
        pytest.skip("No working_paper in DB")
    return {"wp_id": str(row.id), "project_id": str(row.project_id)}


@pytest_asyncio.fixture(autouse=True)
async def cleanup(wp_info):
    """Clean up any test data after each test"""
    yield
    engine = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "DELETE FROM checklist_responses WHERE wp_id = :wp_id"
            ), {"wp_id": wp_info["wp_id"]})
    finally:
        await engine.dispose()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_empty_responses(client: AsyncClient, auth_token: str, wp_info: dict):
    """GET on a fresh wp should return empty list"""
    resp = await client.get(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=_headers(auth_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_put_and_get_responses(client: AsyncClient, auth_token: str, wp_info: dict):
    """PUT batch save then GET should return saved items"""
    headers = _headers(auth_token)
    items = [
        {"item_id": "S01-001", "conclusion": "Y", "remark": "已核对", "wp_ref": "D2-3"},
        {"item_id": "S01-002", "conclusion": "N", "remark": None, "wp_ref": None},
        {"item_id": "TOC-S01", "conclusion": "Y", "remark": None, "wp_ref": None},
    ]
    # PUT
    resp = await client.put(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=headers,
        json={"project_id": wp_info["project_id"], "items": items},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert len(data) == 3

    # GET
    resp2 = await client.get(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=headers,
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    data2 = body2.get("data", body2)
    item_ids = {item["item_id"] for item in data2}
    assert "S01-001" in item_ids
    assert "S01-002" in item_ids
    assert "TOC-S01" in item_ids

    # Verify values
    s01_001 = next(i for i in data2 if i["item_id"] == "S01-001")
    assert s01_001["conclusion"] == "Y"
    assert s01_001["remark"] == "已核对"
    assert s01_001["wp_ref"] == "D2-3"


@pytest.mark.asyncio
async def test_put_upsert_updates_existing(client: AsyncClient, auth_token: str, wp_info: dict):
    """PUT same item_id should update (not duplicate)"""
    headers = _headers(auth_token)
    # First save
    await client.put(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=headers,
        json={"project_id": wp_info["project_id"], "items": [
            {"item_id": "S02-001", "conclusion": "Y", "remark": "v1"}
        ]},
    )
    # Update
    resp = await client.put(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=headers,
        json={"project_id": wp_info["project_id"], "items": [
            {"item_id": "S02-001", "conclusion": "NA", "remark": "v2"}
        ]},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert len(data) == 1
    assert data[0]["conclusion"] == "NA"
    assert data[0]["remark"] == "v2"


@pytest.mark.asyncio
async def test_put_invalid_conclusion(client: AsyncClient, auth_token: str, wp_info: dict):
    """PUT with invalid conclusion should return 422"""
    resp = await client.put(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=_headers(auth_token),
        json={"project_id": wp_info["project_id"], "items": [
            {"item_id": "S03-001", "conclusion": "INVALID"}
        ]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_empty_items(client: AsyncClient, auth_token: str, wp_info: dict):
    """PUT with empty items should return empty list"""
    resp = await client.put(
        f"/api/workpapers/{wp_info['wp_id']}/checklist-responses",
        headers=_headers(auth_token),
        json={"project_id": wp_info["project_id"], "items": []},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data == []
