"""Property-Based Tests for A17-3 业务咨询记录 render strategy.

Property 2: 文件 tag JSON round-trip — 任意字符串列表存入再解析，结果一致

**Validates: Requirements 8.3**
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a173_consultation_record import _parse_file_list


class TestProperty2FileTagJsonRoundTrip:
    """Property 2: 文件 tag JSON round-trip.

    For any file tag array (list of non-empty strings) saved as JSON,
    reloading via _parse_file_list SHALL return the same array in order.

    **Validates: Requirements 8.3**
    """

    @settings(max_examples=5)
    @given(
        file_list=st.lists(
            st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",))),
            min_size=0,
            max_size=10,
        )
    )
    def test_round_trip_preserves_list(self, file_list: list[str]):
        """JSON serialize → _parse_file_list round-trip preserves content."""
        json_str = json.dumps(file_list, ensure_ascii=False)
        parsed = _parse_file_list(json_str)
        assert parsed == file_list

    @settings(max_examples=5)
    @given(
        file_list=st.lists(
            st.text(min_size=1, max_size=30),
            min_size=1,
            max_size=8,
        )
    )
    def test_round_trip_preserves_order(self, file_list: list[str]):
        """Order is preserved after round-trip."""
        json_str = json.dumps(file_list, ensure_ascii=False)
        parsed = _parse_file_list(json_str)
        for i, item in enumerate(file_list):
            assert parsed[i] == item

    @settings(max_examples=5)
    @given(
        file_list=st.lists(
            st.text(min_size=1, max_size=30),
            min_size=0,
            max_size=10,
        )
    )
    def test_round_trip_preserves_length(self, file_list: list[str]):
        """Length is preserved after round-trip."""
        json_str = json.dumps(file_list, ensure_ascii=False)
        parsed = _parse_file_list(json_str)
        assert len(parsed) == len(file_list)

    def test_empty_remark_returns_empty_list(self):
        """Empty/None remark gracefully returns []."""
        assert _parse_file_list(None) == []
        assert _parse_file_list("") == []

    def test_invalid_json_returns_empty_list(self):
        """Invalid JSON gracefully returns []."""
        assert _parse_file_list("not json") == []
        assert _parse_file_list("{invalid}") == []

    def test_non_list_json_returns_empty_list(self):
        """Non-list JSON (e.g. dict) gracefully returns []."""
        assert _parse_file_list('{"key": "value"}') == []
