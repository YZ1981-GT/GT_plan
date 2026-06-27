"""A17-2-1 关键审计事项(KAM) — Property-Based Tests.

Property 2: KAM JSON round-trip — For any KAM object (6 string fields:
            basic, policy, reason, response, result, ref_index) saved as JSON
            to remark, reloading SHALL return equivalent object.
Property 5: KAM add/remove consistency — For any sequence of add/remove
            operations, kams list length and notes length are consistent.

**Validates: Requirements 8**
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a1721_kam import render
from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _row(item_id, conclusion=None, remark=None):
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


def _make_ctx(rows: list, client_name: str = "测试公司", audit_year: int | None = 2024) -> RenderContext:
    """Create a mock RenderContext for A17-2-1."""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = rows

    proj_row = MagicMock()
    proj_row.client_name = client_name
    proj_row.audit_year = audit_year
    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    db.execute = AsyncMock(side_effect=[cr_result, proj_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-a1721-001"
    ctx.db = db
    ctx.project_id = "proj-001"
    return ctx


# ─── Hypothesis strategies ────────────────────────────────────────────────────

# KAM object: 6 string fields
st_kam_obj = st.fixed_dictionaries({
    "basic": st.text(min_size=0, max_size=50),
    "policy": st.text(min_size=0, max_size=50),
    "reason": st.text(min_size=0, max_size=50),
    "response": st.text(min_size=0, max_size=50),
    "result": st.text(min_size=0, max_size=50),
    "ref_index": st.text(min_size=0, max_size=50),
})

# List of KAM objects (1-5)
st_kam_list = st.lists(st_kam_obj, min_size=1, max_size=5)

# Notes content per KAM
st_note_content = st.text(min_size=0, max_size=100)

# Add/remove operation sequence
st_add_remove_ops = st.lists(
    st.tuples(
        st.sampled_from(["add", "remove"]),
        st.integers(min_value=1, max_value=10),
    ),
    min_size=1,
    max_size=10,
)


# ─── Property 2: KAM JSON round-trip ─────────────────────────────────────────


@settings(max_examples=5)
@given(kam_list=st_kam_list)
def test_property2_kam_json_roundtrip(kam_list):
    """Property 2: KAM JSON saved to remark, reloading returns equivalent object.

    **Validates: Requirements 8**
    """
    rows = []

    # Create checklist_responses rows with each KAM as JSON in remark
    for i, kam in enumerate(kam_list, start=1):
        rows.append(_row(f"a1721-kam{i}", remark=json.dumps(kam)))

    ctx = _make_ctx(rows)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None
    loaded_kams = result["kams"]

    assert len(loaded_kams) == len(kam_list)

    for orig, loaded in zip(kam_list, loaded_kams):
        assert loaded["basic"] == orig["basic"]
        assert loaded["policy"] == orig["policy"]
        assert loaded["reason"] == orig["reason"]
        assert loaded["response"] == orig["response"]
        assert loaded["result"] == orig["result"]
        assert loaded["ref_index"] == orig["ref_index"]


# ─── Property 5: KAM add/remove consistency ──────────────────────────────────


@settings(max_examples=5)
@given(ops=st_add_remove_ops)
def test_property5_kam_add_remove_consistency(ops):
    """Property 5: For any sequence of add/remove, kams length and notes length are consistent.

    We simulate by building a final set of KAM indices after operations,
    then verifying render returns matching kams/notes counts.

    **Validates: Requirements 8**
    """
    # Simulate add/remove sequence to determine final KAM indices
    active_indices: list[int] = []
    next_index = 1

    for op, _count in ops:
        if op == "add":
            active_indices.append(next_index)
            next_index += 1
        elif op == "remove" and active_indices:
            # Remove last added
            active_indices.pop()

    # Build rows from the final state
    rows = []
    for idx in active_indices:
        kam_data = {
            "basic": f"KAM {idx} 基本情况",
            "policy": f"KAM {idx} 会计政策",
            "reason": f"KAM {idx} 原因",
            "response": f"KAM {idx} 应对",
            "result": f"KAM {idx} 结果",
            "ref_index": f"A{idx}",
        }
        rows.append(_row(f"a1721-kam{idx}", remark=json.dumps(kam_data)))
        rows.append(_row(f"a1721-notes-{idx}", remark=f"附注 {idx}"))

    ctx = _make_ctx(rows)
    result = asyncio.get_event_loop().run_until_complete(render(ctx))

    assert result is not None

    # kams length == notes length == number of active indices
    assert len(result["kams"]) == len(active_indices)
    assert len(result["notes"]) == len(active_indices)

    # Each KAM has matching note
    kam_indices = {k["index"] for k in result["kams"]}
    note_indices = {n["kam_index"] for n in result["notes"]}
    assert kam_indices == note_indices
