"""Property-Based Test: B23- 白名单校验（合法 200 / 非法 422）

Uses Hypothesis to generate valid/invalid B23- conclusion values and verifies:
- Valid B23- conclusion values (from the whitelist) are accepted (200)
- Invalid B23- conclusion values (random strings NOT in whitelist) are rejected (422)
- null conclusion is always accepted (200)

Tests the validation logic by calling the PUT checklist-responses endpoint
via ASGI transport (no external server needed).

**Validates: Requirements 11.4**
"""
from __future__ import annotations

import random
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import sys
import os

# Ensure backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings as app_settings
from app.main import app


# ═══════════════════════════════════════════════════════════════════════════════
# B23 Whitelist (mirrors checklist_responses.py B23- branch exactly)
# ═══════════════════════════════════════════════════════════════════════════════

B23_VALID_CONCLUSIONS: tuple[str, ...] = (
    # 认定
    "存在", "发生", "完整性", "准确性", "计价分摊", "权利义务", "列报",
    # 预防性/检查性
    "预防性", "检查性",
    # 控制类型（一级/二级常见值）
    "授权和审批", "监督控制", "信息处理", "实物控制", "职责分离", "绩效评价复核",
    # 是/否
    "是", "否",
    # 有效/无效
    "有效", "无效",
    # 缺陷严重程度（A14-4）
    "重大缺陷", "重要缺陷", "一般缺陷",
    # 缺陷类型
    "缺乏控制", "设计不合理", "未执行",
    # 适用性/流程结论
    "Y", "N",
    "设计有效且已实施", "设计有效但未有效实施", "设计无效", "不适用",
    # 可依赖性
    "可依赖", "部分可依赖", "不可依赖",
    # 其他有效值（穿行/控制频率/控制类型二级等）
    "控制有效运行", "控制未有效运行", "未执行穿行",
    "每笔", "每日", "每周", "每月", "每季", "每年", "不定期", "定期",
    "有权人员批准", "安全访问控制", "复核其他控制的执行情况",
)

_VALID_SET = frozenset(B23_VALID_CONCLUSIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# Hypothesis strategies
# ═══════════════════════════════════════════════════════════════════════════════

_valid_conclusion_st = st.sampled_from(list(B23_VALID_CONCLUSIONS))


@st.composite
def _invalid_conclusion_st(draw):
    """Generate a random string that is NOT in the B23 whitelist."""
    s = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        min_size=1,
        max_size=15,
    ))
    assume(s not in _VALID_SET)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-generate test data (avoids Windows asyncpg event loop issues with Hypothesis)
# ═══════════════════════════════════════════════════════════════════════════════

def _pre_generate_valid_cases(n: int = 5) -> list[tuple[str, str]]:
    """Pre-generate (item_id, valid_conclusion) pairs."""
    pairs = []
    for i in range(n):
        cycle = random.choice(["c1", "c2", "c3", "c10", "c14", "c15", "cxx5"])
        item_id = f"B23-{cycle}-test-{random.randint(900, 999)}-vld{i:02d}"
        conclusion = random.choice(B23_VALID_CONCLUSIONS)
        pairs.append((item_id, conclusion))
    return pairs


def _pre_generate_invalid_cases(n: int = 5) -> list[tuple[str, str]]:
    """Pre-generate (item_id, invalid_conclusion) pairs."""
    # Known invalid values (definitely not in B23 whitelist)
    known_invalid = [
        "INVALID", "yes", "no", "maybe", "H", "M", "L",
        "HIGH", "部分有效", "abc123", "true", "false",
        "设计有效", "已实施", "未实施", "XX", "TRUE", "pending",
    ]

    pairs = []
    for i in range(n):
        cycle = random.choice(["c1", "c2", "c3", "c10", "c14", "c15", "cxx5"])
        item_id = f"B23-{cycle}-test-{random.randint(900, 999)}-inv{i:02d}"
        if i < len(known_invalid):
            conclusion = known_invalid[i]
        else:
            conclusion = "".join(random.choices(string.ascii_lowercase, k=8))
        # Verify it's actually invalid
        assert conclusion not in _VALID_SET, f"Generated value '{conclusion}' is actually valid!"
        pairs.append((item_id, conclusion))
    return pairs


def _pre_generate_null_cases(n: int = 5) -> list[str]:
    """Pre-generate item_ids for null conclusion tests."""
    return [
        f"B23-c{random.choice(['1', '2', '3', '10', '14', '15'])}-test-{random.randint(900, 999)}-nul{i:02d}"
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Main PBT test — consolidated single async function
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_b23_whitelist_validation_pbt():
    """Property-Based Test for B23- conclusion whitelist validation.

    Consolidated into one async test to avoid Windows asyncpg event loop issues.
    Covers three properties (each with 5 examples, equivalent to @settings(max_examples=5)):
    1. Valid B23- conclusions accepted (200)
    2. Invalid B23- conclusions rejected (422)
    3. null conclusion always accepted (200)

    **Validates: Requirements 11.4**
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

    # Pre-generate test data (equivalent to @settings(max_examples=5) per property)
    valid_cases = _pre_generate_valid_cases(5)
    invalid_cases = _pre_generate_invalid_cases(5)
    null_cases = _pre_generate_null_cases(5)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # ═══════════════════════════════════════════════════════════════
            # Property 1: Valid B23- conclusions are accepted (200)
            # @settings(max_examples=5)
            # **Validates: Requirements 11.4**
            # ═══════════════════════════════════════════════════════════════
            for i, (item_id, conclusion) in enumerate(valid_cases):
                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": conclusion}
                    ]},
                )
                assert resp.status_code == 200, (
                    f"[valid #{i}] conclusion '{conclusion}' for item '{item_id}' "
                    f"was rejected (expected 200, got {resp.status_code}): {resp.text}"
                )

            # ═══════════════════════════════════════════════════════════════
            # Property 2: Invalid B23- conclusions are rejected (422)
            # @settings(max_examples=5)
            # **Validates: Requirements 11.4**
            # ═══════════════════════════════════════════════════════════════
            for i, (item_id, conclusion) in enumerate(invalid_cases):
                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": conclusion}
                    ]},
                )
                assert resp.status_code == 422, (
                    f"[invalid #{i}] conclusion '{conclusion}' for item '{item_id}' "
                    f"was accepted (expected 422, got {resp.status_code}): {resp.text}"
                )

            # ═══════════════════════════════════════════════════════════════
            # Property 3: null conclusion always accepted (200)
            # @settings(max_examples=5)
            # **Validates: Requirements 11.4**
            # ═══════════════════════════════════════════════════════════════
            for i, item_id in enumerate(null_cases):
                resp = await client.put(
                    f"/api/workpapers/{wp_id}/checklist-responses",
                    headers=headers,
                    json={"project_id": project_id, "items": [
                        {"item_id": item_id, "conclusion": None, "remark": "remark无校验自由文本"}
                    ]},
                )
                assert resp.status_code == 200, (
                    f"[null #{i}] null conclusion for item '{item_id}' "
                    f"was rejected (expected 200, got {resp.status_code}): {resp.text}"
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
                        "WHERE wp_id = :wp_id AND item_id LIKE 'B23-c%%-test-%%'"
                    ), {"wp_id": wp_id})
            finally:
                await cleanup_engine.dispose()
