"""formula_runtime.adapters.note — 附注领域变更适配器。

NoteMutationAdapter 实现 DomainMutationAdapter 协议，
仅允许 auto cell 写入，按 section/row/column 批量操作。

locator 必含:
  - section: 附注章节标识 (note_section)
  - row: 行索引/key
  - column: 列 key
  - cell_type: 必须为 "auto" (仅公式运行时自动回填的单元格可写)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED_LOCATOR_KEYS = frozenset({"section", "row", "column", "cell_type"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_locator(target: CanonicalFormulaTarget) -> str | None:
    """Validate locator keys and cell_type. Returns error message or None."""
    missing = _REQUIRED_LOCATOR_KEYS - set(target.locator.keys())
    if missing:
        return f"locator missing keys: {sorted(missing)}"
    if target.locator.get("cell_type") != "auto":
        return f"only auto cells can be written; got cell_type={target.locator.get('cell_type')!r}"
    return None


def _version_hash(value: Any) -> str:
    """Compute a deterministic version string from a cell value."""
    serialized = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()[:16]


def _get_cell_value(table_data: dict | None, row: str, column: str) -> Any:
    """Extract cell value from table_data JSONB structure.

    Supports two common structures:
      1. {"rows": [{"key": ..., "cells": {"col": val}}]} — list of row dicts
      2. {"rows": {"row_key": {"col": val}}} — dict keyed by row
    Returns None if not found.
    """
    if not table_data:
        return None
    rows = table_data.get("rows")
    if rows is None:
        return None

    if isinstance(rows, list):
        for r in rows:
            if str(r.get("key", r.get("id", ""))) == row:
                cells = r.get("cells", r)
                return cells.get(column)
    elif isinstance(rows, dict):
        row_data = rows.get(row)
        if isinstance(row_data, dict):
            return row_data.get(column)
    return None


def _set_cell_value(table_data: dict | None, row: str, column: str, value: Any) -> dict:
    """Set cell value in table_data, returning a new dict (for ORM dirty detection).

    Creates structure if needed. Uses dict-keyed rows format for simplicity.
    """
    if table_data is None:
        table_data = {}
    # Deep-copy to ensure ORM dirty detection
    result = json.loads(json.dumps(table_data, default=str))
    rows = result.setdefault("rows", {})

    if isinstance(rows, list):
        # Find and update existing row or append
        found = False
        for r in rows:
            if str(r.get("key", r.get("id", ""))) == row:
                cells = r.setdefault("cells", {})
                cells[column] = value
                found = True
                break
        if not found:
            rows.append({"key": row, "cells": {column: value}})
    elif isinstance(rows, dict):
        row_data = rows.setdefault(row, {})
        row_data[column] = value
    else:
        result["rows"] = {row: {column: value}}

    return result


def _group_by_section(
    targets: list[CanonicalFormulaTarget],
) -> dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]]:
    """Group targets by (project_id, year, section) for batch DB access."""
    groups: dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]] = {}
    for t in targets:
        key = (t.project_id, t.year, t.locator["section"])
        groups.setdefault(key, []).append(t)
    return groups


# ---------------------------------------------------------------------------
# NoteMutationAdapter
# ---------------------------------------------------------------------------


class NoteMutationAdapter:
    """附注领域变更适配器，仅允许 auto cell 写入。"""

    domain: str = "note"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # prepare_many
    # ------------------------------------------------------------------

    async def prepare_many(
        self,
        targets: list[CanonicalFormulaTarget],
        values: dict[str, Any],
    ) -> list[FormulaMutation]:
        """Read current values and prepare mutations.

        Rejects non-auto cells. Groups by section for efficient batch DB access.
        """
        mutations: list[FormulaMutation] = []
        rejected: list[str] = []

        # Validate all targets first
        valid_targets: list[CanonicalFormulaTarget] = []
        for t in targets:
            err = _validate_locator(t)
            if err:
                rejected.append(f"{t.addr_id}: {err}")
                continue
            valid_targets.append(t)

        if rejected:
            # Raise with details about rejected targets
            raise ValueError(f"Rejected targets: {'; '.join(rejected)}")

        # Group by section for batch loading
        groups = _group_by_section(valid_targets)

        # Lazy import to avoid circular deps at module level
        from app.models.report_models import DisclosureNote

        for (project_id, year, section), group_targets in groups.items():
            # Batch load the note row for this section
            stmt = select(DisclosureNote).where(
                and_(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
            )
            result = await self._session.execute(stmt)
            note = result.scalar_one_or_none()

            for t in group_targets:
                row_key = t.locator["row"]
                col_key = t.locator["column"]

                before_value: Any = None
                expected_version: str | None = None

                if note is not None:
                    before_value = _get_cell_value(note.table_data, row_key, col_key)
                    expected_version = _version_hash(before_value)

                after_value = values.get(t.addr_id)
                # Convert Decimal to serializable form for JSON storage
                if isinstance(after_value, Decimal):
                    after_value = str(after_value)

                mutations.append(
                    FormulaMutation(
                        target=t,
                        before_value=before_value,
                        after_value=after_value,
                        expected_version=expected_version,
                    )
                )

        return mutations

    # ------------------------------------------------------------------
    # apply_many
    # ------------------------------------------------------------------

    async def apply_many(
        self,
        mutations: list[FormulaMutation],
    ) -> list[AppliedMutation]:
        """Write after_value to note cells, verify version via CAS."""
        from app.models.report_models import DisclosureNote

        applied: list[AppliedMutation] = []

        # Group mutations by section for batch processing
        section_groups: dict[tuple[UUID, int, str], list[FormulaMutation]] = {}
        for m in mutations:
            key = (m.target.project_id, m.target.year, m.target.locator["section"])
            section_groups.setdefault(key, []).append(m)

        for (project_id, year, section), group_mutations in section_groups.items():
            stmt = select(DisclosureNote).where(
                and_(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
            )
            result = await self._session.execute(stmt)
            note = result.scalar_one_or_none()

            if note is None:
                # Cannot apply to non-existent note — skip or raise
                for m in group_mutations:
                    raise ValueError(
                        f"Note section not found: project={project_id}, "
                        f"year={year}, section={section}"
                    )
                continue

            for m in group_mutations:
                row_key = m.target.locator["row"]
                col_key = m.target.locator["column"]

                # CAS: verify current version matches expected
                current_value = _get_cell_value(note.table_data, row_key, col_key)
                current_version = _version_hash(current_value)

                if m.expected_version is not None and current_version != m.expected_version:
                    raise ValueError(
                        f"Version conflict for {m.target.addr_id}: "
                        f"expected={m.expected_version}, current={current_version}"
                    )

                # Apply the new value
                note.table_data = _set_cell_value(
                    note.table_data, row_key, col_key, m.after_value
                )

            # Update timestamp
            note.updated_at = datetime.now(timezone.utc)

            # Flush (not commit — service-only flush pattern)
            await self._session.flush()

            # Generate applied results
            now_iso = datetime.now(timezone.utc).isoformat()
            for m in group_mutations:
                row_key = m.target.locator["row"]
                col_key = m.target.locator["column"]
                new_value = _get_cell_value(note.table_data, row_key, col_key)
                applied.append(
                    AppliedMutation(
                        target=m.target,
                        applied_version=_version_hash(new_value),
                        applied_at=now_iso,
                    )
                )

        return applied

    # ------------------------------------------------------------------
    # restore_many
    # ------------------------------------------------------------------

    async def restore_many(
        self,
        snapshots: list[FormulaMutation],
    ) -> list[RestoredMutation]:
        """Restore before_value with optimistic version check."""
        from app.models.report_models import DisclosureNote

        restored: list[RestoredMutation] = []

        # Group by section
        section_groups: dict[tuple[UUID, int, str], list[FormulaMutation]] = {}
        for m in snapshots:
            key = (m.target.project_id, m.target.year, m.target.locator["section"])
            section_groups.setdefault(key, []).append(m)

        for (project_id, year, section), group_mutations in section_groups.items():
            stmt = select(DisclosureNote).where(
                and_(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
            )
            result = await self._session.execute(stmt)
            note = result.scalar_one_or_none()

            for m in group_mutations:
                row_key = m.target.locator["row"]
                col_key = m.target.locator["column"]

                if note is None:
                    restored.append(
                        RestoredMutation(
                            target=m.target,
                            restored_version="",
                            conflict=True,
                            conflict_detail=f"Note section not found: {section}",
                        )
                    )
                    continue

                # Optimistic version check: current must match after_value version
                current_value = _get_cell_value(note.table_data, row_key, col_key)
                current_version = _version_hash(current_value)
                expected_after_version = _version_hash(m.after_value)

                if current_version != expected_after_version:
                    # Conflict: someone else modified the cell
                    restored.append(
                        RestoredMutation(
                            target=m.target,
                            restored_version=current_version,
                            conflict=True,
                            conflict_detail=(
                                f"Version changed since apply: "
                                f"expected={expected_after_version}, "
                                f"current={current_version}"
                            ),
                        )
                    )
                    continue

                # Restore before_value
                note.table_data = _set_cell_value(
                    note.table_data, row_key, col_key, m.before_value
                )
                restored_version = _version_hash(m.before_value)
                restored.append(
                    RestoredMutation(
                        target=m.target,
                        restored_version=restored_version,
                        conflict=False,
                    )
                )

            if note is not None:
                note.updated_at = datetime.now(timezone.utc)
                await self._session.flush()

        return restored

    # ------------------------------------------------------------------
    # read_versions
    # ------------------------------------------------------------------

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]:
        """Return current version strings for given targets."""
        from app.models.report_models import DisclosureNote

        versions: dict[str, str] = {}

        # Group by section
        groups = _group_by_section(targets)

        for (project_id, year, section), group_targets in groups.items():
            stmt = select(DisclosureNote).where(
                and_(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
            )
            result = await self._session.execute(stmt)
            note = result.scalar_one_or_none()

            for t in group_targets:
                row_key = t.locator["row"]
                col_key = t.locator["column"]

                if note is not None:
                    value = _get_cell_value(note.table_data, row_key, col_key)
                    versions[t.addr_id] = _version_hash(value)
                else:
                    versions[t.addr_id] = _version_hash(None)

        return versions
