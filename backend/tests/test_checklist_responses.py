"""Tests for the checklist response API contract.

Validates: Requirements 4.1-4.6

Note: Uses a single database test function to avoid event loop re-creation issues
with asyncpg connection pool on Windows (pytest-asyncio creates new loop per test).
"""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_checklist_responses_crud(monkeypatch):
    """CRUD + version/conflict/atomic/event contract for Requirements 4.1-4.6."""
    from app.core.security import create_access_token
    from app.services.event_bus import event_bus

    publish_mock = AsyncMock()
    monkeypatch.setattr(event_bus, "publish", publish_mock)

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
            if wp_row is not None:
                await conn.execute(text("""
                    DELETE FROM checklist_responses
                    WHERE wp_id = :wp_id
                      AND item_id = ANY(:item_ids)
                """), {
                    "wp_id": str(wp_row.id),
                    "item_ids": [
                        "S01-001", "S01-002", "TOC-S01",
                        "SPEC-ATOMIC-OK", "SPEC-ATOMIC-BAD",
                        "SPEC-EVENT-COMMIT",
                    ],
                })
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
                {"item_id": "S01-002", "conclusion": "N/A", "remark": None, "wp_ref": None},
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
            assert all(item["version"] for item in data)
            assert all(item["overwritten"] is False for item in data)
            initial_version = data[0]["version"]
            assert publish_mock.await_count == 1
            event_payload = publish_mock.await_args.args[0]
            assert event_payload.extra["trigger"] == "checklist_response_save"
            assert event_payload.extra["atomic"] is True

            # --- Test 3: GET verify saved data + stable version/ETag ---
            resp = await client.get(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.headers["etag"].startswith('W/"')
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
            assert s01_001["version"] == initial_version

            # --- Test 4: no if_match keeps LWW compatibility and reports overwrite ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"items": [
                    {"item_id": "S01-001", "conclusion": "N/A", "remark": "v2"}
                ]},
            )
            assert resp.status_code == 200
            body = resp.json()
            data = body.get("data", body)
            assert len(data) == 1
            assert data[0]["conclusion"] == "N/A"
            assert data[0]["remark"] == "v2"
            assert data[0]["overwritten"] is True
            version_v2 = data[0]["version"]

            # --- Test 5: matching if_match succeeds; stale version returns atomic 409 ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"items": [{
                    "item_id": "S01-001",
                    "conclusion": "Y",
                    "remark": "v3",
                    "if_match": version_v2,
                }]},
            )
            assert resp.status_code == 200
            matched = resp.json().get("data", resp.json())[0]
            assert matched["overwritten"] is False

            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"items": [{
                    "item_id": "S01-001",
                    "conclusion": "N",
                    "remark": "stale-write",
                    "if_match": version_v2,
                }]},
            )
            assert resp.status_code == 409
            conflict_body = resp.json()
            conflict = conflict_body.get("detail", conflict_body.get("message"))
            assert conflict["code"] == "version_conflict"
            assert conflict["item_id"] == "S01-001"
            assert conflict["atomic"] is True

            # --- Test 6: invalid item rolls back the entire batch and identifies item_id ---
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"items": [
                    {"item_id": "SPEC-ATOMIC-OK", "conclusion": "Y"},
                    {"item_id": "SPEC-ATOMIC-BAD", "conclusion": "INVALID"},
                ]},
            )
            assert resp.status_code == 422
            validation_body = resp.json()
            validation = validation_body.get("detail", validation_body.get("message"))
            assert validation["item_id"] == "SPEC-ATOMIC-BAD"
            assert validation["atomic"] is True

            resp = await client.get(
                f"/api/workpapers/{wp_id}/checklist-responses", headers=headers
            )
            persisted = resp.json().get("data", resp.json())
            assert all(item["item_id"] != "SPEC-ATOMIC-OK" for item in persisted)
            saved = next(item for item in persisted if item["item_id"] == "S01-001")
            assert saved["remark"] == "v3"

            # --- Test 7: event failure is post-commit and cannot roll back data ---
            publish_mock.side_effect = RuntimeError("event unavailable")
            resp = await client.put(
                f"/api/workpapers/{wp_id}/checklist-responses",
                headers=headers,
                json={"items": [{
                    "item_id": "SPEC-EVENT-COMMIT",
                    "conclusion": "Y",
                    "remark": "committed",
                }]},
            )
            assert resp.status_code == 200
            resp = await client.get(
                f"/api/workpapers/{wp_id}/checklist-responses", headers=headers
            )
            persisted = resp.json().get("data", resp.json())
            event_item = next(
                item for item in persisted if item["item_id"] == "SPEC-EVENT-COMMIT"
            )
            assert event_item["remark"] == "committed"

            # --- Test 8: Empty items ---
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
                    await conn.execute(text("""
                        DELETE FROM checklist_responses
                        WHERE wp_id = :wp_id
                          AND item_id = ANY(:item_ids)
                    """), {
                        "wp_id": wp_id,
                        "item_ids": [
                            "S01-001", "S01-002", "TOC-S01",
                            "SPEC-ATOMIC-OK", "SPEC-ATOMIC-BAD",
                            "SPEC-EVENT-COMMIT",
                        ],
                    })
            finally:
                await cleanup_engine.dispose()


def test_checklist_put_uses_general_workpaper_edit_guard():
    """PUT contract is wired to the shared workpaper edit permission dependency."""
    from app.routers.checklist_responses import batch_save_checklist_responses

    dependency = inspect.signature(batch_save_checklist_responses).parameters[
        "current_user"
    ].default.dependency
    assert "require_wp_edit_permission" in dependency.__qualname__


@pytest.mark.asyncio
async def test_shared_edit_guard_rejects_readonly_before_database_access():
    """The shared edit guard rejects a non-editor before any write-side DB work."""
    from app.deps import require_wp_edit_permission

    dependency = require_wp_edit_permission()
    readonly_user = SimpleNamespace(
        id=uuid.uuid4(),
        role=SimpleNamespace(value="readonly"),
    )
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await dependency(
            wp_id=uuid.uuid4(),
            current_user=readonly_user,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "无底稿编辑权限"
    db.execute.assert_not_awaited()
