"""Tests for checklist_responses router — V085 CRUD endpoints

Validates: Requirements 2.2, 2.3

Note: Uses a single test function to avoid event loop re-creation issues
with asyncpg connection pool on Windows (pytest-asyncio creates new loop per test).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_checklist_responses_crud():
    """Full CRUD test: GET empty, PUT batch, GET verify, UPSERT, invalid conclusion, empty items"""
    from app.core.security import create_access_token

    # Setup: get admin user id and a working paper
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2, max_overflow=0)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text(
                "SELECT id FROM users WHERE username = 'admin' AND is_active = true LIMIT 1"
            ))
            user_row = r.fetchone()

            r2 = await conn.execute(text(
                "SELECT id, project_id FROM working_paper LIMIT 1"
            ))
            wp_row = r2.fetchone()
    finally:
        await engine.dispose()

    if user_row is None:
        pytest.skip("No admin user in DB")
    if wp_row is None:
        pytest.skip("No working_paper in DB")

    token = create_access_token({"sub": str(user_row.id), "type": "access"})
    headers = {"Authorization": f"Bearer {token}"}
    wp_id = str(wp_row.id)
    project_id = str(wp_row.project_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # --- Test 1: GET empty ---
            resp = await client.get(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            assert isinstance(data, list)

            # --- Test 2: PUT batch save ---
            items = [
                {"item_id": "S01-001", "conclusion": "Y", "remark": "test", "wp_ref": "D2-3"},
                {"item_id": "S01-002", "conclusion": "N", "remark": None, "wp_ref": None},
                {"item_id": "TOC-S01", "conclusion": "Y", "remark": None, "wp_ref": None},
            ]
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"project_id": project_id, "items": items},
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            assert len(data) == 3

            # --- Test 3: GET verify saved data ---
            resp = await client.get(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            item_ids = {item["item_id"] for item in data}
            assert "S01-001" in item_ids
            assert "S01-002" in item_ids
            assert "TOC-S01" in item_ids

            s01_001 = next(i for i in data if i["item_id"] == "S01-001")
            assert s01_001["conclusion"] == "Y"
            assert s01_001["remark"] == "test"
            assert s01_001["wp_ref"] == "D2-3"

            # --- Test 4: UPSERT (update existing) ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"project_id": project_id, "items": [
                    {"item_id": "S01-001", "conclusion": "NA", "remark": "v2"}
                ]},
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            assert len(data) == 1
            assert data[0]["conclusion"] == "NA"
            assert data[0]["remark"] == "v2"

            # --- Test 5: Invalid conclusion ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"project_id": project_id, "items": [
                    {"item_id": "S99-001", "conclusion": "INVALID"}
                ]},
            )
            assert resp.status_code == 422

            # --- Test 6: Empty items ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"project_id": project_id, "items": []},
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            assert data == []

        finally:
            # Cleanup
            cleanup_engine = create_async_engine(
                settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses WHERE wp_id = :wp_id"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
