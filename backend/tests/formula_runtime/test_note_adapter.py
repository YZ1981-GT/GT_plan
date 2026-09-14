"""Tests for NoteMutationAdapter.

Validates: Requirements 3, 4 | Properties P3, P4

Tests:
- Only auto cells accepted (non-auto rejected)
- prepare→apply round-trip (P3)
- Batch prepare/apply by section grouping
- Version conflict on restore
- Project isolation
- PBT max_examples=5 (Hypothesis fast profile)
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_runtime.adapters.note import (
    NoteMutationAdapter,
    _get_cell_value,
    _set_cell_value,
    _validate_locator,
    _version_hash,
    _group_by_section,
)
from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    DomainMutationAdapter,
    FormulaMutation,
    RestoredMutation,
)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run async coroutine synchronously for Hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_target(
    section: str = "revenue",
    row: str = "0",
    column: str = "amount",
    cell_type: str = "auto",
    project_id: uuid.UUID | None = None,
    year: int = 2025,
) -> CanonicalFormulaTarget:
    """Create a CanonicalFormulaTarget for note domain."""
    return CanonicalFormulaTarget(
        domain="note",
        project_id=project_id or uuid.UUID("5e193c68-0000-0000-0000-000000000001"),
        year=year,
        addr_id=f"note:{section}!{row}:{column}",
        locator={
            "section": section,
            "row": row,
            "column": column,
            "cell_type": cell_type,
        },
    )


def _make_note_row(
    project_id: uuid.UUID,
    year: int,
    section: str,
    table_data: dict | None = None,
):
    """Create a mock DisclosureNote row."""
    note = MagicMock()
    note.project_id = project_id
    note.year = year
    note.note_section = section
    note.table_data = table_data
    note.is_deleted = False
    note.updated_at = None
    return note


def _mock_session_with_notes(notes: list) -> AsyncMock:
    """Create a mock session that returns specified notes on execute."""
    session = AsyncMock()
    session.flush = AsyncMock()

    # Build lookup by (project_id, year, section)
    note_lookup: dict[tuple, Any] = {}
    for n in notes:
        key = (n.project_id, n.year, n.note_section)
        note_lookup[key] = n

    call_count = [0]

    async def _mock_execute(stmt):
        # Return appropriate note based on the query
        # Since we can't easily parse SA statements, we return notes sequentially
        # based on how many times execute is called
        result = MagicMock()
        if call_count[0] < len(notes):
            result.scalar_one_or_none = MagicMock(return_value=notes[call_count[0]])
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
        call_count[0] += 1
        return result

    session.execute = _mock_execute
    return session


# ─── Unit Tests: Helper Functions ─────────────────────────────────────────────


class TestHelpers:
    """Test helper functions."""

    def test_validate_locator_auto_accepted(self):
        target = _make_target(cell_type="auto")
        assert _validate_locator(target) is None

    def test_validate_locator_manual_rejected(self):
        target = _make_target(cell_type="manual")
        err = _validate_locator(target)
        assert err is not None
        assert "only auto cells" in err

    def test_validate_locator_missing_keys(self):
        target = CanonicalFormulaTarget(
            domain="note",
            project_id=uuid.uuid4(),
            year=2025,
            addr_id="note:x!0:a",
            locator={"section": "x"},  # missing row, column, cell_type
        )
        err = _validate_locator(target)
        assert err is not None
        assert "missing keys" in err

    def test_get_cell_value_dict_rows(self):
        data = {"rows": {"r1": {"col_a": Decimal("100.50")}}}
        assert _get_cell_value(data, "r1", "col_a") == Decimal("100.50")
        assert _get_cell_value(data, "r1", "col_b") is None
        assert _get_cell_value(data, "r2", "col_a") is None

    def test_get_cell_value_list_rows(self):
        data = {"rows": [{"key": "r1", "cells": {"amount": "200"}}]}
        assert _get_cell_value(data, "r1", "amount") == "200"
        assert _get_cell_value(data, "r2", "amount") is None

    def test_get_cell_value_none(self):
        assert _get_cell_value(None, "r", "c") is None
        assert _get_cell_value({}, "r", "c") is None

    def test_set_cell_value_dict_rows(self):
        data = {"rows": {"r1": {"a": 1}}}
        result = _set_cell_value(data, "r1", "b", 2)
        assert result["rows"]["r1"]["b"] == 2
        assert result["rows"]["r1"]["a"] == 1
        # Original not mutated
        assert "b" not in data["rows"]["r1"]

    def test_set_cell_value_creates_structure(self):
        result = _set_cell_value(None, "row1", "col1", "val")
        assert result["rows"]["row1"]["col1"] == "val"

    def test_version_hash_deterministic(self):
        v1 = _version_hash("hello")
        v2 = _version_hash("hello")
        assert v1 == v2
        assert len(v1) == 16

    def test_version_hash_different_values(self):
        assert _version_hash("a") != _version_hash("b")
        assert _version_hash(None) != _version_hash(0)

    def test_group_by_section(self):
        pid = uuid.uuid4()
        t1 = _make_target(section="revenue", project_id=pid)
        t2 = _make_target(section="revenue", row="1", project_id=pid)
        t3 = _make_target(section="cash", project_id=pid)
        groups = _group_by_section([t1, t2, t3])
        assert len(groups) == 2
        assert len(groups[(pid, 2025, "revenue")]) == 2
        assert len(groups[(pid, 2025, "cash")]) == 1


# ─── Unit Tests: Protocol Compliance ─────────────────────────────────────────


class TestProtocolCompliance:
    """Verify NoteMutationAdapter satisfies DomainMutationAdapter Protocol."""

    def test_is_runtime_checkable(self):
        session = AsyncMock()
        adapter = NoteMutationAdapter(session)
        assert isinstance(adapter, DomainMutationAdapter)

    def test_domain_attribute(self):
        session = AsyncMock()
        adapter = NoteMutationAdapter(session)
        assert adapter.domain == "note"


# ─── Unit Tests: prepare_many ─────────────────────────────────────────────────


class TestPrepareMany:
    """Test prepare_many behavior."""

    def test_rejects_non_auto_cells(self):
        """Non-auto cells must be rejected."""
        session = AsyncMock()
        adapter = NoteMutationAdapter(session)
        target = _make_target(cell_type="manual")

        with pytest.raises(ValueError, match="only auto cells"):
            _run(adapter.prepare_many([target], {"note:revenue!0:amount": Decimal("100")}))

    def test_rejects_missing_locator_keys(self):
        """Missing locator keys must be rejected."""
        session = AsyncMock()
        adapter = NoteMutationAdapter(session)
        target = CanonicalFormulaTarget(
            domain="note",
            project_id=uuid.uuid4(),
            year=2025,
            addr_id="note:x!0:a",
            locator={"section": "x", "row": "0"},  # missing column, cell_type
        )

        with pytest.raises(ValueError, match="missing keys"):
            _run(adapter.prepare_many([target], {}))

    def test_prepare_reads_existing_value(self):
        """prepare_many reads the current value from DB."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "500.00"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        mutations = _run(adapter.prepare_many(
            [target],
            {target.addr_id: Decimal("600.00")},
        ))

        assert len(mutations) == 1
        assert mutations[0].before_value == "500.00"
        assert mutations[0].after_value == "600.00"
        assert mutations[0].expected_version is not None

    def test_prepare_nonexistent_note_returns_none_before(self):
        """If note doesn't exist, before_value is None."""
        session = _mock_session_with_notes([])

        # Override execute to return None
        async def _exec(stmt):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r

        session.execute = _exec

        adapter = NoteMutationAdapter(session)
        target = _make_target()
        mutations = _run(adapter.prepare_many([target], {target.addr_id: "new"}))

        assert len(mutations) == 1
        assert mutations[0].before_value is None
        assert mutations[0].after_value == "new"


