"""Property-Based Tests for A9-2 向治理层通报内部控制缺陷沟通函 render strategy.

Property 4: 后端返回结构与 variant 一致性
- response SHALL contain variant="governance"
- response SHALL NOT contain "general" key in deficiency_list
- response SHALL NOT contain "response" key in section_data

**Validates: Requirements 4.3, 6.1**
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a92_deficiency_letter_governance import render


# ─── Strategies ───────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
B22BRow = namedtuple("B22BRow", ["wp_id"])


@st.composite
def a92_ctx_strategy(draw: st.DrawFn):
    """Generate a minimal mock RenderContext with random project data."""
    client_name = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))))
    audit_year = draw(st.integers(min_value=2020, max_value=2030))
    has_b22b = draw(st.booleans())
    num_major = draw(st.integers(min_value=0, max_value=3))
    num_significant = draw(st.integers(min_value=0, max_value=3))
    num_general = draw(st.integers(min_value=0, max_value=3))

    ctx = MagicMock()
    ctx.wp_id = "wp-a92-test"
    ctx.project_id = "proj-a92-test"
    db = AsyncMock()

    # A92 checklist_responses (empty for simplicity — the property validates structure)
    a92_result = MagicMock()
    a92_result.fetchall.return_value = []

    # B22B lookup
    b22b_wp_result = MagicMock()
    b22b_wp_result.fetchone.return_value = B22BRow("b22b-wp") if has_b22b else None

    # B22B deficiencies
    b22b_rows = []
    for i in range(num_major):
        b22b_rows.append(ChecklistRow(
            f"b22b-deficiency-m{i}", None,
            json.dumps({"id": f"M-{i}", "description": "d", "impact": "i", "severity": "major", "index_ref": None}),
        ))
    for i in range(num_significant):
        b22b_rows.append(ChecklistRow(
            f"b22b-deficiency-s{i}", None,
            json.dumps({"id": f"S-{i}", "description": "d", "impact": "i", "severity": "significant", "index_ref": None}),
        ))
    for i in range(num_general):
        b22b_rows.append(ChecklistRow(
            f"b22b-deficiency-g{i}", None,
            json.dumps({"id": f"G-{i}", "description": "d", "impact": "i", "severity": "general", "index_ref": None}),
        ))

    b22b_cr_result = MagicMock()
    b22b_cr_result.fetchall.return_value = b22b_rows

    # Project context
    proj_result = MagicMock()
    proj_result.fetchone.return_value = ProjectRow(client_name, audit_year)

    if has_b22b:
        db.execute = AsyncMock(side_effect=[a92_result, b22b_wp_result, b22b_cr_result, proj_result])
    else:
        db.execute = AsyncMock(side_effect=[a92_result, b22b_wp_result, proj_result])

    ctx.db = db
    return ctx


# ─── Property 4: 后端返回结构与 variant 一致性 ───────────────────────────────


class TestProperty4GovernanceResponseStructure:
    """Property 4: A9-2 响应结构验证.

    For any A9-2 render request:
    - variant SHALL be "governance"
    - deficiency_list SHALL NOT have "general" key
    - section_data SHALL NOT have "response" key

    **Validates: Requirements 4.3, 6.1**
    """

    @settings(max_examples=5)
    @given(ctx=a92_ctx_strategy())
    @pytest.mark.asyncio
    async def test_variant_is_governance(self, ctx):
        """Feature: a9-2-deficiency-letter-governance, Property 4: variant == governance."""
        result = await render(ctx)
        assert result is not None
        assert result["variant"] == "governance"

    @settings(max_examples=5)
    @given(ctx=a92_ctx_strategy())
    @pytest.mark.asyncio
    async def test_no_general_in_deficiency_list(self, ctx):
        """Feature: a9-2-deficiency-letter-governance, Property 4: no general in deficiency_list."""
        result = await render(ctx)
        assert result is not None
        assert "general" not in result["deficiency_list"]
        # Only major and significant keys present
        assert set(result["deficiency_list"].keys()) == {"major", "significant"}

    @settings(max_examples=5)
    @given(ctx=a92_ctx_strategy())
    @pytest.mark.asyncio
    async def test_no_response_in_section_data(self, ctx):
        """Feature: a9-2-deficiency-letter-governance, Property 4: no response in section_data."""
        result = await render(ctx)
        assert result is not None
        assert "response" not in result["section_data"]
        # Expected keys without response
        expected_keys = {"addressee", "independence", "committee", "signature"}
        assert set(result["section_data"].keys()) == expected_keys

    @settings(max_examples=5)
    @given(ctx=a92_ctx_strategy())
    @pytest.mark.asyncio
    async def test_top_level_keys_complete(self, ctx):
        """Feature: a9-2-deficiency-letter-governance, Property 4: top-level keys correct."""
        result = await render(ctx)
        assert result is not None
        assert set(result.keys()) == {"variant", "section_data", "deficiency_list", "project_context", "b22b_warning"}

    @settings(max_examples=5)
    @given(ctx=a92_ctx_strategy())
    @pytest.mark.asyncio
    async def test_general_deficiencies_filtered_even_when_b22b_has_them(self, ctx):
        """Feature: a9-2-deficiency-letter-governance, Property 4: general deficiencies never appear."""
        result = await render(ctx)
        assert result is not None
        # Even if B22B has general deficiencies, they should not appear
        all_items = result["deficiency_list"]["major"] + result["deficiency_list"]["significant"]
        for item in all_items:
            assert item["severity"] in ("major", "significant")
