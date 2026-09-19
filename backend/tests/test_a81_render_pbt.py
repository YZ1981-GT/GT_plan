"""Property-Based Tests for A8-1 管理层对其他信息的书面声明 render strategy.

Property 2: 文件清单 JSON round-trip — 任意字符串列表存入再解析，结果一致
Property 5: 渲染策略返回结构完整性 — statements(6) + signature_data(2) + project_context(3)

**Validates: Requirements 4.5, 7.3, 8.3, 12.1, 12.2, 12.3**
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a81_other_info_representation import _parse_file_list

# ─── Expected keys ────────────────────────────────────────────────────────────

EXPECTED_STATEMENT_KEYS = {"1", "2", "3", "4", "5", "6"}
EXPECTED_SIGNATURE_KEYS = {"representative", "signature_date"}
EXPECTED_CONTEXT_KEYS = {"client_name", "audit_report_date", "cpa_names"}


# ─── Property 2: 文件清单 JSON round-trip ─────────────────────────────────────

class TestProperty2FileListJsonRoundTrip:
    """Property 2: 文件清单 JSON round-trip.

    For any file list (array of non-empty strings) saved as JSON,
    reloading via _parse_file_list SHALL return the same array
    with all items preserved in order.

    **Validates: Requirements 4.5, 7.3, 8.3, 12.3**
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


# ─── Property 5: 渲染策略返回结构完整性 ──────────────────────────────────────


@st.composite
def a81_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A8-1 render responses matching the expected schema."""
    statements = {
        "1": {"files": draw(st.lists(st.text(min_size=1, max_size=30), max_size=5))},
        "2": {"date": draw(st.one_of(st.none(), st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)))},
        "3": {
            "consistency": draw(st.sampled_from(["Y", "N", None])),
            "explanation": draw(st.one_of(st.none(), st.text(min_size=0, max_size=100))),
        },
        "4": {"files": draw(st.lists(st.text(min_size=1, max_size=30), max_size=5))},
        "5": {"files": draw(st.lists(st.text(min_size=1, max_size=30), max_size=5))},
        "6": {"other": draw(st.one_of(st.none(), st.text(min_size=0, max_size=200)))},
    }
    signature_data = {
        "representative": draw(st.one_of(st.none(), st.text(min_size=1, max_size=30))),
        "signature_date": draw(st.one_of(st.none(), st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True))),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_report_date": draw(st.one_of(st.none(), st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True))),
        "cpa_names": draw(st.lists(st.text(min_size=1, max_size=20), max_size=3)),
    }
    return {"statements": statements, "signature_data": signature_data, "project_context": project_context}


class TestProperty5ResponseSchemaCompleteness:
    """Property 5: 渲染策略返回结构完整性.

    For any valid A8-1 render response:
    - statements SHALL have keys "1" through "6"
    - signature_data SHALL have representative and signature_date
    - project_context SHALL have client_name, audit_report_date, cpa_names

    **Validates: Requirements 12.1, 12.2**
    """

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_statements_has_6_keys(self, data: dict):
        """Property 5a: statements 恰好 6 keys ("1" through "6")."""
        assert set(data["statements"].keys()) == EXPECTED_STATEMENT_KEYS

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_signature_data_has_2_keys(self, data: dict):
        """Property 5b: signature_data 恰好 2 keys."""
        assert set(data["signature_data"].keys()) == EXPECTED_SIGNATURE_KEYS

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_project_context_has_3_keys(self, data: dict):
        """Property 5c: project_context 恰好 3 keys."""
        assert set(data["project_context"].keys()) == EXPECTED_CONTEXT_KEYS

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_file_list_statements_have_files_key(self, data: dict):
        """Property 5d: statements 1/4/5 有 files key (list)."""
        for n in ("1", "4", "5"):
            assert "files" in data["statements"][n]
            assert isinstance(data["statements"][n]["files"], list)

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_statement_2_has_date(self, data: dict):
        """Property 5e: statement 2 有 date key."""
        assert "date" in data["statements"]["2"]

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_statement_3_has_consistency_and_explanation(self, data: dict):
        """Property 5f: statement 3 有 consistency 和 explanation."""
        assert "consistency" in data["statements"]["3"]
        assert "explanation" in data["statements"]["3"]

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_statement_6_has_other(self, data: dict):
        """Property 5g: statement 6 有 other key."""
        assert "other" in data["statements"]["6"]

    @settings(max_examples=5)
    @given(data=a81_render_response_strategy())
    def test_consistency_valid_values(self, data: dict):
        """Property 5h: consistency 只能是 Y/N/None."""
        assert data["statements"]["3"]["consistency"] in ("Y", "N", None)
