# Feature: disclosure-note-linkage-and-slimdown, Property 5: auto_pull 取数与来源值一致
# Feature: disclosure-note-linkage-and-slimdown, Property 6: auto_pull 值只读且可溯源
# Feature: disclosure-note-linkage-and-slimdown, Property 7: 取数失败降级不阻断渲染
# Feature: disclosure-note-linkage-and-slimdown, Property 8: auto_pull 不污染手填持久化
"""
Property-based tests for NoteAutoPullService.

Validates:
- P5: auto_pull returned value equals dispatch_resolver output
- P6: available=True results have non-empty source_label and value is NOT written to table_data
- P7: If some refs fail, the rest still return results. No exception propagates. Failed refs have available=False
- P8: After pull_for_section, the input note_table_data is byte-for-byte unchanged
"""

from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_auto_pull_service import AutoPullResult, NoteAutoPullService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()
YEAR = 2025

st_wp_code = st.sampled_from(["D1-1", "D2-1", "E1-1", "F2-1", "H1-1", "K8-1"])
st_target_field = st.sampled_from(["审定数(期末)", "审定数(期初)", "本期发生额", "合计"])
st_source_cell = st.sampled_from(["B7", "C12", "D3", "E15", None])
st_ref_id = st.text(min_size=4, max_size=8, alphabet=st.characters(whitelist_categories=("L", "N")))

st_numeric_value = st.one_of(
    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.integers(min_value=-1_000_000_000, max_value=1_000_000_000),
)


@st.composite
def st_cross_ref(draw):
    """Generate a single cross_ref entry with auto_pull=True, direction=inbound."""
    return {
        "ref_id": draw(st_ref_id),
        "target_wp": draw(st_wp_code),
        "target_field": draw(st_target_field),
        "direction": "inbound",
        "auto_pull": True,
        "source": {"row": draw(st.integers(min_value=0, max_value=3)),
                   "column": draw(st.integers(min_value=0, max_value=3))},
        "source_cell": draw(st_source_cell),
    }


@st.composite
def st_schema_with_refs(draw, min_refs=1, max_refs=4):
    """Generate a schema dict with cross_refs containing auto_pull inbound refs."""
    n = draw(st.integers(min_value=min_refs, max_value=max_refs))
    refs = [draw(st_cross_ref()) for _ in range(n)]
    return {"cross_refs": refs}


@st.composite
def st_table_data(draw):
    """Generate note_table_data with auto mode cells (no manual override)."""
    num_cols = draw(st.integers(min_value=1, max_value=4))
    num_rows = draw(st.integers(min_value=1, max_value=4))
    headers = ["项目"] + [f"列{i}" for i in range(num_cols)]
    rows = []
    for _ in range(num_rows):
        values = [draw(st_numeric_value) for _ in range(num_cols)]
        cell_modes = {str(i): "auto" for i in range(num_cols)}
        rows.append({
            "label": draw(st.sampled_from(["银行存款", "现金", "应收账款"])),
            "values": values,
            "_cell_modes": cell_modes,
        })
    return {"headers": headers, "rows": rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> NoteAutoPullService:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    return NoteAutoPullService(db)


# ---------------------------------------------------------------------------
# Property 5: auto_pull 取数与来源值一致
# ---------------------------------------------------------------------------


class TestProperty5AutoPullValueConsistency:
    """Property 5: auto_pull 取数与来源值一致

    **Validates: Requirements 3.1, 3.2, 3.9**

    For any schema with auto_pull==true&&direction==inbound cross_refs,
    the returned value equals dispatch_resolver output.
    """

    @settings(max_examples=5)
    @given(
        schema=st_schema_with_refs(min_refs=1, max_refs=3),
        resolver_value=st_numeric_value,
    )
    @pytest.mark.asyncio
    async def test_returned_value_equals_resolver_output(
        self, schema: dict, resolver_value: Any
    ):
        """auto_pull value equals the value returned by dispatch_resolver."""
        svc = _make_service()

        async def mock_dispatch(binding, ctx):
            return resolver_value

        with patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ):
            results = await svc.pull_for_section(
                PROJECT_ID, YEAR, schema, note_table_data=None
            )

        # Every qualifying ref should have a result with value == resolver_value
        qualifying_refs = [
            r for r in schema.get("cross_refs", [])
            if r.get("auto_pull") is True and r.get("direction") == "inbound"
        ]
        assert len(results) == len(qualifying_refs)

        for result in results:
            assert result.available is True
            assert result.value == resolver_value


