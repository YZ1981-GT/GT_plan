"""Property-Based Tests for B1-4 尽职调查报告 render strategy.

Feature: b1-4-due-diligence-report, Property 7: Render function produces well-structured output

Generate random checklist_responses rows (b14-* item_id), verify render output
contains chapters/variant/signature/project_context and structure is complete.

**Validates: Requirements 7.2**
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._b14_due_diligence import (
    CHAPTERS_META,
    SIGNATURE_FIELDS,
    render,
)
from app.routers.wp_render_strategies._context import RenderContext


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_variant_st = st.sampled_from(["standard", "simplified"])

_chapter_num_st = st.integers(min_value=1, max_value=13)

# Generate content text (may be None)
_content_st = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N"))))

# Generate table rows as JSON-serializable lists
_table_row_st = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
    "value": st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "N"))),
})
_table_rows_st = st.lists(_table_row_st, min_size=0, max_size=3)


@st.composite
def checklist_responses_strategy(draw: st.DrawFn) -> list[tuple[str, str | None, str | None]]:
    """Generate a list of (item_id, conclusion, remark) tuples for b14-* responses.

    Includes:
    - b14-meta-variant (variant selection)
    - b14-signature-{field} (signature fields)
    - b14-ch{N}-content (textarea chapters)
    - b14-ch{N}-{section_id} (mixed chapter textarea sections)
    - b14-ch{N}-table-{table_id} (table data as JSON in remark)
    """
    rows: list[tuple[str, str | None, str | None]] = []

    # 1. Variant meta
    variant = draw(_variant_st)
    rows.append(("b14-meta-variant", variant, None))

    # 2. Signature fields (random subset)
    sig_fields = draw(st.lists(
        st.sampled_from(SIGNATURE_FIELDS),
        min_size=0,
        max_size=len(SIGNATURE_FIELDS),
        unique=True,
    ))
    for field_name in sig_fields:
        value = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))))
        rows.append((f"b14-signature-{field_name}", value, None))

    # 3. Chapter content (random subset of chapters)
    chapters_to_fill = draw(st.lists(
        _chapter_num_st,
        min_size=0,
        max_size=6,
        unique=True,
    ))
    for ch_num in chapters_to_fill:
        meta = CHAPTERS_META[ch_num - 1]
        ch_type = meta["type"]

        if ch_type == "textarea":
            content = draw(_content_st)
            if content:
                rows.append((f"b14-ch{ch_num}-content", None, content))

        elif ch_type == "table":
            table_id = meta.get("table_id", "")
            table_rows = draw(_table_rows_st)
            if table_rows:
                rows.append((f"b14-ch{ch_num}-table-{table_id}", None, json.dumps(table_rows)))

        elif ch_type == "mixed":
            sections = meta.get("sections", [])
            if sections:
                # Fill a random subset of sections
                sec_indices = draw(st.lists(
                    st.integers(min_value=0, max_value=len(sections) - 1),
                    min_size=0,
                    max_size=min(3, len(sections)),
                    unique=True,
                ))
                for sec_idx in sec_indices:
                    sec = sections[sec_idx]
                    sec_id = sec["id"]
                    sec_type = sec["type"]

                    if sec_type == "textarea":
                        content = draw(_content_st)
                        if content:
                            rows.append((f"b14-ch{ch_num}-{sec_id}", None, content))
                    elif sec_type == "table":
                        table_id = sec.get("table_id", sec_id)
                        table_rows = draw(_table_rows_st)
                        if table_rows:
                            rows.append((f"b14-ch{ch_num}-table-{table_id}", None, json.dumps(table_rows)))

    return rows


# ─── Helper: build mock RenderContext ─────────────────────────────────────────


def _make_ctx(responses: list[tuple[str, str | None, str | None]]) -> RenderContext:
    """Build a mock RenderContext with checklist_responses rows."""
    # Build fake DB rows for checklist_responses query
    cr_rows = []
    for item_id, conclusion, remark in responses:
        row = MagicMock()
        row.item_id = item_id
        row.conclusion = conclusion
        row.remark = remark
        cr_rows.append(row)

    # Build fake project row
    proj_row = MagicMock()
    proj_row.client_name = "测试公司"
    proj_row.audit_year = 2025
    proj_row.business_category = "制造业"

    db = AsyncMock()

    # Two sequential db.execute calls: 1st for checklist_responses, 2nd for projects
    cr_result = MagicMock()
    cr_result.fetchall.return_value = cr_rows

    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    db.execute = AsyncMock(side_effect=[cr_result, proj_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-b14-test-001"
    ctx.db = db
    ctx.project_id = "proj-test-001"

    return ctx


# ─── Property 7: Render function produces well-structured output ─────────────


class TestProperty7RenderOutputStructure:
    """Feature: b1-4-due-diligence-report, Property 7: Render function produces well-structured output

    For any set of checklist_responses rows with item_ids matching b14-* prefix,
    the render function should produce an output containing: a chapters dict keyed
    by chapter id, a variant string of value 'standard' or 'simplified', a signature
    dict with all required fields, and a project_context dict with
    client_name/industry/audit_period/firm_name.

    **Validates: Requirements 7.2**
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_render_output_has_required_top_level_keys(self, responses):
        """Render output contains chapters, variant, signature, project_context."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        expected_keys = {"chapters", "variant", "signature", "project_context"}
        assert set(result.keys()) == expected_keys, (
            f"Top-level keys mismatch: {set(result.keys())} != {expected_keys}"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_chapters_contains_all_13_chapter_ids(self, responses):
        """Chapters dict has keys ch1 through ch13."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        chapters = result["chapters"]
        assert isinstance(chapters, dict)

        expected_ch_ids = {f"ch{i}" for i in range(1, 14)}
        assert set(chapters.keys()) == expected_ch_ids, (
            f"Chapter keys mismatch: {set(chapters.keys())} != {expected_ch_ids}"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_variant_is_standard_or_simplified(self, responses):
        """Variant field is either 'standard' or 'simplified'."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert result["variant"] in ("standard", "simplified"), (
            f"Unexpected variant value: {result['variant']}"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_signature_has_all_required_fields(self, responses):
        """Signature dict contains all 5 required fields."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        signature = result["signature"]
        assert isinstance(signature, dict)

        for field_name in SIGNATURE_FIELDS:
            assert field_name in signature, (
                f"Signature missing field: {field_name}"
            )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_project_context_has_required_fields(self, responses):
        """Project context dict contains client_name, industry, audit_period, firm_name."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        pc = result["project_context"]
        assert isinstance(pc, dict)

        required_fields = {"client_name", "industry", "audit_period", "firm_name"}
        for field_name in required_fields:
            assert field_name in pc, (
                f"project_context missing field: {field_name}"
            )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(responses=checklist_responses_strategy())
    def test_variant_matches_input_response(self, responses):
        """Variant value in output matches the b14-meta-variant input."""
        ctx = _make_ctx(responses)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None

        # Find the variant from input responses
        input_variant = None
        for item_id, conclusion, _remark in responses:
            if item_id == "b14-meta-variant":
                input_variant = conclusion
                break

        if input_variant:
            assert result["variant"] == input_variant


# ─── Strategies for Property 6: B14RenderData round-trip ─────────────────────

_nullable_str_st = st.one_of(st.none(), st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "P"))))

_table_cell_st = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N"))),
    st.integers(min_value=-9999, max_value=9999),
    st.floats(min_value=-9999, max_value=9999, allow_nan=False, allow_infinity=False),
)

_render_table_row_st = st.dictionaries(
    keys=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
    values=_table_cell_st,
    min_size=1,
    max_size=4,
)


@st.composite
def b14_render_data_strategy(draw: st.DrawFn) -> dict:
    """Generate a complete B14RenderData dict matching render output structure.

    Structure:
    - chapters: dict of ch1~ch13 with id/title/type/visible + type-specific fields
    - variant: "standard" or "simplified"
    - signature: dict with partner/partner_date/manager/manager_date/report_date
    - project_context: dict with client_name/industry/audit_period/firm_name
    """
    variant = draw(_variant_st)

    # Build chapters
    chapters: dict = {}
    for meta in CHAPTERS_META:
        ch_id = meta["id"]
        ch_type = meta["type"]
        visible = True
        if meta.get("variant_only") == "standard" and variant == "simplified":
            visible = False

        ch_data: dict = {
            "id": ch_id,
            "title": meta["title"],
            "type": ch_type,
            "visible": visible,
        }

        if ch_type == "textarea":
            ch_data["content"] = draw(_nullable_str_st)

        elif ch_type == "table":
            table_id = meta.get("table_id", "")
            rows = draw(st.lists(_render_table_row_st, min_size=0, max_size=3))
            ch_data["rows"] = rows
            ch_data["table_id"] = table_id

        elif ch_type == "mixed":
            sections: list[dict] = []
            for sec_meta in meta.get("sections", []):
                sec_type = sec_meta["type"]
                sec_data: dict = {
                    "id": sec_meta["id"],
                    "title": sec_meta["title"],
                    "type": sec_type,
                }
                if sec_type == "textarea":
                    sec_data["content"] = draw(_nullable_str_st)
                elif sec_type == "table":
                    table_id = sec_meta.get("table_id", sec_meta["id"])
                    sec_data["rows"] = draw(st.lists(_render_table_row_st, min_size=0, max_size=3))
                    sec_data["table_id"] = table_id
                sections.append(sec_data)
            ch_data["sections"] = sections

        chapters[ch_id] = ch_data

    # Signature
    signature = {
        "partner": draw(_nullable_str_st),
        "partner_date": draw(_nullable_str_st),
        "manager": draw(_nullable_str_st),
        "manager_date": draw(_nullable_str_st),
        "report_date": draw(_nullable_str_st),
    }

    # Project context
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N")))),
        "industry": draw(st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N")))),
        "audit_period": draw(st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N")))),
        "firm_name": draw(st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N")))),
    }

    return {
        "chapters": chapters,
        "variant": variant,
        "signature": signature,
        "project_context": project_context,
    }


# ─── Property 6: B14RenderData serialization round-trip ──────────────────────


class TestProperty6RenderDataRoundTrip:
    """Feature: b1-4-due-diligence-report, Property 6: B14RenderData serialization round-trip

    For any valid B14RenderData object (containing chapters with various types,
    variant, signature, project_context), serializing to JSON and deserializing
    back should produce a structurally equivalent object.

    **Validates: Requirements 7.4**
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=b14_render_data_strategy())
    def test_json_round_trip_equivalence(self, data):
        """JSON serialize → deserialize produces equivalent B14RenderData."""
        serialized = json.dumps(data, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == data, (
            f"Round-trip mismatch: deserialized != original"
        )
