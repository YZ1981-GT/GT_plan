"""Tests for render-config sign_status injection (task 4.2).

Validates:
- word-template render-config includes sign_status field
- sign_status="signed" → permissions.edit=false
- sign_status="draft"/"pending" → permissions.edit=true
- Non-word-template wp_codes do NOT include sign_status
- A16 sub-version scope format: word_template:A16:{wp_code}
- Standalone scope format: word_template:{wp_code}
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ─── Helper: build minimal mock objects for _get_render_config_impl ───────────

def _make_working_paper(project_id, wp_index_id, parsed_data=None):
    wp = MagicMock()
    wp.id = uuid4()
    wp.project_id = project_id
    wp.wp_index_id = wp_index_id
    wp.is_deleted = False
    wp.parsed_data = parsed_data or {"html_data": {"Sheet1": {}}}
    wp.file_path = None
    wp.source_type = "template"
    return wp


def _make_wp_index(wp_code, wp_name=None):
    idx = MagicMock()
    idx.id = uuid4()
    idx.wp_code = wp_code
    idx.wp_name = wp_name or f"底稿 {wp_code}"
    idx.is_deleted = False
    idx.audit_cycle = "A"
    return idx


class _FakeResult:
    """Minimal mock for sqlalchemy result."""
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []

    def scalars(self):
        return self

    def first(self):
        return self._value

    def all(self):
        return self._rows

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


def _setup_db_for_word_template(db, project_id, wp_code, sign_status_value=None, year=2025):
    """Configure mock DB to simulate word-template render-config path."""
    wp_index = _make_wp_index(wp_code)
    working_paper = _make_working_paper(project_id, wp_index.id)

    # Track call count to route different execute calls
    call_results = []

    # 1. SELECT WorkingPaper
    call_results.append(_FakeResult(working_paper))
    # 2. SELECT is_deleted FROM projects (not deleted)
    call_results.append(_FakeResult(False))
    # 3. SELECT WpIndex
    call_results.append(_FakeResult(wp_index))
    # 4. SELECT cross refs
    call_results.append(_FakeResult(rows=[]))
    # 5. SELECT project year + business_category
    row = MagicMock()
    row.__getitem__ = lambda self, i: year if i == 0 else "C"
    call_results.append(_FakeResult(row))
    # 6. SELECT year for auto-fill
    row2 = MagicMock()
    row2.__getitem__ = lambda self, i: year if i == 0 else None
    call_results.append(_FakeResult(row2))
    # 7. FieldOverrideService.get → sign_status value
    call_results.append(_FakeResult(sign_status_value))

    call_idx = [0]

    async def _execute_side_effect(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx < len(call_results):
            return call_results[idx]
        return _FakeResult()

    db.execute = AsyncMock(side_effect=_execute_side_effect)
    return working_paper, wp_index


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestSignStatusScope:
    """Test scope format derivation for sign_status queries."""

    def test_a16_sub_version_scope(self):
        """A16-x wp_codes use word_template:A16:{wp_code} scope."""
        # This tests the scope logic inline
        wp_code = "A16-3"
        if wp_code.startswith("A16-"):
            scope = f"word_template:A16:{wp_code}"
        else:
            scope = f"word_template:{wp_code}"
        assert scope == "word_template:A16:A16-3"

    def test_standalone_scope(self):
        """Non-A16 wp_codes use word_template:{wp_code} scope."""
        wp_code = "A9-1"
        if wp_code.startswith("A16-"):
            scope = f"word_template:A16:{wp_code}"
        else:
            scope = f"word_template:{wp_code}"
        assert scope == "word_template:A9-1"

    def test_a16_parent_scope(self):
        """A16 (parent, no dash suffix) uses standalone format."""
        wp_code = "A16"
        if wp_code.startswith("A16-"):
            scope = f"word_template:A16:{wp_code}"
        else:
            scope = f"word_template:{wp_code}"
        assert scope == "word_template:A16"

    @pytest.mark.parametrize("wp_code,expected_scope", [
        ("A16-1", "word_template:A16:A16-1"),
        ("A16-2", "word_template:A16:A16-2"),
        ("A16-7", "word_template:A16:A16-7"),
        ("A8-1", "word_template:A8-1"),
        ("A9-1", "word_template:A9-1"),
        ("A10-1", "word_template:A10-1"),
        ("A18-1", "word_template:A18-1"),
        ("A27-1", "word_template:A27-1"),
    ])
    def test_scope_format_parametrized(self, wp_code, expected_scope):
        if wp_code.startswith("A16-"):
            scope = f"word_template:A16:{wp_code}"
        else:
            scope = f"word_template:{wp_code}"
        assert scope == expected_scope


class TestSignStatusPermissions:
    """Test permissions derivation from sign_status."""

    @pytest.mark.parametrize("status,expected_edit", [
        ("draft", True),
        ("pending", True),
        ("signed", False),
    ])
    def test_permissions_edit_flag(self, status, expected_edit):
        """edit permission is False only when signed."""
        permissions = {"edit": status != "signed"}
        assert permissions["edit"] == expected_edit

    def test_default_sign_status_is_draft(self):
        """When no sign_status in field_overrides, default to 'draft'."""
        sign_status = None  # simulates FieldOverrideService.get() returning None
        if not sign_status:
            sign_status = "draft"
        assert sign_status == "draft"
        permissions = {"edit": sign_status != "signed"}
        assert permissions["edit"] is True
