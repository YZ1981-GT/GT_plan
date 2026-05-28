"""Tests for group_note_baseline_service.py (Sprint A.7).

15+ tests covering save/apply/diff/sync/upgrade/feedback/template_type_check.
Uses mock DB (AsyncSession mock).
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.group_note_baseline_service import (
    GroupNoteBaselineService,
    _build_lineage_entry,
    _format_version,
    _is_section_modified,
    _lineage_contains_baseline,
    _parse_version,
    _section_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_baseline(
    baseline_id=None,
    parent_project_id=None,
    version="v1.0",
    template_type="soe",
    sections_data=None,
    parent_baseline_id=None,
    is_active=True,
):
    b = MagicMock()
    b.id = baseline_id or uuid.uuid4()
    b.parent_project_id = parent_project_id or uuid.uuid4()
    b.version = version
    b.template_type = template_type
    b.sections_data = sections_data or []
    b.parent_baseline_id = parent_baseline_id
    b.is_active = is_active
    b.name = "Test Baseline"
    b.created_by = None
    b.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    b.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return b


def _make_note(
    project_id=None,
    year=2025,
    section_id="cash",
    section_title="货币资金",
    table_data=None,
    text_content=None,
    template_lineage=None,
    is_local_override=False,
    text_template_vars=None,
):
    n = MagicMock()
    n.id = uuid.uuid4()
    n.project_id = project_id or uuid.uuid4()
    n.year = year
    n.section_id = section_id
    n.section_title = section_title
    n.note_section = section_id
    n.table_data = table_data
    n.text_content = text_content
    n.template_lineage = template_lineage
    n.is_local_override = is_local_override
    n.text_template_vars = text_template_vars
    n.is_deleted = False
    n.sort_index = 0
    n.level = 1
    n.parent_section_id = None
    return n


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_version_normal(self):
        assert _parse_version("v1.0") == (1, 0)
        assert _parse_version("v2.3") == (2, 3)
        assert _parse_version("v10.15") == (10, 15)

    def test_parse_version_edge(self):
        assert _parse_version("") == (1, 0)
        assert _parse_version("invalid") == (1, 0)
        assert _parse_version("v1") == (1, 0)

    def test_format_version(self):
        assert _format_version(1, 0) == "v1.0"
        assert _format_version(2, 5) == "v2.5"

    def test_section_key_prefers_section_id(self):
        assert _section_key({"section_id": "cash", "section_title": "货币资金"}) == "cash"

    def test_section_key_fallback_title(self):
        assert _section_key({"section_title": "货币资金"}) == "货币资金"

    def test_section_key_empty(self):
        assert _section_key({}) == ""

    def test_build_lineage_entry_new(self):
        baseline = _make_baseline(baseline_id=uuid.UUID("12345678-1234-1234-1234-123456789abc"))
        result = _build_lineage_entry(None, baseline)
        assert len(result) == 1
        assert result[0]["baseline_id"] == "12345678-1234-1234-1234-123456789abc"
        assert result[0]["version"] == "v1.0"
        assert "applied_at" in result[0]

    def test_build_lineage_entry_append(self):
        existing = [{"baseline_id": "old", "version": "v0.9", "applied_at": "2025-01-01"}]
        baseline = _make_baseline()
        result = _build_lineage_entry(existing, baseline)
        assert len(result) == 2
        assert result[0]["baseline_id"] == "old"

    def test_lineage_contains_baseline_true(self):
        bid = uuid.uuid4()
        lineage = [{"baseline_id": str(bid), "version": "v1.0"}]
        assert _lineage_contains_baseline(lineage, bid) is True

    def test_lineage_contains_baseline_false(self):
        lineage = [{"baseline_id": "other", "version": "v1.0"}]
        assert _lineage_contains_baseline(lineage, uuid.uuid4()) is False

    def test_lineage_contains_baseline_none(self):
        assert _lineage_contains_baseline(None, uuid.uuid4()) is False

    def test_is_section_modified_same(self):
        note = _make_note(text_content="hello", table_data={"rows": []})
        section = {"text_content": "hello", "table_data": {"rows": []}}
        assert _is_section_modified(note, section) is False

    def test_is_section_modified_text_diff(self):
        note = _make_note(text_content="hello")
        section = {"text_content": "world"}
        assert _is_section_modified(note, section) is True

    def test_is_section_modified_table_diff(self):
        note = _make_note(table_data={"rows": [{"values": [1]}]})
        section = {"table_data": {"rows": [{"values": [2]}]}}
        assert _is_section_modified(note, section) is True


# ---------------------------------------------------------------------------
# Service tests (mock DB)
# ---------------------------------------------------------------------------


class TestSaveBaseline:
    @pytest.mark.asyncio
    async def test_save_baseline_first_version(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        pid = uuid.uuid4()

        # Mock: no existing baseline
        with patch.object(svc, "_get_latest_baseline", return_value=None):
            with patch.object(svc, "_snapshot_sections", return_value=[{"section_id": "cash"}]):
                result = await svc.save_baseline(pid, "My Baseline", "soe")

        assert result["version"] == "v1.0"
        assert "baseline_id" in result
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_baseline_increments_version(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        pid = uuid.uuid4()

        existing = _make_baseline(version="v1.2")
        with patch.object(svc, "_get_latest_baseline", return_value=existing):
            with patch.object(svc, "_snapshot_sections", return_value=[]):
                result = await svc.save_baseline(pid, "Baseline v2", "soe")

        assert result["version"] == "v1.3"

    @pytest.mark.asyncio
    async def test_save_baseline_with_explicit_sections(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        pid = uuid.uuid4()
        sections = [{"section_id": "s1", "section_title": "Test"}]

        with patch.object(svc, "_get_latest_baseline", return_value=None):
            result = await svc.save_baseline(pid, "B", "soe", sections_data=sections)

        assert result["version"] == "v1.0"


class TestApplyBaseline:
    @pytest.mark.asyncio
    async def test_apply_baseline_not_found(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        with patch.object(svc, "_get_baseline", return_value=None):
            result = await svc.apply_baseline(uuid.uuid4(), 2025, uuid.uuid4())

        assert result["success"] is False
        assert result["error"] == "baseline_not_found"

    @pytest.mark.asyncio
    async def test_apply_baseline_creates_new_notes(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金", "text_content": "hello"},
            ],
        )

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[]):
                        result = await svc.apply_baseline(child_pid, 2025, bid)

        assert result["success"] is True
        assert result["applied_count"] == 1
        # New note should be added
        db.add.assert_called()

    @pytest.mark.asyncio
    async def test_apply_baseline_merges_existing(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        child_pid = uuid.uuid4()
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {
                    "section_id": "cash",
                    "section_title": "货币资金",
                    "table_data": {"rows": [{"values": [100], "label": "银行存款"}]},
                    "text_content": "new text",
                },
            ],
        )

        existing_note = _make_note(
            project_id=child_pid,
            section_id="cash",
            section_title="货币资金",
            table_data={"rows": [{"values": [50], "label": "银行存款", "_cell_modes": {"0": "manual"}}]},
            text_content="old text",
        )

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "check_template_type", return_value={"match": True, "warning": None}):
                with patch.object(svc, "_resolve_lineage_chain", return_value=[]):
                    with patch.object(svc, "_get_child_notes", return_value=[existing_note]):
                        result = await svc.apply_baseline(child_pid, 2025, bid)

        assert result["success"] is True
        assert result["applied_count"] == 1
        # text_content should be updated
        assert existing_note.text_content == "new text"
        # template_lineage should be written
        assert existing_note.template_lineage is not None
        assert len(existing_note.template_lineage) >= 1
        assert existing_note.template_lineage[-1]["baseline_id"] == str(bid)


class TestDiffBaseline:
    @pytest.mark.asyncio
    async def test_diff_baseline_not_found(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        with patch.object(svc, "_get_baseline", return_value=None):
            result = await svc.diff_baseline(uuid.uuid4(), 2025, uuid.uuid4())

        assert result == {"error": "baseline_not_found"}

    @pytest.mark.asyncio
    async def test_diff_baseline_all_added(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金"},
                {"section_id": "ar", "section_title": "应收账款"},
            ],
        )

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "_get_child_notes", return_value=[]):
                result = await svc.diff_baseline(uuid.uuid4(), 2025, bid)

        assert len(result["added"]) == 2
        assert len(result["removed"]) == 0
        assert len(result["modified"]) == 0

    @pytest.mark.asyncio
    async def test_diff_baseline_mixed(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        baseline = _make_baseline(
            baseline_id=bid,
            sections_data=[
                {"section_id": "cash", "section_title": "货币资金", "text_content": "same"},
                {"section_id": "ar", "section_title": "应收账款", "text_content": "new"},
            ],
        )

        child_notes = [
            _make_note(section_id="cash", section_title="货币资金", text_content="same"),
            _make_note(section_id="inv", section_title="存货", text_content="child only"),
        ]

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "_get_child_notes", return_value=child_notes):
                result = await svc.diff_baseline(uuid.uuid4(), 2025, bid)

        assert len(result["added"]) == 1  # ar
        assert len(result["removed"]) == 1  # inv
        assert len(result["unchanged"]) == 1  # cash


class TestSyncBaseline:
    @pytest.mark.asyncio
    async def test_sync_multiple_children(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()
        children = [uuid.uuid4(), uuid.uuid4()]

        async def mock_apply(pid, year, baseline_id):
            return {"success": True, "applied_count": 1}

        with patch.object(svc, "apply_baseline", side_effect=mock_apply):
            result = await svc.sync_baseline(bid, children, year=2025)

        assert result["total"] == 2
        assert result["success_count"] == 2

    @pytest.mark.asyncio
    async def test_sync_partial_failure(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()
        children = [uuid.uuid4(), uuid.uuid4()]

        call_count = [0]

        async def mock_apply(pid, year, baseline_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "applied_count": 1}
            raise ValueError("DB error")

        with patch.object(svc, "apply_baseline", side_effect=mock_apply):
            result = await svc.sync_baseline(bid, children, year=2025)

        assert result["success_count"] == 1
        assert result["results"][1]["success"] is False


class TestUpgradeBaseline:
    @pytest.mark.asyncio
    async def test_upgrade_minor(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        old_baseline = _make_baseline(baseline_id=bid, version="v1.2")

        with patch.object(svc, "_get_baseline", return_value=old_baseline):
            with patch.object(svc, "_find_affected_children", return_value=["proj1"]):
                result = await svc.upgrade_baseline(bid, [{"section_id": "new"}], bump="minor")

        assert result["new_version"] == "v1.3"
        assert result["old_version"] == "v1.2"
        assert result["needs_notification"] is True
        assert result["affected_children"] == ["proj1"]
        assert old_baseline.is_active is False

    @pytest.mark.asyncio
    async def test_upgrade_major(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        old_baseline = _make_baseline(baseline_id=bid, version="v2.5")

        with patch.object(svc, "_get_baseline", return_value=old_baseline):
            with patch.object(svc, "_find_affected_children", return_value=[]):
                result = await svc.upgrade_baseline(bid, [], bump="major")

        assert result["new_version"] == "v3.0"
        assert result["needs_notification"] is False

    @pytest.mark.asyncio
    async def test_upgrade_not_found(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        with patch.object(svc, "_get_baseline", return_value=None):
            result = await svc.upgrade_baseline(uuid.uuid4(), [])

        assert result == {"error": "baseline_not_found"}


class TestSuggestFeedback:
    @pytest.mark.asyncio
    async def test_suggest_feedback_returns_modifications(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        diff_result = {
            "modified": [{"section_key": "cash", "title": "货币资金"}],
            "removed": [{"section_key": "custom", "title": "自定义"}],
            "added": [],
            "unchanged": [],
        }

        with patch.object(svc, "diff_baseline", return_value=diff_result):
            suggestions = await svc.suggest_feedback(uuid.uuid4(), 2025, uuid.uuid4())

        assert len(suggestions) == 2
        assert suggestions[0]["type"] == "modified"
        assert suggestions[1]["type"] == "child_addition"

    @pytest.mark.asyncio
    async def test_suggest_feedback_baseline_not_found(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        with patch.object(svc, "diff_baseline", return_value={"error": "baseline_not_found"}):
            suggestions = await svc.suggest_feedback(uuid.uuid4(), 2025, uuid.uuid4())

        assert suggestions == []


class TestCheckTemplateType:
    @pytest.mark.asyncio
    async def test_check_match(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        baseline = _make_baseline(baseline_id=bid, template_type="soe")

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "_get_child_notes", return_value=[]):
                with patch.object(svc, "_infer_child_template_type", return_value="soe"):
                    result = await svc.check_template_type(uuid.uuid4(), bid)

        assert result["match"] is True
        assert result["warning"] is None

    @pytest.mark.asyncio
    async def test_check_mismatch(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)
        bid = uuid.uuid4()

        baseline = _make_baseline(baseline_id=bid, template_type="soe")

        with patch.object(svc, "_get_baseline", return_value=baseline):
            with patch.object(svc, "_get_child_notes", return_value=[]):
                with patch.object(svc, "_infer_child_template_type", return_value="listed"):
                    result = await svc.check_template_type(uuid.uuid4(), bid)

        assert result["match"] is False
        assert "mismatch" in result["warning"].lower()


class TestResolveLineageChain:
    @pytest.mark.asyncio
    async def test_single_level(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        baseline = _make_baseline(parent_baseline_id=None)

        with patch.object(svc, "_get_baseline", return_value=None):
            chain = await svc._resolve_lineage_chain(baseline)

        assert len(chain) == 1
        assert chain[0]["baseline_id"] == str(baseline.id)

    @pytest.mark.asyncio
    async def test_multi_level(self):
        db = _mock_db()
        svc = GroupNoteBaselineService(db)

        grandparent = _make_baseline(version="v1.0", parent_baseline_id=None)
        parent = _make_baseline(version="v1.1", parent_baseline_id=grandparent.id)

        async def mock_get(bid):
            if bid == grandparent.id:
                return grandparent
            return None

        with patch.object(svc, "_get_baseline", side_effect=mock_get):
            chain = await svc._resolve_lineage_chain(parent)

        assert len(chain) == 2
        assert chain[0]["version"] == "v1.1"
        assert chain[1]["version"] == "v1.0"
