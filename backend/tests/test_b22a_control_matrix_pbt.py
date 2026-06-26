"""Property-Based Tests for B22A 内部控制了解程序表 — Backend

Property 8: Data persistence round-trip (PUT → GET → verify consistency)
Conclusion whitelist validation (valid values → 200, invalid values → 422, null → 200)

Uses pre-generated random test data (5 examples each) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints, ALL test assertions
are consolidated into a single async test function, following the same pattern as
test_b50_risk_assessment_pbt.py.

**Validates: Requirements 9.1, 9.5, 9.6**
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

# B22A item_id patterns (from design doc)
B22A_TAB_PREFIXES = ["T1", "T2", "T3", "T4", "T5"]
B22A_FIELD_SUFFIXES = [
    "item-1-point", "item-1-desc", "item-1-method", "item-1-conclusion",
    "item-1-ref", "item-2-point", "item-2-conclusion", "item-3-conclusion",
    "count", "note", "score", "score-override",
]
B22A_IT_PANELS = ["env", "itgc", "app", "change", "access", "sod"]
B22A_SUMMARY_IDS = ["B22A-SUM-overall", "B22A-SUM-note", "B22A-review-sign"]

# Valid conclusion values for B22A- prefix (from design / checklist_responses.py)
VALID_CONCLUSIONS = [
    "设计有效", "设计无效", "已实施", "未实施", "不适用",  # Conclusion
    "Y", "N", "NA",                                      # 签字/标记
    "有效", "部分有效", "无效",                            # Element_Score
    "高", "中", "低",                                     # IT_Dependency
]

# Invalid conclusion values (not in B22A whitelist)
INVALID_CONCLUSIONS = [
    "INVALID", "yes", "no", "maybe", "H", "M", "L",
    "HIGH", "有效果", "无效果", "abc123", "XX", "TRUE",
]

# Sample remark/wp_ref values
SAMPLE_REMARKS = [None, "", "测试备注", "询问,观察,检查文件", "了解情况", "控制要点描述"]
SAMPLE_WP_REFS = [None, "", "2026-01-15", "B22A-ref", "2026-06-23"]


def _random_b22a_item_id() -> str:
    """Generate a random B22A- item_id following design patterns."""
    rand_suffix = ''.join(random.choices(string.digits, k=3))
    pattern = random.choice([
        # Regular tab items
        lambda: f"B22A-{random.choice(B22A_TAB_PREFIXES)}-test-{rand_suffix}-{random.choice(B22A_FIELD_SUFFIXES)}",
        # IT sub-panel items
        lambda: f"B22A-T4-IT-{random.choice(B22A_IT_PANELS)}-test-{rand_suffix}-conclusion",
        # Summary/review items
        lambda: f"B22A-test-{rand_suffix}-misc",
    ])
    return pattern()


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of B22A- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_b22a_item_id(),
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
async def test_b22a_control_matrix_pbt():
    """Property-Based Tests for B22A control matrix backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 8: Data persistence round-trip (5 random batches)
      **Validates: Requirements 9.1, 9.5, 9.6**
    - Conclusion whitelist: valid values accepted (5 random examples)
      **Validates: Requirements 9.1（后端校验分支）**
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
            # Conclusion whitelist: valid values accepted (max_examples=5)
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(VALID_CONCLUSIONS)
                item_id = _random_b22a_item_id()

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
                item_id = _random_b22a_item_id()

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
                item_id = _random_b22a_item_id()

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
            # Cleanup all B22A- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'B22A-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
