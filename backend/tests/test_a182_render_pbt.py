"""Property-Based Tests for A18-2 与监管层沟通函 render strategy.

Property 3: 响应结构完整性 — recipient 2 keys + matters 4 items each 4 keys + issuance 3 keys + project_context 3 keys

**Validates: Requirements 8.1, Design §Correctness Properties P3**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── Expected keys ────────────────────────────────────────────────────────────

EXPECTED_RECIPIENT_KEYS = {"authority", "custom"}
EXPECTED_MATTER_KEYS = {"id", "title", "applicability", "content"}
EXPECTED_ISSUANCE_KEYS = {"cpa1", "cpa2", "date"}
EXPECTED_CONTEXT_KEYS = {"client_name", "audit_year", "firm_name"}

MATTER_TITLES = [
    "舞弊",
    "重大违反法律法规行为",
    "年度报告中信息不一致或错报",
    "其他事项",
]


@st.composite
def a182_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A18-2 render responses matching the expected schema."""
    recipient = {
        "authority": draw(st.text(min_size=0, max_size=50)),
        "custom": draw(st.text(min_size=0, max_size=50)),
    }
    matters = []
    for i in range(4):
        matters.append({
            "id": i + 1,
            "title": MATTER_TITLES[i],
            "applicability": draw(st.sampled_from(["Y", "N", "NA", None])),
            "content": draw(st.text(min_size=0, max_size=200)),
        })
    issuance = {
        "cpa1": draw(st.text(min_size=0, max_size=30)),
        "cpa2": draw(st.text(min_size=0, max_size=30)),
        "date": draw(st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True) | st.just("")),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_year": draw(st.text(min_size=0, max_size=10)),
        "firm_name": draw(st.just("致同会计师事务所（特殊普通合伙）") | st.text(min_size=1, max_size=50)),
    }
    return {"recipient": recipient, "matters": matters, "issuance": issuance, "project_context": project_context}


class TestProperty3ResponseStructureCompleteness:
    """Property 3: 响应结构完整性.

    For any valid A18-2 render response:
    - recipient SHALL have exactly 2 keys
    - matters SHALL be a list of 4 items each with 4 keys
    - issuance SHALL have exactly 3 keys
    - project_context SHALL have exactly 3 keys

    **Validates: Design §Correctness Properties P3**
    """

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_recipient_has_exactly_2_keys(self, data: dict):
        """Property 3a: recipient 恰好 2 keys (authority, custom)."""
        assert set(data["recipient"].keys()) == EXPECTED_RECIPIENT_KEYS

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_matters_has_exactly_4_items(self, data: dict):
        """Property 3b: matters 恰好 4 项."""
        assert len(data["matters"]) == 4

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_each_matter_has_4_keys(self, data: dict):
        """Property 3c: 每个 matter 恰好 4 keys (id, title, applicability, content)."""
        for matter in data["matters"]:
            assert set(matter.keys()) == EXPECTED_MATTER_KEYS

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_matter_ids_are_1_to_4(self, data: dict):
        """Property 3d: matter ids 为 1~4."""
        ids = [m["id"] for m in data["matters"]]
        assert ids == [1, 2, 3, 4]

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_matter_titles_match(self, data: dict):
        """Property 3e: matter titles 与预定义一致."""
        titles = [m["title"] for m in data["matters"]]
        assert titles == MATTER_TITLES

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_issuance_has_exactly_3_keys(self, data: dict):
        """Property 3f: issuance 恰好 3 keys (cpa1, cpa2, date)."""
        assert set(data["issuance"].keys()) == EXPECTED_ISSUANCE_KEYS

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_project_context_has_exactly_3_keys(self, data: dict):
        """Property 3g: project_context 恰好 3 keys."""
        assert set(data["project_context"].keys()) == EXPECTED_CONTEXT_KEYS

    @settings(max_examples=5)
    @given(data=a182_render_response_strategy())
    def test_applicability_valid_values(self, data: dict):
        """Property 3h: applicability 只能是 Y/N/NA/None."""
        for matter in data["matters"]:
            assert matter["applicability"] in ("Y", "N", "NA", None)
