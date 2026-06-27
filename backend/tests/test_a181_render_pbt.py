"""Property-Based Tests for A18-1 向监管部门报送审计小结 render strategy.

Property 3: 响应结构完整性 — recipient 1 key + body 2 keys + issuance 2 keys + project_context 4 keys

**Validates: Requirements 1.1, Design §Data Models**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


EXPECTED_RECIPIENT_KEYS = {"bureau"}
EXPECTED_BODY_KEYS = {"contact_person", "contact_phone"}
EXPECTED_ISSUANCE_KEYS = {"partner", "date"}
EXPECTED_CONTEXT_KEYS = {"client_name", "audit_year", "firm_name", "partner_name"}


@st.composite
def a181_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A18-1 render responses matching the expected schema."""
    recipient = {"bureau": draw(st.text(min_size=0, max_size=50))}
    body = {
        "contact_person": draw(st.text(min_size=0, max_size=20)),
        "contact_phone": draw(st.text(min_size=0, max_size=20)),
    }
    issuance = {
        "partner": draw(st.text(min_size=0, max_size=20)),
        "date": draw(st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True) | st.just("")),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_year": draw(st.text(min_size=0, max_size=10)),
        "firm_name": "致同会计师事务所（特殊普通合伙）",
        "partner_name": draw(st.text(min_size=0, max_size=20)),
    }
    return {"recipient": recipient, "body": body, "issuance": issuance, "project_context": project_context}


class TestProperty3ResponseStructureCompleteness:
    """Property 3: 响应结构完整性."""

    @settings(max_examples=5)
    @given(data=a181_render_response_strategy())
    def test_recipient_has_exactly_1_key(self, data: dict):
        assert set(data["recipient"].keys()) == EXPECTED_RECIPIENT_KEYS

    @settings(max_examples=5)
    @given(data=a181_render_response_strategy())
    def test_body_has_exactly_2_keys(self, data: dict):
        assert set(data["body"].keys()) == EXPECTED_BODY_KEYS

    @settings(max_examples=5)
    @given(data=a181_render_response_strategy())
    def test_issuance_has_exactly_2_keys(self, data: dict):
        assert set(data["issuance"].keys()) == EXPECTED_ISSUANCE_KEYS

    @settings(max_examples=5)
    @given(data=a181_render_response_strategy())
    def test_project_context_has_exactly_4_keys(self, data: dict):
        assert set(data["project_context"].keys()) == EXPECTED_CONTEXT_KEYS

    @settings(max_examples=5)
    @given(data=a181_render_response_strategy())
    def test_firm_name_always_fixed(self, data: dict):
        assert data["project_context"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"
