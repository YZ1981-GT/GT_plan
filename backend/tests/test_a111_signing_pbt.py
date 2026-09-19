"""Property-Based Tests for A1-11 Signing Control Form — Backend

Property 9: Data persistence round-trip (PUT → GET → verify consistency)
Conclusion whitelist validation (valid values pass, invalid values → 422)

Uses pre-generated random test data (5 examples each) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints (the app's DB engine
pool binds to one event loop; pytest-asyncio creates a new loop per async test function),
ALL test assertions are consolidated into a single async test function, following the
same pattern as test_checklist_responses.py. Random data is generated upfront to preserve
the PBT spirit (randomized inputs across different item_ids, conclusions, remarks).
"""
from __future__ import annotations

import random

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings as app_settings
from app.main import app


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Data Generation
# ═══════════════════════════════════════════════════════════════════════════════

# Valid A1-11 item_id suffixes (from design doc)
A111_ITEM_SUFFIXES = [
    "entity-name", "engagement-no", "entity-type", "industry",
    "biz-category", "first-engagement", "report-title", "recipient",
    "attachment-note", "sign-pm", "sign-partner", "sign-qc",
    "sign-eqcr", "sign-it", "sign-tax", "mgmt-dept", "mgmt-doc-no",
    "mgmt-cn-copies", "mgmt-en-copies", "mgmt-proofread", "mgmt-print",
    "mgmt-seal",
]

# Valid conclusion values for A1-11 prefix
VALID_CONCLUSIONS = ["Y", "N", "NA", "A", "B", "C"]

# Invalid conclusion values (not in whitelist)
INVALID_CONCLUSIONS = ["INVALID", "yes", "no", "maybe", "1", "TRUE", "x",
                       "YY", "nn", "abc", "D", "E", "中文无效"]

# Sample remark/wp_ref values
SAMPLE_REMARKS = [None, "", "测试备注", "remark text", "中文 text 123", "简短"]
SAMPLE_WP_REFS = [None, "", "2025-01-01", "D2-3", "A1-11", "2025-12-31"]


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of A1-11 items for round-trip testing."""
    k = random.randint(1, 5)
    suffixes = random.sample(A111_ITEM_SUFFIXES, k)
    return [
        {
            "item_id": f"A1-11-{suffix}",
            "conclusion": random.choice([None] + VALID_CONCLUSIONS),
            "remark": random.choice(SAMPLE_REMARKS),
            "wp_ref": random.choice(SAMPLE_WP_REFS),
        }
        for suffix in suffixes
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Single consolidated test function (avoids event loop issues)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a111_signing_pbt():
    """Property-Based Tests for A1-11 signing control form backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 9: Data persistence round-trip (5 random batches)
      **Validates: Requirements 4.1**
    - Conclusion whitelist: valid values accepted (5 random examples)
    - Conclusion whitelist: invalid values rejected 422 (5 random examples)
    - Conclusion whitelist: null always accepted (5 random examples)
    """
    from app.core.security import create_access_token

    # --- Setup: get admin user and a working paper ---
    engine = create_async_engine(app_settings.DATABASE_URL, pool_size=2, max_overflow=0)
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
            # ═══════════════════════════════════════════════════════════════════
            # Property 9: Data persistence round-trip (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                items = _generate_round_trip_batch()

                # PUT: save items
                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": items},
                )
                assert resp.status_code == 200, (
                    f"[round-trip #{i}] PUT failed: {resp.text}"
                )

                # GET: retrieve all items
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                )
                assert resp.status_code == 200
                body = resp.json()
                data = body.get("data", body)

                # Build lookup by item_id
                saved_map = {item["item_id"]: item for item in data}

                # Verify each PUT item is correctly preserved in GET
                for item in items:
                    assert item["item_id"] in saved_map, (
                        f"[round-trip #{i}] item_id '{item['item_id']}' "
                        f"not found in GET response"
                    )
                    saved = saved_map[item["item_id"]]
                    assert saved["conclusion"] == item["conclusion"], (
                        f"[round-trip #{i}] conclusion mismatch for "
                        f"{item['item_id']}: expected {item['conclusion']!r}, "
                        f"got {saved['conclusion']!r}"
                    )
                    assert saved["remark"] == item["remark"], (
                        f"[round-trip #{i}] remark mismatch for "
                        f"{item['item_id']}: expected {item['remark']!r}, "
                        f"got {saved['remark']!r}"
                    )
                    assert saved["wp_ref"] == item["wp_ref"], (
                        f"[round-trip #{i}] wp_ref mismatch for "
                        f"{item['item_id']}: expected {item['wp_ref']!r}, "
                        f"got {saved['wp_ref']!r}"
                    )

            # ═══════════════════════════════════════════════════════════════════
            # Conclusion whitelist: valid values accepted (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                suffix = random.choice(A111_ITEM_SUFFIXES)
                conclusion = random.choice(VALID_CONCLUSIONS)
                item_id = f"A1-11-{suffix}"

                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": conclusion}
                    ]},
                )
                assert resp.status_code == 200, (
                    f"[valid #{i}] conclusion '{conclusion}' for '{item_id}' "
                    f"rejected: {resp.text}"
                )

            # ═══════════════════════════════════════════════════════════════════
            # Conclusion whitelist: invalid values rejected 422 (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                suffix = random.choice(A111_ITEM_SUFFIXES)
                conclusion = random.choice(INVALID_CONCLUSIONS)
                item_id = f"A1-11-{suffix}"

                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": conclusion}
                    ]},
                )
                assert resp.status_code == 422, (
                    f"[invalid #{i}] conclusion '{conclusion}' for '{item_id}' "
                    f"was accepted (expected 422, got {resp.status_code}): "
                    f"{resp.text}"
                )

            # ═══════════════════════════════════════════════════════════════════
            # Conclusion whitelist: null always accepted (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                suffix = random.choice(A111_ITEM_SUFFIXES)
                item_id = f"A1-11-{suffix}"

                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": None}
                    ]},
                )
                assert resp.status_code == 200, (
                    f"[null #{i}] null conclusion for '{item_id}' "
                    f"rejected: {resp.text}"
                )

        finally:
            # Cleanup all A1-11 test data
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'A1-11-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