# ---------------------------------------------------------------------------
# Property 6: auto_pull 值只读且可溯源
# ---------------------------------------------------------------------------


class TestProperty6ReadOnlyAndTraceable:
    """Property 6: auto_pull 值只读且可溯源

    **Validates: Requirements 3.3**

    For available==true results, source_label is non-empty and value was NOT
    written to table_data.
    """

    @settings(max_examples=5)
    @given(
        schema=st_schema_with_refs(min_refs=1, max_refs=3),
        table_data=st_table_data(),
        resolver_value=st_numeric_value,
    )
    @pytest.mark.asyncio
    async def test_available_results_have_source_label_and_no_write(
        self, schema: dict, table_data: dict, resolver_value: Any
    ):
        """available=True results have non-empty source_label; table_data unchanged."""
        svc = _make_service()
        table_data_before = json.dumps(table_data, sort_keys=True, ensure_ascii=False)

        async def mock_dispatch(binding, ctx):
            return resolver_value

        with patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ):
            results = await svc.pull_for_section(
                PROJECT_ID, YEAR, schema, note_table_data=table_data
            )

        for result in results:
            if result.available:
                # source_label must be non-empty for traceable results
                assert result.source_label != "", (
                    f"ref_id={result.ref_id} available=True but source_label is empty"
                )

        # table_data must not be mutated (value is read-only, never written)
        table_data_after = json.dumps(table_data, sort_keys=True, ensure_ascii=False)
        assert table_data_before == table_data_after, (
            "table_data was mutated by pull_for_section (auto_pull should be read-only)"
        )


# ---------------------------------------------------------------------------
# Property 7: 取数失败降级不阻断渲染
# ---------------------------------------------------------------------------


class TestProperty7FailureDegradation:
    """Property 7: 取数失败降级不阻断渲染

    **Validates: Requirements 3.4, 3.10**

    If some refs fail, the rest still return results. No exception propagates.
    Failed refs have available=False.
    """

    @settings(max_examples=5)
    @given(schema=st_schema_with_refs(min_refs=2, max_refs=4))
    @pytest.mark.asyncio
    async def test_partial_failure_does_not_block_others(self, schema: dict):
        """Some refs raise exceptions; rest still return successfully."""
        svc = _make_service()
        call_count = {"n": 0}

        async def mock_dispatch_alternating(binding, ctx):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                raise RuntimeError("Simulated resolver failure")
            return 42.0

        with patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch_alternating,
        ):
            # Must NOT raise
            results = await svc.pull_for_section(
                PROJECT_ID, YEAR, schema, note_table_data=None
            )

        qualifying_refs = [
            r for r in schema.get("cross_refs", [])
            if r.get("auto_pull") is True and r.get("direction") == "inbound"
        ]
        # Results list covers ALL qualifying refs (1:1 correspondence)
        assert len(results) == len(qualifying_refs)

        # At least some should be available, some should not
        available_results = [r for r in results if r.available]
        failed_results = [r for r in results if not r.available]
        assert len(available_results) > 0, "Expected at least one successful result"
        assert len(failed_results) > 0, "Expected at least one failed result"

        # Failed results must have a non-empty reason
        for r in failed_results:
            assert r.available is False
            assert r.reason != "", f"Failed ref {r.ref_id} has empty reason"


# ---------------------------------------------------------------------------
# Property 8: auto_pull 不污染手填持久化
# ---------------------------------------------------------------------------


class TestProperty8NoPollution:
    """Property 8: auto_pull 不污染手填持久化

    **Validates: Requirements 3.7**

    After pull_for_section, the input note_table_data is byte-for-byte unchanged
    (auto_pull is read-only, never writes to table_data).
    """

    @settings(max_examples=5)
    @given(
        schema=st_schema_with_refs(min_refs=1, max_refs=4),
        table_data=st_table_data(),
        resolver_value=st_numeric_value,
    )
    @pytest.mark.asyncio
    async def test_table_data_unchanged_after_pull(
        self, schema: dict, table_data: dict, resolver_value: Any
    ):
        """note_table_data is byte-for-byte unchanged after pull_for_section."""
        svc = _make_service()
        # Deep copy for comparison
        original_snapshot = copy.deepcopy(table_data)

        async def mock_dispatch(binding, ctx):
            return resolver_value

        with patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ):
            await svc.pull_for_section(
                PROJECT_ID, YEAR, schema, note_table_data=table_data
            )

        # table_data must be identical to the deep copy taken before
        assert table_data == original_snapshot, (
            "table_data was mutated by pull_for_section! "
            f"Before: {json.dumps(original_snapshot, default=str)[:200]}... "
            f"After: {json.dumps(table_data, default=str)[:200]}..."
        )


