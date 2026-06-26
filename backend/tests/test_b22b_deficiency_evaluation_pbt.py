"""Property-Based Tests for B22B 内部控制缺陷评价表 — Backend

Property 8: Data persistence round-trip (PUT → GET → verify consistency)
Property 12: Conclusion whitelist validation (valid values → 200, invalid → 422, null → 200)

Uses pre-generated random test data (5 batches) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints, ALL test assertions
are consolidated into a single async test function, following the same pattern as
test_b22a_control_matrix_pbt.py.

**Validates: Requirements 7.1, 7.5, 7.6, 10.1, 10.2, 10.3, 10.4**
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

# B22B item_id patterns (from design doc)
B22B_FIELD_SUFFIXES = [
    "category", "accounts", "amount", "compensating",
    "corrective", "severity", "override", "source", "eliminated",
]
B22B_OVERALL_IDS = [
    "B22B-overall-conclusion", "B22B-overall-note",
    "B22B-def-count", "B22B-review-sign",
    "B22B-materiality-manual",
]

# Valid conclusion values for B22B- prefix (from design / checklist_responses.py)
VALID_CONCLUSIONS = [
    "重大缺陷", "重要缺陷", "一般缺陷",           # SeverityLevel
    "设计缺陷", "运行缺陷",                        # DeficiencyCategory
    "Y", "N",                                      # 签字/布尔标记
    "存在重大缺陷", "存在重要缺陷",                 # OverallConclusion
    "仅存在一般缺陷", "未发现控制缺陷",             # OverallConclusion
]

# Invalid conclusion values (not in B22B whitelist)
INVALID_CONCLUSIONS = [
    "INVALID", "yes", "no", "maybe", "H", "M", "L",
    "HIGH", "有效", "部分有效", "无效", "abc123",
    "设计有效", "已实施", "未实施", "不适用",
    "XX", "TRUE", "FALSE",
]

# Sample remark/wp_ref values
SAMPLE_REMARKS = [None, "", "测试备注", "资产,负债,收入", "补偿性控制描述", "500000"]
SAMPLE_WP_REFS = [None, "", "2026-01-15", "2026-06-23"]


def _random_b22b_item_id() -> str:
    """Generate a random B22B- item_id following design patterns.

    Uses high index range (900+) to avoid collision with real data.
    """
    rand_idx = random.randint(900, 999)
    rand_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
    pattern_choice = random.randint(0, 2)

    if pattern_choice == 0:
        # Deficiency item field
        field = random.choice(B22B_FIELD_SUFFIXES)
        return f"B22B-def-{rand_idx}-{field}"
    elif pattern_choice == 1:
        # Test-specific overall/misc items (use unique suffix to avoid collision)
        return f"B22B-test-{rand_suffix}-misc"
    else:
        # Amendment with high index
        amend_n = random.randint(900, 999)
        return f"B22B-amend-{amend_n}-reason"


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of B22B- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_b22b_item_id(),
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
async def test_b22b_deficiency_evaluation_pbt():
    """Property-Based Tests for B22B deficiency evaluation backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 8: Data persistence round-trip (5 random batches)
      **Validates: Requirements 7.1, 7.5, 7.6**
    - Property 12: Conclusion whitelist — valid values accepted (5 random examples)
      **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    - Property 12: Conclusion whitelist — invalid values rejected 422 (5 random examples)
    - Property 12: Conclusion whitelist — null always accepted (5 random examples)
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
            # Property 8: Data persistence round-trip (max_examples=5)
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
            # Property 12: valid conclusions accepted (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(VALID_CONCLUSIONS)
                item_id = _random_b22b_item_id()

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
            # Property 12: invalid conclusions rejected 422 (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(INVALID_CONCLUSIONS)
                # Use a def-field item_id to ensure B22B- prefix matching
                item_id = f"B22B-def-{random.randint(1, 50)}-severity"

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
            # Property 12: null conclusion always accepted (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                item_id = _random_b22b_item_id()

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
            # Cleanup all B22B- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'B22B-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
