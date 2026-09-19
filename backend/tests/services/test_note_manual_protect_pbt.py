# Feature: disclosure-note-linkage-and-slimdown, Property 4: manual 单元格双路径不可覆盖
"""
Property-based test for manual cell protection during refill.

Validates that cells marked as manual (_cell_modes[str(col)] != "auto")
are never overwritten during refill_sections with skip_manual=True.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.report_models import ContentType, DisclosureNote
from app.services.disclosure_engine import DisclosureEngine


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()
YEAR = 2025

# Cell values that could be manual-entered
st_manual_value = st.one_of(
    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.integers(min_value=-1_000_000_000, max_value=1_000_000_000),
    st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.none(),
)

# Non-auto modes for manual cells
st_non_auto_mode = st.sampled_from(["manual", "locked", "user", "override"])


@st.composite
def st_manual_table_data(draw):
    """Generate table_data where at least some cells are manual (non-auto)."""
    num_cols = draw(st.integers(min_value=1, max_value=3))
    num_rows = draw(st.integers(min_value=1, max_value=4))
    headers = ["项目"] + [f"列{i}" for i in range(num_cols)]

    rows = []
    for _ in range(num_rows):
        values = [draw(st_manual_value) for _ in range(num_cols)]
        # Ensure at least one cell is non-auto
        cell_modes = {}
        has_manual = False
        for i in range(num_cols):
            if draw(st.booleans()):
                cell_modes[str(i)] = draw(st_non_auto_mode)
                has_manual = True
            else:
                cell_modes[str(i)] = "auto"

        # Force at least one manual cell if none were generated
        if not has_manual:
            forced_col = draw(st.integers(min_value=0, max_value=num_cols - 1))
            cell_modes[str(forced_col)] = "manual"

        rows.append({
            "label": draw(st.sampled_from(["银行存款", "现金", "应收账款", "存货"])),
            "values": values,
            "_cell_modes": cell_modes,
            "_cell_meta": {
                str(i): {"semantic": "closing_balance" if i == 0 else "opening_balance"}
                for i in range(num_cols)
            },
        })

    return {"headers": headers, "rows": rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> DisclosureEngine:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock()
    eng = DisclosureEngine(db)
    eng._wp_cache = {}
    eng._tb_cache = {}
    eng._wp_account_cache = {}
    eng._wp_fine_cache = {}
    eng._prior_notes_cache = {}
    return eng


def _make_note(
    section: str,
    content_type: ContentType = ContentType.table,
    table_data: dict | None = None,
) -> MagicMock:
    note = MagicMock(spec=DisclosureNote)
    note.note_section = section
    note.content_type = content_type
    note.table_data = table_data
    note.is_stale = True
    return note


# ---------------------------------------------------------------------------
# Property 4 (refresh path): manual 单元格重算路径不可覆盖
# ---------------------------------------------------------------------------


class TestProperty4ManualCellProtection:
    """Property 4: manual 单元格双路径不可覆盖（刷新路径分支）

    **Validates: Requirements 2.4, 3.6**

    For any cell marked _cell_modes[str(col)] != "auto", after
    refill_sections with skip_manual=True, the cell's value is unchanged.
    """

    @settings(max_examples=5)
    @given(table_data=st_manual_table_data())
    @pytest.mark.asyncio
    async def test_manual_cells_unchanged_after_refill(self, table_data: dict):
        """Manual cells (mode != 'auto') are never modified by refill_sections."""
        eng = _make_engine()
        note = _make_note("五、P4", content_type=ContentType.table, table_data=table_data)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [note]
        eng.db.execute = AsyncMock(return_value=mock_result)

        rows = table_data.get("rows", [])
        headers = table_data.get("headers", [])
        num_cols = max(0, len(headers) - 1)

        # Snapshot manual cells BEFORE refill
        manual_cells_before: dict[tuple[int, int], Any] = {}
        for row_idx, row in enumerate(rows):
            cell_modes = row.get("_cell_modes", {})
            values = row.get("values", [])
            for col_idx in range(min(num_cols, len(values))):
                mode = cell_modes.get(str(col_idx), "auto")
                if mode != "auto":
                    # Deep copy the value to avoid reference issues
                    manual_cells_before[(row_idx, col_idx)] = values[col_idx]

        # Build binding that covers all row labels
        binding_rows = {}
        for row in rows:
            label = row.get("label", "")
            if label not in binding_rows:
                binding_rows[label] = {
                    "binding": {
                        "closing_balance": {"source": "trial_balance", "field": "audited"},
                        "opening_balance": {"source": "trial_balance", "field": "opening"},
                    }
                }

        binding = {
            "tables": [{
                "header_normalize": [{"semantic": "row_label"}] + [
                    {"semantic": "closing_balance" if i == 0 else "opening_balance"}
                    for i in range(num_cols)
                ],
                "rows": binding_rows,
            }]
        }

        # dispatch_resolver always returns a clearly different value
        async def mock_dispatch(cell_binding, ctx):
            return 999_999.99  # Distinctly different from any generated value

        with (
            patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
            patch(
                "app.services.note_template_bindings_loader.get_binding_for_section",
                return_value=binding,
            ),
            patch(
                "app.services.note_source_resolvers.dispatch_resolver",
                side_effect=mock_dispatch,
            ),
            patch("sqlalchemy.orm.attributes.flag_modified"),
        ):
            await eng.refill_sections(PROJECT_ID, YEAR, ["五、P4"], skip_manual=True)

        # Verify: ALL manual cells retain their original values
        for (row_idx, col_idx), original_value in manual_cells_before.items():
            actual_value = rows[row_idx]["values"][col_idx]
            assert actual_value == original_value, (
                f"Manual cell [{row_idx}][{col_idx}] was modified! "
                f"Original={original_value}, After refill={actual_value}. "
                f"Mode={rows[row_idx]['_cell_modes'].get(str(col_idx))}"
            )


# ---------------------------------------------------------------------------
# Property 4 (auto_pull path): manual 单元格取数路径不可覆盖
# Feature: disclosure-note-linkage-and-slimdown, Property 4: manual 单元格双路径不可覆盖
# ---------------------------------------------------------------------------


class TestProperty4ManualCellAutoPullPath:
    """Property 4: manual 单元格双路径不可覆盖（auto_pull 路径分支）

    **Validates: Requirements 2.4, 3.6**

    For refs targeting manual cells, _is_manual_override returns True and
    pull_for_section skips them (available=False, reason="手工模式，跳过自动取数").
    """

    @settings(max_examples=5)
    @given(table_data=st_manual_table_data())
    @pytest.mark.asyncio
    async def test_manual_cells_skipped_by_auto_pull(self, table_data: dict):
        """auto_pull skips manual cells: available=False, reason='手工模式，跳过自动取数'."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services.note_auto_pull_service import NoteAutoPullService

        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        svc = NoteAutoPullService(db)

        rows = table_data.get("rows", [])
        headers = table_data.get("headers", [])
        num_cols = max(0, len(headers) - 1)

        # Build cross_refs targeting manual cells specifically
        manual_refs = []
        for row_idx, row in enumerate(rows):
            cell_modes = row.get("_cell_modes", {})
            for col_idx in range(num_cols):
                mode = cell_modes.get(str(col_idx), "auto")
                if mode != "auto":
                    manual_refs.append({
                        "ref_id": f"manual-{row_idx}-{col_idx}",
                        "target_wp": "D1-1",
                        "target_field": "审定数(期末)",
                        "direction": "inbound",
                        "auto_pull": True,
                        "source": {"row": row_idx, "column": col_idx},
                    })

        if not manual_refs:
            return  # Skip if no manual cells generated (shouldn't happen per strategy)

        schema = {"cross_refs": manual_refs}

        # dispatch_resolver should NOT be called for manual cells
        dispatch_called = {"count": 0}

        async def mock_dispatch(binding, ctx):
            dispatch_called["count"] += 1
            return 999_999.99

        with patch(
            "app.services.note_source_resolvers.dispatch_resolver",
            side_effect=mock_dispatch,
        ):
            results = await svc.pull_for_section(
                PROJECT_ID, YEAR, schema, note_table_data=table_data
            )

        # All refs targeting manual cells should be skipped
        assert len(results) == len(manual_refs)
        for result in results:
            assert result.available is False, (
                f"Manual cell ref {result.ref_id} should have available=False"
            )
            assert result.reason == "手工模式，跳过自动取数", (
                f"Expected reason '手工模式，跳过自动取数', got '{result.reason}'"
            )

        # dispatch_resolver should never have been called
        assert dispatch_called["count"] == 0, (
            f"dispatch_resolver was called {dispatch_called['count']} times for manual cells"
        )