# ─── Unit Tests: apply_many ───────────────────────────────────────────────────


class TestApplyMany:
    """Test apply_many behavior."""

    def test_apply_writes_value(self):
        """apply_many writes after_value to the note cell."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "500.00"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        mutation = FormulaMutation(
            target=target,
            before_value="500.00",
            after_value="600.00",
            expected_version=_version_hash("500.00"),
        )

        applied = _run(adapter.apply_many([mutation]))

        assert len(applied) == 1
        assert isinstance(applied[0], AppliedMutation)
        assert applied[0].target is target
        assert applied[0].applied_version == _version_hash("600.00")
        # Verify the note's table_data was updated
        assert _get_cell_value(note.table_data, "0", "amount") == "600.00"

    def test_apply_version_conflict_raises(self):
        """apply_many raises on version mismatch (CAS)."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "changed_by_someone"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        mutation = FormulaMutation(
            target=target,
            before_value="500.00",
            after_value="600.00",
            expected_version=_version_hash("500.00"),  # Stale version
        )

        with pytest.raises(ValueError, match="Version conflict"):
            _run(adapter.apply_many([mutation]))

    def test_apply_nonexistent_note_raises(self):
        """apply_many raises if note section doesn't exist."""
        session = AsyncMock()

        async def _exec(stmt):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r

        session.execute = _exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        target = _make_target()
        mutation = FormulaMutation(
            target=target,
            before_value=None,
            after_value="100",
            expected_version=None,
        )

        with pytest.raises(ValueError, match="Note section not found"):
            _run(adapter.apply_many([mutation]))


