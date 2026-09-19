"""Property-Based Tests for B23 业务流程与控制了解表 — Backend

Property 6: Data persistence round-trip (PUT → GET → verify consistency)
Property 11: Conclusion whitelist validation (valid values → 200, invalid → 422, null → 200)

Uses pre-generated random test data (5 examples each) per project PBT convention.
Requires a running PostgreSQL database with at least one working_paper row.

Architecture note: Due to Windows asyncpg event loop constraints, ALL test assertions
are consolidated into a single async test function, following the same pattern as
test_b22a_control_matrix_pbt.py.

**Validates: Requirements 8.1, 8.5, 8.6, 11.1, 11.2, 11.4**
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

# B23 item_id patterns (from design doc)
B23_PROCESS_NUMS = [1, 2, 3, 4, 5, 6, 7, 8]
B23_CTRL_FIELDS = [
    "objective", "description", "frequency", "executor",
    "methods", "conclusion", "remark",
]
B23_WT_FIELDS = ["sample", "path", "finding", "reference"]

# Valid conclusion values for B23- prefix (from checklist_responses.py，14 循环重做后扩展)
VALID_CONCLUSIONS = [
    "设计有效且已实施", "设计有效但未有效实施", "设计无效", "不适用",  # 循环/流程结论
    "控制有效运行", "控制未有效运行", "未执行穿行",                  # 穿行结论（旧）
    "有效", "无效",                                                  # 控制测试运行有效性
    "每笔", "每日", "每周", "每月", "每季", "每年", "不定期", "定期", # 控制频率
    "存在", "发生", "完整性", "准确性", "计价分摊", "权利义务", "列报",  # 认定
    "预防性", "检查性",                                              # 预防性/检查性
    "授权和审批", "监督控制", "信息处理", "实物控制", "职责分离", "绩效评价复核",  # 控制类型
    "有权人员批准", "安全访问控制", "复核其他控制的执行情况",         # 控制类型二级
    "缺乏控制", "设计不合理", "未执行",                              # 缺陷类型
    "重大缺陷", "重要缺陷", "一般缺陷",                              # 缺陷严重程度(A14-4)
    "是", "否", "Y", "N",                                            # 是否/签字/适用性
]

# Invalid conclusion values (not in B23 whitelist)
INVALID_CONCLUSIONS = [
    "INVALID", "yes", "no", "maybe", "H", "M", "L",
    "HIGH", "部分有效", "abc123",
    "设计有效", "已实施", "未实施", "XX", "TRUE",
]

# Sample remark/wp_ref values
SAMPLE_REMARKS = [None, "", "测试备注", "询问,观察,检查文件", "穿行测试路径描述", "控制目标文本"]
SAMPLE_WP_REFS = [None, "", "2026-01-15", "2026-06-23"]


def _random_b23_item_id() -> str:
    """Generate a random B23- item_id following design patterns.

    Uses high index range (900+) and random suffixes to avoid collision
    between test iterations and with real data.
    """
    process_num = random.choice(B23_PROCESS_NUMS)
    rand_idx = random.randint(900, 999)
    rand_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
    pattern_choice = random.randint(0, 3)

    if pattern_choice == 0:
        # Control point field: B23-P{n}-ctrl-{m}-{field}
        field = random.choice(B23_CTRL_FIELDS)
        return f"B23-P{process_num}-ctrl-{rand_idx}-{field}"
    elif pattern_choice == 1:
        # Walkthrough record: B23-P{n}-wt-{m}-{s}-{field}
        sample_idx = random.randint(1, 5)
        field = random.choice(B23_WT_FIELDS)
        return f"B23-P{process_num}-wt-{rand_idx}-{sample_idx}-{field}"
    elif pattern_choice == 2:
        # Misc test items with unique suffix
        return f"B23-P{process_num}-test-{rand_suffix}-{rand_idx}"
    else:
        # Another unique pattern
        return f"B23-test-{rand_suffix}-{rand_idx}-misc"


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of B23- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_b23_item_id(),
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
async def test_b23_process_control_pbt():
    """Property-Based Tests for B23 process control backend.

    Consolidated into one test function to avoid Windows asyncpg event loop issues.
    Contains:
    - Property 6: Data persistence round-trip (5 random batches)
      **Validates: Requirements 8.1, 8.5, 8.6**
    - Property 11: Conclusion whitelist — valid values accepted (5 random examples)
      **Validates: Requirements 11.1, 11.2, 11.4**
    - Property 11: Conclusion whitelist — invalid values rejected 422 (5 random examples)
    - Property 11: Conclusion whitelist — null always accepted (5 random examples)
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
            # Property 6: Data persistence round-trip (max_examples=5)
            # **Validates: Requirements 8.1, 8.5, 8.6**
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
            # Property 11: valid conclusions accepted (max_examples=5)
            # **Validates: Requirements 11.1, 11.2, 11.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(VALID_CONCLUSIONS)
                item_id = _random_b23_item_id()

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
            # Property 11: invalid conclusions rejected 422 (max_examples=5)
            # **Validates: Requirements 11.1, 11.2, 11.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                conclusion = random.choice(INVALID_CONCLUSIONS)
                item_id = _random_b23_item_id()

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
            # Property 11: null conclusion always accepted (max_examples=5)
            # **Validates: Requirements 11.1, 11.2, 11.4**
            # ═══════════════════════════════════════════════════════════════════
            for i in range(5):
                item_id = _random_b23_item_id()

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
            # Cleanup all B23- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'B23-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
