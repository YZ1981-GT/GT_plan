"""A17-1 重大事项概要汇总 — Property-Based Tests.

Property 2: 表格行 JSON round-trip — table chapters (6/8) saved as JSON remark,
            reloaded returns equivalent rows with all columns preserved.
Property 5: 渲染策略返回结构 — response contains 16 chapters with correct types,
            signature_table with 10 rows, and project_context.

**Validates: Requirements 10**
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a171_audit_summary import (
    CHAPTERS_META,
    SIGNATURE_ROLES,
    render,
)
from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _row(item_id, conclusion=None, remark=None):
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


def _make_ctx(rows: list, client_name: str = "测试公司", audit_year: int | None = 2024) -> RenderContext:
    """Create a mock RenderContext."""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = rows

    proj_row = MagicMock()
    proj_row.client_name = client_name
    proj_row.audit_year = audit_year
    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    xref_result = MagicMock()
    xref_result.fetchall.return_value = []

    db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-a171-001"
    ctx.db = db
    ctx.project_id = "proj-001"
    return ctx


# ─── Hypothesis strategies ────────────────────────────────────────────────────

# Chapter 6 table rows: {risk, response, result, conclusion}
st_ch6_row = st.fixed_dictionaries({
    "risk": st.text(min_size=1, max_size=30),
    "response": st.text(min_size=1, max_size=30),
    "result": st.text(min_size=1, max_size=30),
    "conclusion": st.text(min_size=1, max_size=30),
})

# Chapter 8 table rows: {item, amount, note}
st_ch8_row = st.fixed_dictionaries({
    "item": st.text(min_size=1, max_size=20),
    "amount": st.one_of(st.none(), st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False)),
    "note": st.text(min_size=0, max_size=20),
})

st_ch6_rows = st.lists(st_ch6_row, min_size=0, max_size=5)
st_ch8_rows = st.lists(st_ch8_row, min_size=0, max_size=5)

st_yn_answer = st.one_of(st.none(), st.just("Y"), st.just("N"))
st_explanation = st.one_of(st.none(), st.text(min_size=1, max_size=30))

st_textarea_contents = st.dictionaries(
    keys=st.sampled_from([1, 2, 3, 4, 5, 7, 13, 14, 15, 16]),
    values=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    max_size=10,
)

st_client_name = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))


# ─── Property 2: table JSON round-trip ───────────────────────────────────────

@settings(max_examples=5)
@given(
    ch6_rows=st_ch6_rows,
    ch8_rows=st_ch8_rows,
)
def test_property2_table_json_roundtrip(ch6_rows, ch8_rows):
    """Property 2: table data saved as JSON to remark, reloading returns equivalent rows.

    **Validates: Requirements 10**
    """
    rows = []
    if ch6_rows:
        rows.append(_row("a171-ch6-table", remark=json.dumps(ch6_rows)))
    if ch8_rows:
        rows.append(_row("a171-ch8-table", remark=json.dumps(ch8_rows)))

    ctx = _make_ctx(rows)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None

    # Chapter 6 round-trip
    ch6_loaded = result["chapters"]["6"]["rows"]
    if ch6_rows:
        assert len(ch6_loaded) == len(ch6_rows)
        for orig, loaded in zip(ch6_rows, ch6_loaded):
            assert loaded["risk"] == orig["risk"]
            assert loaded["response"] == orig["response"]
            assert loaded["result"] == orig["result"]
            assert loaded["conclusion"] == orig["conclusion"]
    else:
        assert ch6_loaded == []

    # Chapter 8 round-trip
    ch8_loaded = result["chapters"]["8"]["rows"]
    if ch8_rows:
        assert len(ch8_loaded) == len(ch8_rows)
        for orig, loaded in zip(ch8_rows, ch8_loaded):
            assert loaded["item"] == orig["item"]
            assert loaded["note"] == orig["note"]
            # float comparison: None stays None, values compare equal
            if orig["amount"] is None:
                assert loaded["amount"] is None
            else:
                assert abs(loaded["amount"] - orig["amount"]) < 1e-6
    else:
        assert ch8_loaded == []


# ─── Property 5: response schema 16 chapters + signature + context ───────────

@settings(max_examples=5)
@given(
    textarea_contents=st_textarea_contents,
    ch6_rows=st_ch6_rows,
    yn_answer=st_yn_answer,
    yn_explanation=st_explanation,
    client_name=st_client_name,
)
def test_property5_response_schema(textarea_contents, ch6_rows, yn_answer, yn_explanation, client_name):
    """Property 5: response contains 16 chapters with correct types, signature_table(10), project_context.

    **Validates: Requirements 10**
    """
    rows = []

    # Add textarea chapters
    for num, content in textarea_contents.items():
        if content:
            rows.append(_row(f"a171-ch{num}-content", remark=content))

    # Add table chapter
    if ch6_rows:
        rows.append(_row("a171-ch6-table", remark=json.dumps(ch6_rows)))

    # Add Y/N chapters
    for ch_num in (9, 10, 11, 12):
        rows.append(_row(f"a171-ch{ch_num}-yn", conclusion=yn_answer, remark=yn_explanation))

    ctx = _make_ctx(rows, client_name=client_name)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None

    # Top-level keys
    expected_keys = {"chapters", "signature_table", "cross_references", "project_context"}
    assert set(result.keys()) == expected_keys

    # 16 chapters with string keys "1"-"16"
    chapters = result["chapters"]
    assert len(chapters) == 16
    for i in range(1, 17):
        ch = chapters[str(i)]
        assert "type" in ch
        assert "title" in ch
        assert ch["type"] in ("textarea", "table", "yn")

    # Type-specific fields
    textarea_nums = [1, 2, 3, 4, 5, 7, 13, 14, 15, 16]
    table_nums = [6, 8]
    yn_nums = [9, 10, 11, 12]

    for num in textarea_nums:
        assert "content" in chapters[str(num)]
    for num in table_nums:
        assert "rows" in chapters[str(num)]
        assert isinstance(chapters[str(num)]["rows"], list)
    for num in yn_nums:
        assert "answer" in chapters[str(num)]
        assert "explanation" in chapters[str(num)]
        assert chapters[str(num)]["answer"] in (None, "Y", "N")

    # signature_table: 10 rows
    sig = result["signature_table"]
    assert len(sig) == 10
    for row in sig:
        assert "role" in row
        assert "name" in row
        assert "date" in row

    # project_context
    pc = result["project_context"]
    assert "client_name" in pc
    assert "audit_period" in pc
    assert "preparer" in pc