# ─── Unit Tests: restore_many ─────────────────────────────────────────────────


class TestRestoreMany:
    """Test restore_many behavior."""

    def test_restore_success(self):
        """restore_many restores before_value when version matches."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        # Current value is "600.00" (was applied)
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "600.00"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        snapshot = FormulaMutation(
            target=target,
            before_value="500.00",
            after_value="600.00",
            expected_version=_version_hash("500.00"),
        )

        restored = _run(adapter.restore_many([snapshot]))

        assert len(restored) == 1
        assert restored[0].conflict is False
        assert restored[0].restored_version == _version_hash("500.00")
        # Cell should be back to before_value
        assert _get_cell_value(note.table_data, "0", "amount") == "500.00"

    def test_restore_conflict_when_version_changed(self):
        """restore_many reports conflict if cell was modified after apply."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        # Someone changed the value to "999" after our apply wrote "600.00"
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "999"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        snapshot = FormulaMutation(
            target=target,
            before_value="500.00",
            after_value="600.00",  # We expect current to be "600.00"
            expected_version=_version_hash("500.00"),
        )

        restored = _run(adapter.restore_many([snapshot]))

        assert len(restored) == 1
        assert restored[0].conflict is True
        assert "Version changed" in (restored[0].conflict_detail or "")

    def test_restore_missing_note_conflicts(self):
        """restore_many reports conflict if note section doesn't exist."""
        session = AsyncMock()

        async def _exec(stmt):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r

        session.execute = _exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        target = _make_target()
        snapshot = FormulaMutation(
            target=target,
            before_value="old",
            after_value="new",
        )

        restored = _run(adapter.restore_many([snapshot]))
        assert len(restored) == 1
        assert restored[0].conflict is True


# ─── Unit Tests: read_versions ────────────────────────────────────────────────


class TestReadVersions:
    """Test read_versions behavior."""

    def test_read_versions_existing(self):
        """read_versions returns hash of current values."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"amount": "500.00"}}}
        )
        session = _mock_session_with_notes([note])
        adapter = NoteMutationAdapter(session)

        target = _make_target(section="revenue", row="0", column="amount", project_id=pid)
        versions = _run(adapter.read_versions([target]))

        assert target.addr_id in versions
        assert versions[target.addr_id] == _version_hash("500.00")

    def test_read_versions_missing_note(self):
        """read_versions returns hash of None for missing note."""
        session = AsyncMock()

        async def _exec(stmt):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r

        session.execute = _exec
        adapter = NoteMutationAdapter(session)
        target = _make_target()

        versions = _run(adapter.read_versions([target]))
        assert versions[target.addr_id] == _version_hash(None)


# ─── Unit Tests: Batch Section Grouping ───────────────────────────────────────


class TestBatchGrouping:
    """Test that operations group by section for efficiency."""

    def test_prepare_groups_by_section(self):
        """Multiple targets in same section should use one DB query."""
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        note = _make_note_row(
            pid, 2025, "revenue",
            table_data={"rows": {"0": {"a": "1"}, "1": {"a": "2"}}}
        )

        execute_count = [0]

        async def _counted_exec(stmt):
            execute_count[0] += 1
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=note)
            return r

        session = AsyncMock()
        session.execute = _counted_exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        t1 = _make_target(section="revenue", row="0", column="a", project_id=pid)
        t2 = _make_target(section="revenue", row="1", column="a", project_id=pid)

        mutations = _run(adapter.prepare_many(
            [t1, t2],
            {t1.addr_id: "10", t2.addr_id: "20"},
        ))

        # Same section → only 1 DB query
        assert execute_count[0] == 1
        assert len(mutations) == 2


# ─── Unit Tests: Project Isolation ────────────────────────────────────────────


class TestProjectIsolation:
    """Test that different projects cannot access each other's notes."""

    def test_different_projects_separate_queries(self):
        """Targets from different projects use separate DB lookups."""
        pid1 = uuid.UUID("11111111-0000-0000-0000-000000000001")
        pid2 = uuid.UUID("22222222-0000-0000-0000-000000000002")

        note1 = _make_note_row(pid1, 2025, "revenue", {"rows": {"0": {"a": "p1"}}})
        note2 = _make_note_row(pid2, 2025, "revenue", {"rows": {"0": {"a": "p2"}}})

        call_idx = [0]
        notes_seq = [note1, note2]

        async def _exec(stmt):
            r = MagicMock()
            idx = min(call_idx[0], len(notes_seq) - 1)
            r.scalar_one_or_none = MagicMock(return_value=notes_seq[idx])
            call_idx[0] += 1
            return r

        session = AsyncMock()
        session.execute = _exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        t1 = _make_target(section="revenue", row="0", column="a", project_id=pid1)
        t2 = _make_target(section="revenue", row="0", column="a", project_id=pid2)

        mutations = _run(adapter.prepare_many(
            [t1, t2],
            {t1.addr_id: "new1", t2.addr_id: "new2"},
        ))

        # Two different projects → 2 separate queries
        assert call_idx[0] == 2
        assert len(mutations) == 2
        assert mutations[0].before_value == "p1"
        assert mutations[1].before_value == "p2"