# ---------------------------------------------------------------------------
# Task 11.6: detect_changes 检测 auto_pull 受影响单元测试
# ---------------------------------------------------------------------------


class TestDetectChangesAutoPull:
    """detect_changes 检测 auto_pull 受影响单元测试

    Verify that CrossRefService.detect_changes detects auto_pull refs as
    affected when source WP cell changes.

    **Validates: Requirements 3.5**
    """

    def test_detect_changes_finds_affected_auto_pull_ref(self):
        """When source WP cell changes, detect_changes returns the affected ref."""
        from app.services.cross_ref_service import CrossRefService

        svc = CrossRefService()

        # Inject a test reference that simulates an auto_pull cross_ref
        test_ref = {
            "ref_id": "TEST-AP-01",
            "source_wp": "D1",
            "source_sheet": "审定表D1-1",
            "source_cell": "D1",
            "target_wp": "NOTE",
            "target_sheet": "附注",
            "target_cell": "5.3 应收票据合计",
        }
        # Override references cache for test isolation
        svc._references = [test_ref]

        old_html = {"cells": {"D1": {"v": 100000}}}
        new_html = {"cells": {"D1": {"v": 200000}}}

        changes = svc.detect_changes(
            wp_code="D1",
            sheet_name="审定表D1-1",
            old_html_data=old_html,
            new_html_data=new_html,
            changed_cells=["D1"],
        )

        assert len(changes) == 1
        assert changes[0].ref_id == "TEST-AP-01"
        assert changes[0].source_wp_code == "D1"
        assert changes[0].target_wp_code == "NOTE"

    def test_detect_changes_no_match_when_unchanged(self):
        """When html_data is unchanged, detect_changes returns empty."""
        from app.services.cross_ref_service import CrossRefService

        svc = CrossRefService()
        svc._references = [{
            "ref_id": "TEST-AP-02",
            "source_wp": "D1",
            "source_sheet": "审定表D1-1",
            "source_cell": "D1",
            "target_wp": "NOTE",
            "target_sheet": "附注",
            "target_cell": "5.3",
        }]

        same_html = {"cells": {"D1": {"v": 100000}}}

        changes = svc.detect_changes(
            wp_code="D1",
            sheet_name="审定表D1-1",
            old_html_data=same_html,
            new_html_data=same_html,
            changed_cells=["D1"],
        )

        assert len(changes) == 0

    def test_detect_changes_no_match_different_wp_code(self):
        """When wp_code doesn't match, detect_changes returns empty."""
        from app.services.cross_ref_service import CrossRefService

        svc = CrossRefService()
        svc._references = [{
            "ref_id": "TEST-AP-03",
            "source_wp": "D1",
            "source_sheet": "审定表D1-1",
            "source_cell": "D1",
            "target_wp": "NOTE",
            "target_sheet": "附注",
            "target_cell": "5.3",
        }]

        old_html = {"cells": {"D1": {"v": 100}}}
        new_html = {"cells": {"D1": {"v": 200}}}

        # Using a different wp_code that doesn't match
        changes = svc.detect_changes(
            wp_code="E1",
            sheet_name="审定表D1-1",
            old_html_data=old_html,
            new_html_data=new_html,
        )

        assert len(changes) == 0

    def test_detect_changes_first_save_detected(self):
        """First save (old_html_data=None) is detected as change."""
        from app.services.cross_ref_service import CrossRefService

        svc = CrossRefService()
        svc._references = [{
            "ref_id": "TEST-AP-04",
            "source_wp": "D2",
            "source_sheet": "审定表D2-1",
            "source_cell": "B5",
            "target_wp": "NOTE",
            "target_sheet": "附注",
            "target_cell": "5.7",
        }]

        new_html = {"cells": {"B5": {"v": 999}}}

        changes = svc.detect_changes(
            wp_code="D2",
            sheet_name="审定表D2-1",
            old_html_data=None,
            new_html_data=new_html,
        )

        assert len(changes) == 1
        assert changes[0].ref_id == "TEST-AP-04"
