"""Property-Based Tests for B50 重大错报风险评估 — Backend

Property 7: Data persistence round-trip (PUT → GET → verify consistency)
Conclusion whitelist validation (valid values → 200, invalid values → 422, null → 200)

Uses pre-generated random test data (5 examples each) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints (the app's DB engine
pool binds to one event loop; pytest-asyncio creates a new loop per async test function),
ALL test assertions are consolidated into a single async test function, following the
same pattern as test_a111_signing_pbt.py. Random data is generated upfront to preserve
the PBT spirit (randomized inputs across different item_ids, conclusions, remarks).

**Validates: Requirements 8.1, 8.5, 8.6**
"""
from __future__ import annotations

import random
import string

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings as app_settings
from app.main import app


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Data Generation
# ═══════════════════════════════════════════════════════════════════════════════

# B50 item_id patterns (from design doc)
B50_TAB_PREFIXES = ["T1", "T2", "T3", "T4"]
B50_FIELD_SUFFIXES = [
    "factor-1-desc", "factor-1-source", "factor-2-risk", "factor-1-transferred",
    "fs-1-level", "fs-1-category", "fs-2-response",
    "matrix-收入确认-existence-IR", "matrix-收入确认-completeness-CR",
    "matrix-管理层凌驾控制-accuracy-RMM", "matrix-应收账款-cutoff-SR",
    "sr-收入确认-existence-response",
]

# Valid conclusion values for B50- prefix (from design doc / checklist_responses.py)
VALID_CONCLUSIONS = [
    "H", "M", "L",  # risk levels
    "Y", "N", "NA",  # signing/marks
    "B22A", "B23", "industry", "discussion",
    "prior_audit", "management_interview", "other",  # source types
    "control_env", "management_integrity",
    "economic_env", "industry_factor",  # risk categories
]

# Invalid conclusion values (not in whitelist)
INVALID_CONCLUSIONS = [
    "INVALID", "yes", "no", "maybe", "1", "TRUE", "x",
    "HIGH", "MEDIUM", "LOW", "中文无效", "abc123", "XX",
]

# Sample remark/wp_ref values
SAMPLE_REMARKS = [None, "", "测试备注", "细节测试描述", "中文 text 123", "应对程序"]
SAMPLE_WP_REFS = [None, "", "2025-01-01", "D2-3", "B50", "2025-12-31"]


def _random_b50_item_id() -> str:
    """Generate a random B50- item_id following design patterns."""
    tab = random.choice(B50_TAB_PREFIXES)
    suffix = random.choice(B50_FIELD_SUFFIXES)
    # Add a random numeric component to ensure uniqueness across runs
    rand_suffix = ''.join(random.choices(string.digits, k=3))
    return f"B50-{tab}-test-{rand_suffix}-{suffix}"


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of B50- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_b50_item_id(),
            "conclusion": random.choice([None] + VALID_CONCLUSIONS),
            "remark": random.choice(SAMPLE_REMARKS),
            "wp_ref": random.choice(SAMPLE_WP_REFS),
        }
        for _ in range(k)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Single consolidated test function (avoids event loop issues)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_b50_risk_assessment_pbt():
    """Property-Based Tests for B50 risk assessment backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 7: Data persistence round-trip (5 random batches)
      **Validates: Requirements 8.1, 8.5, 8.6**
    - Conclusion whitelist: valid values accepted (5 random examples)
      **Validates: Requirements 8.1（后端校验分支）**
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
            # Property 7: Data persistence round-trip (max_examples=5)
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
                conclusion = random.choice(VALID_CONCLUSIONS)
                item_id = _random_b50_item_id()

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
                conclusion = random.choice(INVALID_CONCLUSIONS)
                item_id = _random_b50_item_id()

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
                item_id = _random_b50_item_id()

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
            # Cleanup all B50- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'B50-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
