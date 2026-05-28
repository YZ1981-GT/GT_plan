"""CI-7 卡点测试：apply_baseline 后 lineage 必有 baseline_id.

Sprint A.7 验收：
- apply_baseline 后每个受影响 note 的 template_lineage 必须包含 baseline_id
- lineage 是 list[dict]，每个 entry 必有 baseline_id + version + applied_at
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.group_note_baseline_service import (
    GroupNoteBaselineService,
    _build_lineage_entry,
)


def _make_baseline(baseline_id=None, version="v1.0", sections_data=None, template_type="soe"):
    b = MagicMock()
    b.id = baseline_id or uuid.uuid4()
    b.parent_project_id = uuid.uuid4()
    b.version = version
    b.template_type = template_type
    b.sections_data = sections_data or []
    b.parent_baseline_id = None
    b.is_active = True
    b.name = "CI-7 Baseline"
    b.created_by = None
    b.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    b.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return b


def _make_note(section_id="cash", section_title="货币资金", project_id=None):
    n = MagicMock()
    n.id = uuid.uuid4()
    n.project_id = project_id or uuid.uuid4()
    n.year = 2025
    n.section_id = section_id
    n.section_title = section_title
    n.note_section = section_id
    n.table_data = None
    n.text_content = None
    n.template_lineage = None
    n.is_local_override = False
    n.text_template_vars = None
    n.is_deleted = False
    n.sort_index = 0
    n.level = 1
    n.parent_section_id = None
    return n


class TestCI7LineageAfterApply:
    """CI-7: apply_baseline 后 lineage 必有 baseline_id."""

    @pytest.mark.asyncio
    async def test_apply_writes_lineage_with_baseline_id(self):
        """After apply_baseline, existing note must have template_lineage containing baseline_id."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金", "text_content": "test"},
            ],
        )

        existing_note = _make_note(section_id="cash", section_title="货币资金", project_id=child_pid)
        # Initially no lineage
        existing_note.template_lineage = None

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[existing_note]):
                        result = await svc.apply_baseline(child_pid, 2025, bid)

        assert result["success"] is True

        # CI-7 核心断言：lineage 必有 baseline_id
        lineage = existing_note.template_lineage
        assert lineage is not None, "template_lineage must not be None after apply"
        assert isinstance(lineage, list), "template_lineage must be a list"
        assert len(lineage) >= 1, "template_lineage must have at least one entry"

        entry = lineage[-1]
        assert "baseline_id" in entry, "lineage entry must have baseline_id"
        assert entry["baseline_id"] == str(bid), "lineage baseline_id must match applied baseline"
        assert "version" in entry, "lineage entry must have version"
        assert "applied_at" in entry, "lineage entry must have applied_at"

    @pytest.mark.asyncio
    async def test_apply_appends_to_existing_lineage(self):
        """If note already has lineage, apply should append (not overwrite)."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid_old = uuid.uuid4()
        bid_new = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid_new,
            version="v2.0",
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金"},
            ],
        )

        existing_note = _make_note(section_id="cash", section_title="货币资金", project_id=child_pid)
        existing_note.template_lineage = [
            {"baseline_id": str(bid_old), "version": "v1.0", "applied_at": "2025-06-01T00:00:00+00:00"}
        ]

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[existing_note]):
                        result = await svc.apply_baseline(child_pid, 2025, bid_new)

        assert result["success"] is True
        lineage = existing_note.template_lineage
        assert len(lineage) == 2, "Should append, not overwrite"
        assert lineage[0]["baseline_id"] == str(bid_old)
        assert lineage[1]["baseline_id"] == str(bid_new)

    @pytest.mark.asyncio
    async def test_apply_new_note_has_lineage(self):
        """When apply creates a new note (not existing), it must also have lineage."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {"section_id": "new_section", "section_title": "新章节", "note_section": "new_section"},
            ],
        )

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[]):
                        result = await svc.apply_baseline(child_pid, 2025, bid)

        assert result["success"] is True
        # Check the added note
        added_call = db.add.call_args
        new_note = added_call[0][0]
        assert new_note.template_lineage is not None
        assert isinstance(new_note.template_lineage, list)
        assert len(new_note.template_lineage) == 1
        assert new_note.template_lineage[0]["baseline_id"] == str(bid)

    def test_build_lineage_entry_structure(self):
        """Verify _build_lineage_entry produces correct structure."""
        bid = uuid.uuid4()
        baseline = _make_baseline(baseline_id=bid, version="v3.1")

        result = _build_lineage_entry(None, baseline)

        assert isinstance(result, list)
        assert len(result) == 1
        entry = result[0]
        assert entry["baseline_id"] == str(bid)
        assert entry["version"] == "v3.1"
        assert "applied_at" in entry
        # applied_at should be ISO format
        datetime.fromisoformat(entry["applied_at"])  # Should not raise

    @pytest.mark.asyncio
    async def test_apply_baseline_lineage_has_correct_version(self):
        """Lineage entry version must match the baseline version that was applied."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            version="v5.3",
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金"},
            ],
        )

        existing_note = _make_note(section_id="cash", section_title="货币资金", project_id=child_pid)

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[existing_note]):
                        await svc.apply_baseline(child_pid, 2025, bid)

        lineage = existing_note.template_lineage
        assert lineage[-1]["version"] == "v5.3"
