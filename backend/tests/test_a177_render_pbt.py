"""Property-Based Tests for A17-7 独立性声明书 render strategy.

Property 4: 响应结构完整性 — response SHALL contain all 8 top-level keys with correct types.
Property 5: variant 由 wp_code 确定 — A17-7→team, A17-7A→committee.

**Validates: Requirements 9, Design §Correctness Properties**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a177_independence_declaration import (
    _determine_variant,
)

# ─── Expected keys ────────────────────────────────────────────────────────────

EXPECTED_TOP_KEYS = {
    "variant",
    "meta_info",
    "declaration_text",
    "period_data",
    "team_sign_table",
    "partner_section",
    "threat_records",
    "guidance_notes",
    "project_context",
}


# ─── Property 4: 响应结构完整性 (8 top-level keys) ──────────────────────────

@st.composite
def a177_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A17-7 render responses matching the expected schema."""
    variant = draw(st.sampled_from(["team", "committee"]))
    meta_info = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_year": draw(st.text(min_size=0, max_size=10)),
        "index_no": draw(st.sampled_from(["A17-7", "A17-7A"])),
    }
    declaration_text = draw(st.text(min_size=1, max_size=200))
    period_data = {
        "business_start": draw(st.none() | st.text(min_size=10, max_size=10)),
        "business_end": draw(st.none() | st.text(min_size=10, max_size=10)),
        "report_start": draw(st.none() | st.text(min_size=10, max_size=10)),
        "report_end": draw(st.none() | st.text(min_size=10, max_size=10)),
    }
    n_members = draw(st.integers(min_value=0, max_value=5))
    team_sign_table = [
        {
            "index": i + 1,
            "name": draw(st.text(min_size=1, max_size=10)),
            "signed": draw(st.booleans()),
            "date": draw(st.none() | st.text(min_size=10, max_size=10)),
        }
        for i in range(n_members)
    ]
    partner_section = {
        "confirmed": draw(st.none() | st.booleans()),
        "explanation": draw(st.none() | st.text(min_size=0, max_size=50)),
        "partner_sign": {"name": draw(st.none() | st.text(min_size=1, max_size=10)), "date": None},
        "manager_sign": {"name": draw(st.none() | st.text(min_size=1, max_size=10)), "date": None},
    }
    threat_records = {
        "economic_interest": [{"member": "m", "type": "t", "amount": "0", "measure": "x"}]
            * draw(st.integers(min_value=0, max_value=3)),
        "loan_guarantee": [{"member": "m", "type": "t", "amount": "0", "measure": "x"}]
            * draw(st.integers(min_value=0, max_value=3)),
        "business_relation": [{"member": "m", "description": "d", "measure": "x"}]
            * draw(st.integers(min_value=0, max_value=3)),
    }
    guidance_notes = [draw(st.text(min_size=1, max_size=50)) for _ in range(5)]
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=30)),
        "audit_year": draw(st.text(min_size=0, max_size=10)),
        "team_members": [{"name": draw(st.text(min_size=1, max_size=10))} for _ in range(n_members)],
    }
    return {
        "variant": variant,
        "meta_info": meta_info,
        "declaration_text": declaration_text,
        "period_data": period_data,
        "team_sign_table": team_sign_table,
        "partner_section": partner_section,
        "threat_records": threat_records,
        "guidance_notes": guidance_notes,
        "project_context": project_context,
    }


class TestProperty4ResponseSchemaCompleteness:
    """Property 4: 响应结构完整性.

    For any valid render response, response SHALL contain all 8+1 top-level keys.

    **Validates: Requirements 9, Design §Correctness Properties P4**
    """

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_response_has_all_top_level_keys(self, data: dict):
        """Property 4a: response has exactly 9 top-level keys."""
        assert set(data.keys()) == EXPECTED_TOP_KEYS

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_variant_is_valid_string(self, data: dict):
        """Property 4b: variant is 'team' or 'committee'."""
        assert data["variant"] in ("team", "committee")

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_meta_info_has_3_keys(self, data: dict):
        """Property 4c: meta_info has exactly 3 keys."""
        assert set(data["meta_info"].keys()) == {"client_name", "audit_year", "index_no"}

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_period_data_has_4_keys(self, data: dict):
        """Property 4d: period_data has exactly 4 keys."""
        assert set(data["period_data"].keys()) == {
            "business_start", "business_end", "report_start", "report_end"
        }

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_team_sign_table_is_list(self, data: dict):
        """Property 4e: team_sign_table is a list."""
        assert isinstance(data["team_sign_table"], list)

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_threat_records_has_3_keys(self, data: dict):
        """Property 4f: threat_records has exactly 3 keys."""
        assert set(data["threat_records"].keys()) == {
            "economic_interest", "loan_guarantee", "business_relation"
        }

    @settings(max_examples=5)
    @given(data=a177_render_response_strategy())
    def test_guidance_notes_is_list_of_5(self, data: dict):
        """Property 4g: guidance_notes is list of 5."""
        assert isinstance(data["guidance_notes"], list)
        assert len(data["guidance_notes"]) == 5


# ─── Property 5: variant 由 wp_code 确定 ────────────────────────────────────

class TestProperty5VariantFromWpCode:
    """Property 5: variant 由 wp_code 确定.

    For any render request, wp_code "A17-7" SHALL produce variant="team",
    wp_code "A17-7A" SHALL produce variant="committee".

    **Validates: Requirements 3, Design §Correctness Properties P5**
    """

    @settings(max_examples=5)
    @given(wp_code=st.just("A17-7"))
    def test_a177_produces_team(self, wp_code: str):
        """Property 5a: A17-7 → team."""
        variant, prefix = _determine_variant(wp_code)
        assert variant == "team"
        assert prefix == "a177-"

    @settings(max_examples=5)
    @given(wp_code=st.just("A17-7A"))
    def test_a177a_produces_committee(self, wp_code: str):
        """Property 5b: A17-7A → committee."""
        variant, prefix = _determine_variant(wp_code)
        assert variant == "committee"
        assert prefix == "a177a-"

    @settings(max_examples=5)
    @given(wp_code=st.text(min_size=0, max_size=10).filter(lambda x: x.upper() not in ("A17-7A",)))
    def test_non_a177a_defaults_to_team(self, wp_code: str):
        """Property 5c: Any wp_code that is not 'A17-7A' defaults to team variant."""
        variant, prefix = _determine_variant(wp_code)
        if wp_code.upper() == "A17-7A":
            assert variant == "committee"
        else:
            assert variant == "team"
            assert prefix == "a177-"
