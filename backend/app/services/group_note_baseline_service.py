"""Sprint A.7 — 集团附注模板基线服务.

主要 API:
- save_baseline(project_id, name, template_type, sections_data) → baseline_id
- apply_baseline(child_project_id, year, baseline_id) → dict
- diff_baseline(child_project_id, year, baseline_id) → dict
- sync_baseline(baseline_id, child_project_ids) → dict
- get_baseline_versions(parent_project_id) → list
- upgrade_baseline(baseline_id, new_sections_data, bump='minor'|'major') → new_version
- suggest_feedback(child_project_id, year, baseline_id) → list[dict]
- check_template_type(child_project_id, baseline_id) → dict

纯 async service，依赖 DB session。
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote, GroupNoteTemplateBaseline
from app.services.note_cell_merge import merge_table_data_preserving_cell_modes

__all__ = ["GroupNoteBaselineService"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_version(version_str: str) -> tuple[int, int]:
    """Parse 'v1.2' → (1, 2). Defaults to (1, 0) on failure."""
    try:
        s = version_str.lstrip("v")
        parts = s.split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return (1, 0)


def _format_version(major: int, minor: int) -> str:
    return f"v{major}.{minor}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _section_key(section: dict[str, Any]) -> str:
    """Stable key for a section (prefer section_id, fallback section_title)."""
    return section.get("section_id") or section.get("section_title") or ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GroupNoteBaselineService:
    """集团附注模板基线服务 (Sprint A.7)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------------------
    # A.7.1 + A.7.5: save_baseline
    # -----------------------------------------------------------------------

    async def save_baseline(
        self,
        parent_project_id: uuid.UUID,
        name: str,
        template_type: str = "soe",
        sections_data: list[dict[str, Any]] | None = None,
        parent_baseline_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Save a new baseline from parent project's disclosure_notes snapshot.

        If sections_data is None, snapshots from DB (parent project's notes).
        Returns: {"baseline_id": UUID, "version": str}
        """
        if sections_data is None:
            sections_data = await self._snapshot_sections(parent_project_id)

        # Determine version: find latest for this parent_project_id
        latest = await self._get_latest_baseline(parent_project_id)
        if latest:
            major, minor = _parse_version(latest.version)
            version = _format_version(major, minor + 1)
        else:
            version = "v1.0"

        baseline = GroupNoteTemplateBaseline(
            id=uuid.uuid4(),
            name=name,
            parent_project_id=parent_project_id,
            version=version,
            parent_baseline_id=parent_baseline_id,
            template_type=template_type,
            sections_data=sections_data,
            is_active=True,
            created_by=created_by,
            created_at=_now(),
            updated_at=_now(),
        )
        self.db.add(baseline)
        await self.db.flush()

        return {"baseline_id": baseline.id, "version": version}

    # -----------------------------------------------------------------------
    # A.7.3: apply_baseline
    # -----------------------------------------------------------------------

    async def apply_baseline(
        self,
        child_project_id: uuid.UUID,
        year: int,
        baseline_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Apply baseline to child project's disclosure_notes.

        - Copies sections_data (text + table + text_template_vars)
        - Uses merge_table_data_preserving_cell_modes to keep manual cells
        - Writes template_lineage
        """
        baseline = await self._get_baseline(baseline_id)
        if baseline is None:
            return {"success": False, "error": "baseline_not_found"}

        # A.7.10: template_type check
        type_check = await self.check_template_type(child_project_id, baseline_id)
        warning = type_check.get("warning")

        # Resolve full lineage chain (A.7.2)
        lineage_chain = await self._resolve_lineage_chain(baseline)

        # Get child's existing notes
        child_notes = await self._get_child_notes(child_project_id, year)
        child_by_key: dict[str, DisclosureNote] = {
            _section_key({"section_id": n.section_id, "section_title": n.section_title}): n
            for n in child_notes
        }

        applied_count = 0
        baseline_sections = baseline.sections_data if isinstance(baseline.sections_data, list) else []

        for section in baseline_sections:
            key = _section_key(section)
            if not key:
                continue

            existing = child_by_key.get(key)
            if existing:
                # Merge: preserve manual cells
                old_table = existing.table_data or {}
                new_table = section.get("table_data") or {}
                if new_table:
                    merged_table = merge_table_data_preserving_cell_modes(old_table, new_table)
                    existing.table_data = merged_table
                # Update text_content from baseline
                if section.get("text_content"):
                    existing.text_content = section["text_content"]
                # Update text_template_vars
                if section.get("text_template_vars"):
                    existing.text_template_vars = section["text_template_vars"]
                # Write lineage
                existing.template_lineage = _build_lineage_entry(
                    existing.template_lineage, baseline
                )
                existing.updated_at = _now()
            else:
                # Create new note from baseline section
                new_note = DisclosureNote(
                    id=uuid.uuid4(),
                    project_id=child_project_id,
                    year=year,
                    note_section=section.get("note_section", key),
                    section_title=section.get("section_title", ""),
                    section_id=section.get("section_id"),
                    level=section.get("level"),
                    parent_section_id=section.get("parent_section_id"),
                    sort_index=section.get("sort_index", 0),
                    table_data=section.get("table_data"),
                    text_content=section.get("text_content"),
                    text_template_vars=section.get("text_template_vars"),
                    template_lineage=_build_lineage_entry(None, baseline),
                    is_local_override=False,
                    created_at=_now(),
                    updated_at=_now(),
                )
                self.db.add(new_note)

            applied_count += 1

        await self.db.flush()

        result: dict[str, Any] = {
            "success": True,
            "applied_count": applied_count,
            "baseline_id": str(baseline.id),
            "baseline_version": baseline.version,
            "lineage_chain": lineage_chain,
        }
        if warning:
            result["warning"] = warning
        return result

    # -----------------------------------------------------------------------
    # A.7.1: diff_baseline
    # -----------------------------------------------------------------------

    async def diff_baseline(
        self,
        child_project_id: uuid.UUID,
        year: int,
        baseline_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compare child's current notes vs baseline.sections_data.

        Returns: {added, removed, modified, unchanged} section lists.
        """
        baseline = await self._get_baseline(baseline_id)
        if baseline is None:
            return {"error": "baseline_not_found"}

        child_notes = await self._get_child_notes(child_project_id, year)
        child_by_key: dict[str, DisclosureNote] = {
            _section_key({"section_id": n.section_id, "section_title": n.section_title}): n
            for n in child_notes
        }

        baseline_sections = baseline.sections_data if isinstance(baseline.sections_data, list) else []
        baseline_keys: set[str] = set()

        added: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []

        for section in baseline_sections:
            key = _section_key(section)
            if not key:
                continue
            baseline_keys.add(key)

            existing = child_by_key.get(key)
            if existing is None:
                added.append({"section_key": key, "title": section.get("section_title", "")})
            else:
                # Compare table_data and text_content
                is_modified = _is_section_modified(existing, section)
                entry = {"section_key": key, "title": section.get("section_title", "")}
                if is_modified:
                    modified.append(entry)
                else:
                    unchanged.append(entry)

        # Sections in child but not in baseline
        removed: list[dict[str, Any]] = []
        for key, note in child_by_key.items():
            if key and key not in baseline_keys:
                removed.append({"section_key": key, "title": note.section_title})

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
            "total_baseline": len(baseline_sections),
            "total_child": len(child_notes),
        }

    # -----------------------------------------------------------------------
    # A.7.7: sync_baseline (batch apply)
    # -----------------------------------------------------------------------

    async def sync_baseline(
        self,
        baseline_id: uuid.UUID,
        child_project_ids: list[uuid.UUID],
        year: int | None = None,
    ) -> dict[str, Any]:
        """Batch apply baseline to multiple child projects.

        Returns: {"results": [{project_id, success, ...}, ...]}
        """
        results: list[dict[str, Any]] = []
        for pid in child_project_ids:
            target_year = year or datetime.now().year
            try:
                r = await self.apply_baseline(pid, target_year, baseline_id)
                results.append({"project_id": str(pid), **r})
            except Exception as e:
                results.append({
                    "project_id": str(pid),
                    "success": False,
                    "error": str(e),
                })

        return {
            "baseline_id": str(baseline_id),
            "total": len(child_project_ids),
            "success_count": sum(1 for r in results if r.get("success")),
            "results": results,
        }

    # -----------------------------------------------------------------------
    # A.7.5: get_baseline_versions
    # -----------------------------------------------------------------------

    async def get_baseline_versions(
        self,
        parent_project_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Get all baseline versions for a parent project."""
        stmt = (
            select(GroupNoteTemplateBaseline)
            .where(GroupNoteTemplateBaseline.parent_project_id == parent_project_id)
            .order_by(GroupNoteTemplateBaseline.created_at.desc())
        )
        result = await self.db.execute(stmt)
        baselines = result.scalars().all()

        return [
            {
                "id": str(b.id),
                "name": b.name,
                "version": b.version,
                "template_type": b.template_type,
                "is_active": b.is_active,
                "parent_baseline_id": str(b.parent_baseline_id) if b.parent_baseline_id else None,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "sections_count": len(b.sections_data) if isinstance(b.sections_data, list) else 0,
            }
            for b in baselines
        ]

    # -----------------------------------------------------------------------
    # A.7.5: upgrade_baseline
    # -----------------------------------------------------------------------

    async def upgrade_baseline(
        self,
        baseline_id: uuid.UUID,
        new_sections_data: list[dict[str, Any]],
        bump: str = "minor",
    ) -> dict[str, Any]:
        """Create a new baseline version (bump minor or major).

        A.7.6: Returns needs_notification + affected_children for caller to notify.
        """
        old_baseline = await self._get_baseline(baseline_id)
        if old_baseline is None:
            return {"error": "baseline_not_found"}

        major, minor = _parse_version(old_baseline.version)
        if bump == "major":
            new_version = _format_version(major + 1, 0)
        else:
            new_version = _format_version(major, minor + 1)

        # Deactivate old baseline
        old_baseline.is_active = False
        old_baseline.updated_at = _now()

        # Create new baseline with parent_baseline_id pointing to old
        new_baseline = GroupNoteTemplateBaseline(
            id=uuid.uuid4(),
            name=old_baseline.name,
            parent_project_id=old_baseline.parent_project_id,
            version=new_version,
            parent_baseline_id=old_baseline.id,
            template_type=old_baseline.template_type,
            sections_data=new_sections_data,
            is_active=True,
            created_by=old_baseline.created_by,
            created_at=_now(),
            updated_at=_now(),
        )
        self.db.add(new_baseline)
        await self.db.flush()

        # A.7.6: Find affected children (projects that applied old baseline)
        affected = await self._find_affected_children(baseline_id)

        return {
            "new_baseline_id": str(new_baseline.id),
            "new_version": new_version,
            "old_version": old_baseline.version,
            "needs_notification": len(affected) > 0,
            "affected_children": affected,
        }

    # -----------------------------------------------------------------------
    # A.7.8: suggest_feedback
    # -----------------------------------------------------------------------

    async def suggest_feedback(
        self,
        child_project_id: uuid.UUID,
        year: int,
        baseline_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Suggest child modifications to merge back into baseline.

        Diffs child vs baseline → lists child-unique modifications.
        """
        diff = await self.diff_baseline(child_project_id, year, baseline_id)
        if "error" in diff:
            return []

        suggestions: list[dict[str, Any]] = []

        # Modified sections = child has diverged from baseline
        for entry in diff.get("modified", []):
            suggestions.append({
                "section_key": entry["section_key"],
                "title": entry.get("title", ""),
                "type": "modified",
                "suggestion": "Child has modified this section; consider merging back.",
            })

        # Removed = child has sections not in baseline (child-unique additions)
        for entry in diff.get("removed", []):
            suggestions.append({
                "section_key": entry["section_key"],
                "title": entry.get("title", ""),
                "type": "child_addition",
                "suggestion": "Child has a section not in baseline; consider adding to baseline.",
            })

        return suggestions

    # -----------------------------------------------------------------------
    # A.7.10: check_template_type
    # -----------------------------------------------------------------------

    async def check_template_type(
        self,
        child_project_id: uuid.UUID,
        baseline_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Check if child's template_type matches baseline's template_type.

        Returns: {"match": bool, "warning": str|None, ...}
        """
        baseline = await self._get_baseline(baseline_id)
        if baseline is None:
            return {"match": False, "warning": "baseline_not_found"}

        # Get child project's template_type from its notes or project record
        # For simplicity, check first note's implied type or use baseline type
        child_notes = await self._get_child_notes(child_project_id, None)
        # Infer child template_type from project (simplified: check if any note
        # has lineage indicating a different type)
        child_type = await self._infer_child_template_type(child_project_id)

        if child_type and child_type != baseline.template_type:
            return {
                "match": False,
                "child_type": child_type,
                "baseline_type": baseline.template_type,
                "warning": (
                    f"Template type mismatch: child is '{child_type}' "
                    f"but baseline is '{baseline.template_type}'. "
                    f"Apply may produce inconsistent results."
                ),
            }

        return {"match": True, "child_type": child_type, "baseline_type": baseline.template_type, "warning": None}

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _get_baseline(self, baseline_id: uuid.UUID) -> GroupNoteTemplateBaseline | None:
        stmt = select(GroupNoteTemplateBaseline).where(
            GroupNoteTemplateBaseline.id == baseline_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_latest_baseline(
        self, parent_project_id: uuid.UUID
    ) -> GroupNoteTemplateBaseline | None:
        stmt = (
            select(GroupNoteTemplateBaseline)
            .where(GroupNoteTemplateBaseline.parent_project_id == parent_project_id)
            .order_by(GroupNoteTemplateBaseline.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _snapshot_sections(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Snapshot current disclosure_notes for a project as sections_data."""
        stmt = (
            select(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.is_deleted == False,  # noqa: E712
            )
            .order_by(DisclosureNote.sort_index)
        )
        result = await self.db.execute(stmt)
        notes = result.scalars().all()

        sections: list[dict[str, Any]] = []
        for n in notes:
            sections.append({
                "section_id": n.section_id,
                "section_title": n.section_title,
                "note_section": n.note_section,
                "level": n.level,
                "parent_section_id": n.parent_section_id,
                "sort_index": n.sort_index,
                "table_data": deepcopy(n.table_data) if n.table_data else None,
                "text_content": n.text_content,
                "text_template_vars": deepcopy(n.text_template_vars) if n.text_template_vars else None,
            })
        return sections

    async def _get_child_notes(
        self, project_id: uuid.UUID, year: int | None
    ) -> list[DisclosureNote]:
        conditions = [
            DisclosureNote.project_id == project_id,
            DisclosureNote.is_deleted == False,  # noqa: E712
        ]
        if year is not None:
            conditions.append(DisclosureNote.year == year)
        stmt = select(DisclosureNote).where(*conditions)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _resolve_lineage_chain(
        self, baseline: GroupNoteTemplateBaseline
    ) -> list[dict[str, Any]]:
        """Resolve parent_baseline_id chain (A.7.2 multi-level lineage)."""
        chain: list[dict[str, Any]] = []
        current = baseline
        visited: set[uuid.UUID] = set()

        while current and current.id not in visited:
            visited.add(current.id)
            chain.append({
                "baseline_id": str(current.id),
                "version": current.version,
                "name": current.name,
            })
            if current.parent_baseline_id:
                current = await self._get_baseline(current.parent_baseline_id)
            else:
                break

        return chain

    async def _find_affected_children(self, baseline_id: uuid.UUID) -> list[str]:
        """Find project_ids that have applied this baseline (via template_lineage)."""
        # Query notes where template_lineage contains this baseline_id
        # JSONB containment: template_lineage @> [{"baseline_id": "..."}]
        # Simplified: scan notes with non-null template_lineage
        stmt = (
            select(DisclosureNote.project_id)
            .where(
                DisclosureNote.template_lineage.isnot(None),
                DisclosureNote.is_deleted == False,  # noqa: E712
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        project_ids = result.scalars().all()

        # Filter to those whose lineage references this baseline
        affected: list[str] = []
        for pid in project_ids:
            # Check at least one note in this project references the baseline
            note_stmt = (
                select(DisclosureNote)
                .where(
                    DisclosureNote.project_id == pid,
                    DisclosureNote.template_lineage.isnot(None),
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
                .limit(1)
            )
            note_result = await self.db.execute(note_stmt)
            note = note_result.scalar_one_or_none()
            if note and _lineage_contains_baseline(note.template_lineage, baseline_id):
                affected.append(str(pid))

        return affected

    async def _infer_child_template_type(self, project_id: uuid.UUID) -> str | None:
        """Infer template_type for a child project.

        Checks Project.template_type if available, otherwise returns None.
        """
        try:
            from app.models.core import Project
            stmt = select(Project).where(Project.id == project_id)
            result = await self.db.execute(stmt)
            project = result.scalar_one_or_none()
            if project and hasattr(project, "template_type"):
                return getattr(project, "template_type", None)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _build_lineage_entry(
    existing_lineage: Any,
    baseline: GroupNoteTemplateBaseline,
) -> list[dict[str, Any]]:
    """Build/append lineage entry for a note."""
    entries: list[dict[str, Any]] = []
    if isinstance(existing_lineage, list):
        entries = deepcopy(existing_lineage)

    entries.append({
        "baseline_id": str(baseline.id),
        "version": baseline.version,
        "applied_at": _now().isoformat(),
    })
    return entries


def _lineage_contains_baseline(lineage: Any, baseline_id: uuid.UUID) -> bool:
    """Check if lineage list contains a reference to baseline_id."""
    if not isinstance(lineage, list):
        return False
    bid_str = str(baseline_id)
    for entry in lineage:
        if isinstance(entry, dict) and entry.get("baseline_id") == bid_str:
            return True
    return False


def _is_section_modified(note: DisclosureNote, baseline_section: dict[str, Any]) -> bool:
    """Check if a child note differs from baseline section."""
    # Compare text_content
    note_text = note.text_content or ""
    baseline_text = baseline_section.get("text_content") or ""
    if note_text != baseline_text:
        return True

    # Compare table_data (simplified: check if keys/structure differ)
    note_table = note.table_data or {}
    baseline_table = baseline_section.get("table_data") or {}
    if note_table != baseline_table:
        return True

    return False
