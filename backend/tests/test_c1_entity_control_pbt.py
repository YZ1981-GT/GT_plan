"""Property-Based Tests for C1 企业层面控制测试 — Backend

Feature: c1-entity-level-control, Property 5: 数据持久化往返一致性

Property 5: For any valid C1- prefixed data, after PUT save then GET load,
all field values (conclusion, remark) equal the pre-save values.

**Validates: Requirements 7.1, 7.4**

Uses pre-generated random test data (5 examples per project PBT convention for
the checklist-responses live DB round-trip; hypothesis @given is reserved in this
repo for pure-function properties, while the async+asyncpg endpoint round-trip
follows the D-series consolidated single-test pattern to avoid Windows asyncpg
event-loop constraints — see test_d2_accounts_receivable_pbt.py).

Isolation note: importing `app.main` pulls in the router_registry →
`_d4_contract_ocr` chain which requires the (pre-existing, uninstalled) `aiofiles`
module and blocks collection. To keep this round-trip test runnable, we mount ONLY
the `checklist_responses` router on a minimal FastAPI app and override
`get_current_user`. This exercises the real PUT/GET UPSERT + C1- validation +
live PostgreSQL persistence without importing the blocked chain.

Requires a running PostgreSQL database with at least one working_paper row.
"""
from __future__ import annotations

import random
import string
import types

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings as app_settings
from app.deps import get_current_user
from app.routers.checklist_responses import router as checklist_router


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Data Generation
# ═══════════════════════════════════════════════════════════════════════════════

# Valid C1- conclusion values (from checklist_responses.py C1- branch whitelist)
VALID_C1_CONCLUSIONS = [
    "Y", "N", "NA",
    "有效", "部分有效", "无效",
    "控制有效运行", "控制存在偏差但可接受", "控制无效",
    "询问", "观察", "检查", "重新执行", "抽样", "询问和观察",
    "每笔", "每日", "每周", "每月", "每季", "每年",
    "每月一次", "每季一次", "每年一次", "根据需要", "不定期",
    "已执行", "尚未执行",
]

# 九段 slug (phase0-notes.md §3 / §6.1)
C1_SECTIONS = ["ce", "ra", "mo", "bu", "ic", "fr", "el", "ye", "rp"]

# 过程记录字段 slug (phase0-notes.md §5)
C1_PROCESS_FIELDS = [
    "activity", "process", "materiality", "control", "custDesc", "custCode",
    "freq", "execDate", "processOwner", "controlOwner", "interviewee",
    "interviewDate", "testMethod", "howTest", "testResult",
]

# 样本列 slug (phase0-notes.md §6.4)
C1_SAMPLE_COLS = ["date", "account", "ref", "desc", "debit", "credit"]

# Sample remark values
SAMPLE_REMARKS = [
    None, "", "测试备注", "企业层面控制测试说明", "控制环境有效",
    "会计分录人工授权样本", "过程记录：询问和观察", "识别缺陷摘要",
]


def _random_c1_item_id() -> str:
    """Generate a random C1- item_id following phase0-notes.md §6 patterns.

    Uses high index range (900+) and random suffixes to avoid collision
    between test iterations and with real data.
    """
    rand_idx = random.randint(900, 999)
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    sec = random.choice(C1_SECTIONS)

    pattern_choice = random.randint(0, 8)

    if pattern_choice == 0:
        # 步骤适用性/执行人/结果说明/索引号: C1-{sec}-{step}-{field}
        field = random.choice(["applicable", "executor", "result", "index"])
        return f"C1-{sec}-{rand_idx}-{field}"
    elif pattern_choice == 1:
        # 整段适用性: C1-{sec}-section-applicable
        return f"C1-{sec}-section-applicable-{rand_suffix}"
    elif pattern_choice == 2:
        # 各段结论: C1-{sec}-conclusion
        return f"C1-{sec}-conclusion-{rand_suffix}"
    elif pattern_choice == 3:
        # 财报内控汇总: C1-4-summary-{n}-{field}
        n = random.randint(1, 6)
        field = random.choice(["control", "desc", "result", "conclusion"])
        return f"C1-4-summary-{n}-{field}-{rand_idx}"
    elif pattern_choice == 4:
        # 过程记录字段: C1-4-{k}-{field}
        k = random.randint(1, 6)
        field = random.choice(C1_PROCESS_FIELDS)
        return f"C1-4-{k}-{field}-{rand_idx}"
    elif pattern_choice == 5:
        # 样本明细: C1-4-4-sample-{row}-{col}
        col = random.choice(C1_SAMPLE_COLS)
        return f"C1-4-4-sample-{rand_idx}-{col}"
    elif pattern_choice == 6:
        # 样本附件: C1-4-4-sample-{row}-attach
        return f"C1-4-4-sample-{rand_idx}-attach"
    elif pattern_choice == 7:
        # 企业层面整体结论: C1-overall-conclusion
        return f"C1-overall-conclusion-{rand_suffix}"
    else:
        # 识别缺陷摘要: C1-defect-{d}-summary
        return f"C1-defect-{rand_idx}-summary"


def _generate_round_trip_batch() -> list[dict]:
    """Generate a random batch of C1- items for round-trip testing."""
    k = random.randint(1, 5)
    return [
        {
            "item_id": _random_c1_item_id(),
            "conclusion": random.choice([None] + VALID_C1_CONCLUSIONS),
            "remark": random.choice(SAMPLE_REMARKS),
        }
        for _ in range(k)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Single consolidated test function (avoids event loop issues)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_c1_entity_control_pbt():
    """Property 5: 数据持久化往返一致性 (round-trip) for C1 企业层面控制测试.

    Feature: c1-entity-level-control, Property 5: 数据持久化往返一致性

    For any valid C1- prefixed data, PUT save then GET load returns identical
    conclusion + remark values (5 random batches).

    **Validates: Requirements 7.1, 7.4**
    """
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

    wp_id = str(wp_row.id)
    project_id = str(wp_row.project_id)

    # --- Minimal app: mount only the checklist_responses router ---
    # (avoids app.main → router_registry → _d4_contract_ocr → aiofiles chain)
    admin_user = types.SimpleNamespace(id=user_row.id)

    test_app = FastAPI()
    test_app.include_router(checklist_router)
    test_app.dependency_overrides[get_current_user] = lambda: admin_user

    headers: dict[str, str] = {}
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # ═══════════════════════════════════════════════════════════════════
            # Property 5: Data persistence round-trip (max_examples=5)
            # **Validates: Requirements 7.1, 7.4**
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
                # Minimal app has no ResponseWrapper middleware → raw list;
                # tolerate both wrapped ({"data": [...]}) and raw list shapes.
                data = body["data"] if isinstance(body, dict) else body

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

        finally:
            # Cleanup all C1- test data created by this test
            cleanup_engine = create_async_engine(
                app_settings.DATABASE_URL, pool_size=1
            )
            try:
                async with cleanup_engine.begin() as conn:
                    await conn.execute(text(
                        "DELETE FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id LIKE 'C1-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
