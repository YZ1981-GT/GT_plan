"""A10-1 与治理层沟通函 — Property-Based Tests.

Property 3: chapters array contains exactly 16 entries with sequential numbers 1-16.
Property 4: response schema has all 9 top-level keys with correct types.

**Validates: Requirements 10**
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a101_governance_communication import render
from app.routers.wp_render_strategies._context import RenderContext


# ─── Strategies ───────────────────────────────────────────────────────────────

def _mock_db_rows(
    recipient: str | None = None,
    chapter_contents: dict[int, str | None] | None = None,
    fee_json: str | None = None,
    sign_firm: str | None = None,
    sign_partner: str | None = None,
    sign_date: str | None = None,
) -> list:
    """Build fake checklist_responses rows."""
    rows = []
    if recipient:
        rows.append(MagicMock(item_id="a101-recipient", conclusion=recipient, remark=None))
    if chapter_contents:
        for num, content in chapter_contents.items():
            rows.append(MagicMock(
                item_id=f"a101-ch{num}-content",
                conclusion=None,
                remark=content,
            ))
    if fee_json:
        rows.append(MagicMock(item_id="a101-fee", conclusion=None, remark=fee_json))
    if sign_firm:
        rows.append(MagicMock(item_id="a101-sign-firm", conclusion=sign_firm, remark=None))
    if sign_partner:
        rows.append(MagicMock(item_id="a101-sign-partner", conclusion=sign_partner, remark=None))
    if sign_date:
        rows.append(MagicMock(item_id="a101-sign-date", conclusion=sign_date, remark=None))
    return rows


def _make_ctx(rows: list, client_name: str = "测试公司", audit_year: int | None = 2024) -> RenderContext:
    """Create a mock RenderContext."""
    db = AsyncMock()

    # First call: checklist_responses
    cr_result = MagicMock()
    cr_result.fetchall.return_value = rows

    # Second call: projects
    proj_row = MagicMock()
    proj_row.client_name = client_name
    proj_row.audit_year = audit_year
    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    # Third call: cross references
    xref_result = MagicMock()
    xref_result.fetchall.return_value = []

    db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-test-001"
    ctx.db = db
    ctx.project_id = "proj-test-001"
    return ctx


# ─── Hypothesis strategies ────────────────────────────────────────────────────

st_chapter_contents = st.dictionaries(
    keys=st.integers(min_value=1, max_value=16),
    values=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    max_size=16,
)

st_fee_amounts = st.lists(
    st.one_of(st.none(), st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False)),
    min_size=5,
    max_size=5,
)

st_recipient = st.one_of(st.none(), st.text(min_size=1, max_size=30))

st_client_name = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))


# ─── Property 3: chapters exactly 16 sequential ──────────────────────────────

@settings(max_examples=5)
@given(
    chapter_contents=st_chapter_contents,
    recipient=st_recipient,
)
def test_property3_chapters_exactly_16_sequential(chapter_contents, recipient):
    """Property 3: chapters array SHALL contain exactly 16 entries with sequential numbers 1-16.

    **Validates: Requirements 10**
    """
    import json

    rows = _mock_db_rows(
        recipient=recipient,
        chapter_contents=chapter_contents,
    )
    ctx = _make_ctx(rows)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None
    chapters = result["chapters"]
    assert len(chapters) == 16, f"Expected 16 chapters, got {len(chapters)}"

    # Sequential numbers 1-16
    numbers = [ch["number"] for ch in chapters]
    assert numbers == list(range(1, 17)), f"Expected [1..16], got {numbers}"

    # Each chapter has required keys
    for ch in chapters:
        assert "number" in ch
        assert "title" in ch
        assert "content" in ch
        assert "cross_ref" in ch


# ─── Property 4: response schema 9 top-level keys ────────────────────────────

@settings(max_examples=5)
@given(
    chapter_contents=st_chapter_contents,
    fee_amounts=st_fee_amounts,
    client_name=st_client_name,
)
def test_property4_response_schema_9_keys(chapter_contents, fee_amounts, client_name):
    """Property 4: response SHALL contain all 9 top-level keys with correct types.

    **Validates: Requirements 10**
    """
    import json

    fee_json = json.dumps([{"name": n, "amount": a} for n, a in zip(
        ["审计服务", "审阅服务", "其他鉴证服务", "税务服务", "其他服务"],
        fee_amounts,
    )])

    rows = _mock_db_rows(
        chapter_contents=chapter_contents,
        fee_json=fee_json,
        sign_firm="致同",
        sign_partner="张三",
        sign_date="2024-06-01",
    )
    ctx = _make_ctx(rows, client_name=client_name)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None

    # 9 top-level keys
    expected_keys = {
        "meta_info", "recipient", "introduction_text", "chapters",
        "service_fees", "signing_section", "guidance_notes",
        "cross_references", "project_context",
    }
    assert set(result.keys()) == expected_keys, f"Keys mismatch: {set(result.keys())} != {expected_keys}"

    # Type checks
    assert isinstance(result["meta_info"], dict)
    assert isinstance(result["introduction_text"], list)
    assert len(result["introduction_text"]) == 2
    assert isinstance(result["chapters"], list)
    assert len(result["chapters"]) == 16
    assert isinstance(result["service_fees"], list)
    assert len(result["service_fees"]) == 5
    assert isinstance(result["signing_section"], dict)
    assert isinstance(result["guidance_notes"], str)
    assert isinstance(result["cross_references"], dict)
    assert isinstance(result["project_context"], dict)

    # service_fees type check
    for fee in result["service_fees"]:
        assert "name" in fee
        assert "amount" in fee
        assert fee["amount"] is None or isinstance(fee["amount"], (int, float))
