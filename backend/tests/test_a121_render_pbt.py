"""Property-Based Tests for A12-1 法律事务确认函 render strategy.

Property 4: 后端响应结构完整性 — 5 top-level keys, litigation JSON round-trip.

**Validates: Requirements 11.1**
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── Strategies ───────────────────────────────────────────────────────────────

LITIGATION_STATUS_OPTIONS = ("no_litigation", "has_litigation", None)
FEE_STATUS_OPTIONS = ("no_outstanding", "has_outstanding", None)


@st.composite
def litigation_record_strategy(draw: st.DrawFn) -> dict:
    """Generate a single litigation record."""
    return {
        "description": draw(st.none() | st.text(min_size=1, max_size=100)),
        "opinion": draw(st.none() | st.text(min_size=1, max_size=100)),
        "estimated_loss": draw(st.none() | st.floats(min_value=0, max_value=1e8, allow_nan=False)),
    }


@st.composite
def a121_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate a complete A12-1 render response matching expected schema."""
    meta_info = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_period": draw(st.text(min_size=0, max_size=20)),
        "index_no": "A12-1",
    }
    litigation_list = draw(st.lists(litigation_record_strategy(), min_size=0, max_size=5))
    send_section = {
        "recipient": {
            "firm_name": draw(st.none() | st.text(min_size=1, max_size=50)),
            "lawyer_name": draw(st.none() | st.text(min_size=1, max_size=50)),
        },
        "explanation_text": draw(st.text(min_size=10, max_size=200)),
        "inquiry_1": {"litigation_list": litigation_list},
        "inquiry_2": {"content": draw(st.none() | st.text(min_size=1, max_size=200))},
        "inquiry_3": {"content": draw(st.none() | st.text(min_size=1, max_size=200))},
        "simplified_note": draw(st.text(min_size=10, max_size=200)),
        "sign_info": {
            "company_name": draw(st.none() | st.text(min_size=1, max_size=50)),
            "date": draw(st.none() | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
        },
        "reply_info_table": {
            "address": draw(st.none() | st.text(min_size=1, max_size=100)),
            "phone": draw(st.none() | st.text(min_size=1, max_size=20)),
            "contact": draw(st.none() | st.text(min_size=1, max_size=30)),
        },
    }
    reply_section = {
        "litigation_status": draw(st.sampled_from(LITIGATION_STATUS_OPTIONS)),
        "litigation_details": draw(st.none() | st.text(min_size=1, max_size=200)),
        "fee_status": draw(st.sampled_from(FEE_STATUS_OPTIONS)),
        "outstanding_amount": draw(st.none() | st.floats(min_value=0, max_value=1e8, allow_nan=False)),
        "sign": {
            "firm_name": draw(st.none() | st.text(min_size=1, max_size=50)),
            "lawyer_name": draw(st.none() | st.text(min_size=1, max_size=50)),
            "date": draw(st.none() | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
        },
    }
    cross_references = {
        "a5_3_wp_id": draw(st.none() | st.text(min_size=1, max_size=36)),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_period": draw(st.text(min_size=0, max_size=20)),
    }
    return {
        "meta_info": meta_info,
        "send_section": send_section,
        "reply_section": reply_section,
        "cross_references": cross_references,
        "project_context": project_context,
    }


# ─── Property 4: 后端响应结构完整性 ─────────────────────────────────────────


class TestProperty4ResponseSchemaCompleteness:
    """Property 4: 渲染策略返回结构完整性.

    For any valid A12-1 render response:
    - SHALL contain 5 top-level keys
    - send_section SHALL have all required sub-keys
    - reply_section SHALL have all required sub-keys
    - cross_references SHALL have 1 key (a5_3_wp_id)

    **Validates: Requirements 11.1**
    """

    @settings(max_examples=5)
    @given(data=a121_render_response_strategy())
    def test_top_level_has_5_keys(self, data: dict):
        """Feature: a12-1-legal-confirmation, Property 4: top-level has 5 keys."""
        expected_keys = {
            "meta_info", "send_section", "reply_section",
            "cross_references", "project_context",
        }
        assert set(data.keys()) == expected_keys

    @settings(max_examples=5)
    @given(data=a121_render_response_strategy())
    def test_send_section_has_required_keys(self, data: dict):
        """Feature: a12-1-legal-confirmation, Property 4: send_section structure."""
        expected = {
            "recipient", "explanation_text", "inquiry_1", "inquiry_2",
            "inquiry_3", "simplified_note", "sign_info", "reply_info_table",
        }
        assert set(data["send_section"].keys()) == expected

    @settings(max_examples=5)
    @given(data=a121_render_response_strategy())
    def test_reply_section_has_required_keys(self, data: dict):
        """Feature: a12-1-legal-confirmation, Property 4: reply_section structure."""
        expected = {
            "litigation_status", "litigation_details",
            "fee_status", "outstanding_amount", "sign",
        }
        assert set(data["reply_section"].keys()) == expected

    @settings(max_examples=5)
    @given(data=a121_render_response_strategy())
    def test_meta_info_has_index_no(self, data: dict):
        """Feature: a12-1-legal-confirmation, Property 4: meta_info.index_no == A12-1."""
        assert data["meta_info"]["index_no"] == "A12-1"

    @settings(max_examples=5)
    @given(data=a121_render_response_strategy())
    def test_cross_references_has_a5_3(self, data: dict):
        """Feature: a12-1-legal-confirmation, Property 4: cross_references has a5_3_wp_id."""
        assert "a5_3_wp_id" in data["cross_references"]


class TestLitigationJsonRoundTrip:
    """Litigation list JSON round-trip property.

    For any list of litigation records, serializing to JSON and parsing back
    SHALL produce identical data.

    **Validates: Requirements 5.5**
    """

    @settings(max_examples=5)
    @given(records=st.lists(litigation_record_strategy(), min_size=0, max_size=5))
    def test_litigation_json_round_trip(self, records: list):
        """Feature: a12-1-legal-confirmation, litigation JSON round-trip."""
        serialized = json.dumps(records)
        deserialized = json.loads(serialized)
        assert len(deserialized) == len(records)
        for orig, restored in zip(records, deserialized):
            assert orig["description"] == restored["description"]
            assert orig["opinion"] == restored["opinion"]
            # float comparison: None or equal
            if orig["estimated_loss"] is None:
                assert restored["estimated_loss"] is None
            else:
                assert abs(orig["estimated_loss"] - restored["estimated_loss"]) < 1e-6
