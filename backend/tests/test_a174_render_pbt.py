"""Property-Based Tests for A17-4 重大专业分歧事项记录 render strategy.

Property 2: 人员表 JSON round-trip — For any personnel array saved as JSON,
reloading SHALL return equivalent array with all rows/fields preserved.

**Validates: Requirements 11, Design §Property 2**
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a174_disagreement_record import _parse_personnel_json


# ─── Strategies ──────────────────────────────────────────────────────────────

@st.composite
def personnel_row_strategy(draw: st.DrawFn) -> dict:
    """Generate a single personnel row with name/position/role."""
    return {
        "name": draw(st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "Z")))),
        "position": draw(st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "Z")))),
        "role": draw(st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "Z")))),
    }


@st.composite
def personnel_array_strategy(draw: st.DrawFn) -> list[dict]:
    """Generate a valid personnel array (0~10 rows)."""
    return draw(st.lists(personnel_row_strategy(), min_size=0, max_size=10))


# ─── Property 2: Personnel JSON round-trip ───────────────────────────────────

class TestProperty2PersonnelJsonRoundTrip:
    """Property 2: 人员表 JSON round-trip.

    For any personnel array, serializing to JSON and parsing back via
    _parse_personnel_json SHALL return equivalent data.

    **Validates: Requirements 11, Design §Property 2**
    """

    @settings(max_examples=5)
    @given(personnel=personnel_array_strategy())
    def test_round_trip_preserves_length(self, personnel: list[dict]):
        """Round-trip preserves array length."""
        json_str = json.dumps(personnel)
        parsed = _parse_personnel_json(json_str)
        assert len(parsed) == len(personnel)

    @settings(max_examples=5)
    @given(personnel=personnel_array_strategy())
    def test_round_trip_preserves_names(self, personnel: list[dict]):
        """Round-trip preserves all name fields."""
        json_str = json.dumps(personnel)
        parsed = _parse_personnel_json(json_str)
        for orig, restored in zip(personnel, parsed):
            assert restored["name"] == orig["name"]

    @settings(max_examples=5)
    @given(personnel=personnel_array_strategy())
    def test_round_trip_preserves_positions(self, personnel: list[dict]):
        """Round-trip preserves all position fields."""
        json_str = json.dumps(personnel)
        parsed = _parse_personnel_json(json_str)
        for orig, restored in zip(personnel, parsed):
            assert restored["position"] == orig["position"]

    @settings(max_examples=5)
    @given(personnel=personnel_array_strategy())
    def test_round_trip_preserves_roles(self, personnel: list[dict]):
        """Round-trip preserves all role fields."""
        json_str = json.dumps(personnel)
        parsed = _parse_personnel_json(json_str)
        for orig, restored in zip(personnel, parsed):
            assert restored["role"] == orig["role"]

    @settings(max_examples=5)
    @given(personnel=personnel_array_strategy())
    def test_round_trip_output_has_exactly_three_keys(self, personnel: list[dict]):
        """Each parsed row has exactly {name, position, role} keys."""
        json_str = json.dumps(personnel)
        parsed = _parse_personnel_json(json_str)
        for row in parsed:
            assert set(row.keys()) == {"name", "position", "role"}

    def test_invalid_json_returns_empty(self):
        """Invalid JSON input gracefully returns empty list."""
        assert _parse_personnel_json("not valid json{[") == []
        assert _parse_personnel_json(None) == []
        assert _parse_personnel_json("") == []

    def test_non_list_json_returns_empty(self):
        """JSON that is not a list returns empty."""
        assert _parse_personnel_json('{"name": "test"}') == []
        assert _parse_personnel_json('"just a string"') == []