# ─── PBT: Property-Based Tests ────────────────────────────────────────────────

# Strategies
st_section = st.sampled_from(["revenue", "cash", "equity", "expense", "receivable"])
st_row = st.text(min_size=1, max_size=5, alphabet="0123456789")
st_column = st.sampled_from(["amount", "balance", "total", "net", "adj"])
st_cell_value = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=20),
    st.decimals(min_value=-1_000_000, max_value=1_000_000, places=2, allow_nan=False, allow_infinity=False).map(str),
)


class TestPBTNoteAdapter:
    """Property-based tests for NoteMutationAdapter.

    **Validates: Requirements 3, 4 | P3, P4**
    """

    @settings(max_examples=5, deadline=None)
    @given(
        section=st_section,
        row=st_row,
        column=st_column,
        before=st_cell_value,
        after=st_cell_value,
    )
    def test_prepare_apply_roundtrip(self, section, row, column, before, after):
        """P3: prepare→apply round-trip preserves after_value in the cell.

        **Validates: Requirements 3.5, 4.5**
        """
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
        table_data = {"rows": {row: {column: before}}}
        note = _make_note_row(pid, 2025, section, table_data)

        # Track note reference across calls
        call_count = [0]

        async def _exec(stmt):
            call_count[0] += 1
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=note)
            return r

        session = AsyncMock()
        session.execute = _exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        target = _make_target(section=section, row=row, column=column, project_id=pid)

        # Step 1: prepare
        mutations = _run(adapter.prepare_many([target], {target.addr_id: after}))
        assert len(mutations) == 1
        assert mutations[0].before_value == before

        # Step 2: apply (reset call count for fresh query)
        call_count[0] = 0
        applied = _run(adapter.apply_many(mutations))
        assert len(applied) == 1

        # Verify the cell now contains after_value
        current = _get_cell_value(note.table_data, row, column)
        assert current == after

    @settings(max_examples=5, deadline=None)
    @given(
        cell_type=st.sampled_from(["manual", "input", "user", "formula", "locked"]),
    )
    def test_non_auto_cells_always_rejected(self, cell_type):
        """P4: Non-auto cell_type must always be rejected.

        **Validates: Requirements 4.5**
        """
        session = AsyncMock()
        adapter = NoteMutationAdapter(session)
        target = _make_target(cell_type=cell_type)

        with pytest.raises(ValueError, match="only auto cells"):
            _run(adapter.prepare_many([target], {target.addr_id: "any"}))

    @settings(max_examples=5, deadline=None)
    @given(
        section=st_section,
        row=st_row,
        column=st_column,
        value=st_cell_value,
    )
    def test_version_hash_consistency(self, section, row, column, value):
        """Version hashing is deterministic: same value → same hash.

        **Validates: Requirements 3.5**
        """
        h1 = _version_hash(value)
        h2 = _version_hash(value)
        assert h1 == h2
        assert len(h1) == 16

    @settings(max_examples=5, deadline=None)
    @given(
        section=st_section,
        row=st_row,
        column=st_column,
        original=st_cell_value,
        applied_val=st_cell_value,
        tampered=st_cell_value.filter(lambda x: x != "SENTINEL"),
    )
    def test_restore_detects_conflict(self, section, row, column, original, applied_val, tampered):
        """P4: restore detects conflict when current != after_value.

        **Validates: Requirements 4.5**
        """
        pid = uuid.UUID("5e193c68-0000-0000-0000-000000000001")

        # Simulate: cell was tampered to a different value than applied_val
        # Only creates a true conflict if tampered != applied_val
        if tampered == applied_val:
            return  # Not a conflict scenario, skip

        table_data = {"rows": {row: {column: tampered}}}
        note = _make_note_row(pid, 2025, section, table_data)

        async def _exec(stmt):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=note)
            return r

        session = AsyncMock()
        session.execute = _exec
        session.flush = AsyncMock()

        adapter = NoteMutationAdapter(session)
        target = _make_target(section=section, row=row, column=column, project_id=pid)

        snapshot = FormulaMutation(
            target=target,
            before_value=original,
            after_value=applied_val,
        )

        restored = _run(adapter.restore_many([snapshot]))
        assert len(restored) == 1
        assert restored[0].conflict is True
