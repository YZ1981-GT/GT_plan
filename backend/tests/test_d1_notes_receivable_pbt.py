"""Property-Based Tests for D1 应收票据 — Backend

Property 7: Data persistence round-trip (PUT → GET → verify consistency)
Property 12: Conclusion whitelist validation (valid values → 200, invalid → 422)

Uses pre-generated random test data (5 examples each) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints, ALL test assertions
are consolidated into a single async test function, following the same pattern as
test_b23_process_control_pbt.py.

**Validates: Requirements 11.6, 13.1, 13.2, 13.4**
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

# Valid D1- conclusion values (from checklist_responses.py D1- branch)
VALID_D1_CONCLUSIONS = [
    "未开始", "执行中", "已完成", "不适用",
    "符合", "不符合",
    "以摊余成本计量", "以公允价值计量且变动计入其他综合收益",
    "以公允价值计量且变动计入当期损益",
    "终止确认", "不终止确认",
    "已披露且准确", "已披露但需修改", "未披露需补充",
    "组合评估", "个别认定",
    "AJE", "RJE",
    "listed", "soe", "general",
    "Y", "N", "是", "否",
    "合理", "基本合理但需关注", "不合理",
]

# Invalid conclusion values (not in D1 whitelist)
INVALID_D1_CONCLUSIONS = [
    "INVALID", "yes", "no", "maybe", "H", "M", "L",
    "HIGH", "有效", "部分有效", "无效", "abc123",
    "设计有效", "已实施", "未实施", "XX", "TRUE",
    "重大缺陷", "重要缺陷", "一般缺陷",
    "控制有效运行", "控制无效", "每月",
]

# D1- item_id section prefixes (from design doc item_id naming convention)
D1_SECTIONS = [
    "proc", "adj", "ecl", "entry", "sppi", "biz",
    "endorse", "interest", "inventory", "rp", "pledge",
    "check", "policy", "writeoff", "disc", "review",
]

# Sample remark values
SAMPLE_REMARKS = [None, "", "测试备注", "应收票据检查说明", "ECL测试数据", "审计师复核意见"]


def _random_d1_item_id() -> str:
    """Generate a random D1- item_id following design patterns.

    Uses high index range (900+) and random suffixes to avoid collision
    between test iterations and with real data.
    """
    section = random.choice(D1_SECTIONS)
    rand_idx = random.randint(900, 999)
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

    pattern_choice = random.randint(0, 3)

    if pattern_choice == 0:
        # Simple section-index pattern: D1-{section}-{n}
        return f"D1-{section}-{rand_idx}-{rand_suffix}"
    elif pattern_choice == 1:
        # Section with field: D1-{section}-{n}-{field}
        fields = ["status", "conclusion", "amount", "remark", "date", "balance", "rate"]
        field = random.choice(fields)
        return f"D1-{section}-{rand_idx}-{field}"
    elif pattern_choice == 2:
        # Nested pattern: D1-{section}-{n}-{m}-{field}
        sub_idx = random.randint(1, 5)
        fields = ["amount", "type", "desc", "value"]
        field = random.choice(fields)
        return f"D1-{section}-{rand_idx}-{sub_idx}-{field}"
    else:
        # Test-specific unique pattern
        return f"D1-{section}-test-{rand_suffix}-{rand_idx}"


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of D1- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_d1_item_id(),
            "conclusion": random.choice([None] + VALID_D1_CONCLUSIONS),
            "remark": random.choice(SAMPLE_REMARKS),
        }
        for _ in range(k)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Single consolidated test function (avoids event loop issues)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_d1_notes_receivable_pbt():
    """Property-Based Tests for D1 应收票据 backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 7: Data persistence round-trip (5 random batches)
      **Validates: Requirements 11.6**
    - Property 12: Conclusion whitelist — valid values accepted (5 random examples)
      **Validates: Requirements 13.1, 13.2, 13.4**
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
            # Property 7: Data persistence round-trip (max_examples=5)
            # **Validates: Requirements 11.6**
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

            # ═══════════════════════════════════════════════════════════════════
            # Property 12: valid conclusions accepted (max_examples=5)
            # **Validates: Requirements 13.1, 13.2, 13.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(VALID_D1_CONCLUSIONS)
                item_id = _random_d1_item_id()

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
            # **Validates: Requirements 13.1, 13.2, 13.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(INVALID_D1_CONCLUSIONS)
                item_id = _random_d1_item_id()

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
            # **Validates: Requirements 13.1, 13.2, 13.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                item_id = _random_d1_item_id()

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
            # Cleanup all D1- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'D1-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
