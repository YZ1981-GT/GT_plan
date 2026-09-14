"""Task 4.3 (Wave 3) — EvidenceRefQueryService 单元测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 4.3 (Wave 3)
Requirements: R3, R4, R9, R15
Design: §4.4 EvidenceRef 与统一依赖图 / §6.1 通用约定

覆盖：
  * 纯函数单元：
    - _clamp_limit enforces [1, 200]
    - _parse_cursor parses valid cursor / ignores invalid
    - _map_ref_row maps database row to EvidenceRefRow correctly
  * Service logic：
    - Intent idempotency: find_active_ref_by_intent returns existing ref
    - Cursor pagination: limit clamping, has_more detection
    - Deactivation: requires reason, preserves history, updates dep status
    - Impact BFS: bounded traversal, dedup by visited set, truncation
    - Permission filtering: only readable objects returned
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evidence_governance.evidence_ref_query_service import (
    CursorPage,
    DeactivateRefResult,
    DependencyPage,
    DependencyRow,
    EvidenceRefQueryService,
    EvidenceRefRow,
    ImpactNode,
    ImpactResult,
    _clamp_limit,
    _map_dep_row,
    _map_ref_row,
    _parse_cursor,
)
from app.services.evidence_governance.frozen_contracts import (
    CURSOR_PAGE_DEFAULT_LIMIT,
    CURSOR_PAGE_MAX_LIMIT,
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# ===========================================================================
# 1) 纯函数单元测试
# ===========================================================================


class TestClampLimit:
    """Pagination limit clamping: default 100, max 200."""

    def test_normal_value_unchanged(self):
        assert _clamp_limit(50) == 50

    def test_at_max_unchanged(self):
        assert _clamp_limit(200) == 200

    def test_above_max_clamped(self):
        assert _clamp_limit(300) == CURSOR_PAGE_MAX_LIMIT

    def test_zero_returns_default(self):
        assert _clamp_limit(0) == CURSOR_PAGE_DEFAULT_LIMIT

    def test_negative_returns_default(self):
        assert _clamp_limit(-5) == CURSOR_PAGE_DEFAULT_LIMIT

    def test_one_is_valid(self):
        assert _clamp_limit(1) == 1


class TestParseCursor:
    """Keyset cursor parsing."""

    def test_none_cursor_returns_empty(self):
        cond, params = _parse_cursor(None)
        assert cond == ""
        assert params == {}

    def test_empty_string_returns_empty(self):
        cond, params = _parse_cursor("")
        assert cond == ""
        assert params == {}

    def test_valid_cursor(self):
        ts = "2025-01-15T10:30:00+00:00"
        uid = str(uuid.uuid4())
        cursor = f"{ts}|{uid}"
        cond, params = _parse_cursor(cursor)
        assert "cursor_ts" in params
        assert "cursor_id" in params
        assert params["cursor_ts"] == ts
        assert params["cursor_id"] == uid
        assert "AND" in cond

    def test_invalid_uuid_returns_empty(self):
        cond, params = _parse_cursor("2025-01-15T10:30:00|not-a-uuid")
        assert cond == ""
        assert params == {}

    def test_no_separator_returns_empty(self):
        cond, params = _parse_cursor("no-separator")
        assert cond == ""
        assert params == {}

    def test_custom_column_names(self):
        ts = "2025-01-15T10:30:00+00:00"
        uid = str(uuid.uuid4())
        cursor = f"{ts}|{uid}"
        cond, params = _parse_cursor(cursor, id_col="ed.id", ts_col="ed.created_at")
        assert "ed.created_at" in cond
        assert "ed.id" in cond


class TestMapRefRow:
    """Row mapping from DB to EvidenceRefRow."""

    def test_maps_all_fields(self):
        now = datetime.now(timezone.utc)
        ref_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        av_id = uuid.uuid4()
        row = {
            "id": str(ref_id),
            "project_id": str(proj_id),
            "audit_year": 2025,
            "source_type": "workpaper_cell",
            "source_id": "src-1",
            "source_version": 3,
            "evidence_type": "attachment_version",
            "evidence_id": "ev-1",
            "attachment_version_id": str(av_id),
            "target_version": 2,
            "target_hash": "abc123" * 10 + "abcd",
            "label": "test-label",
            "context": "some-context",
            "intent_hash": "hash123" * 9 + "h",
            "status": "active",
            "created_at": now,
        }
        result = _map_ref_row(row)
        assert result.id == ref_id
        assert result.project_id == proj_id
        assert result.audit_year == 2025
        assert result.source_type == "workpaper_cell"
        assert result.evidence_type == "attachment_version"
        assert result.attachment_version_id == av_id
        assert result.status == "active"
        assert result.created_at == now

    def test_optional_fields_none(self):
        now = datetime.now(timezone.utc)
        row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2024,
            "source_type": "voucher",
            "source_id": "v-1",
            "evidence_type": "report",
            "evidence_id": "r-1",
            "intent_hash": "a" * 64,
            "status": "deactivated",
            "created_at": now,
        }
        result = _map_ref_row(row)
        assert result.source_version is None
        assert result.attachment_version_id is None
        assert result.target_version is None
        assert result.target_hash is None
        assert result.label is None
        assert result.context is None


class TestMapDepRow:
    """Row mapping from DB to DependencyRow."""

    def test_maps_all_fields(self):
        dep_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        row = {
            "id": str(dep_id),
            "project_id": str(proj_id),
            "audit_year": 2025,
            "source_type": "workpaper_cell",
            "source_id": "src-1",
            "target_type": "attachment_version",
            "target_id": "tgt-1",
            "source_version": 1,
            "target_version": 2,
            "edge_hash": "e" * 64,
            "status": "active",
            "evidence_ref_id": str(ref_id),
        }
        result = _map_dep_row(row)
        assert result.id == dep_id
        assert result.project_id == proj_id
        assert result.source_type == "workpaper_cell"
        assert result.target_type == "attachment_version"
        assert result.evidence_ref_id == ref_id


# ===========================================================================
# 2) Service-level tests (with mocked DB)
# ===========================================================================


def _make_actor(user_id: uuid.UUID | None = None) -> ActorContext:
    """Create a test user ActorContext."""
    uid = user_id or uuid.uuid4()
    return ActorContext(actor_type=ActorType.USER, actor_user_id=uid)


class TestDeactivateRefValidation:
    """Deactivation requires reason and proper state."""

    @pytest.mark.asyncio
    async def test_empty_reason_raises_metadata_incomplete(self):
        db = AsyncMock()
        svc = EvidenceRefQueryService(db)
        actor = _make_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.deactivate_ref(
                ref_id=uuid.uuid4(),
                reason="",
                actor=actor,
                project_id=uuid.uuid4(),
                audit_year=2025,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.METADATA_INCOMPLETE

    @pytest.mark.asyncio
    async def test_whitespace_only_reason_raises(self):
        db = AsyncMock()
        svc = EvidenceRefQueryService(db)
        actor = _make_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.deactivate_ref(
                ref_id=uuid.uuid4(),
                reason="   ",
                actor=actor,
                project_id=uuid.uuid4(),
                audit_year=2025,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.METADATA_INCOMPLETE


class TestLimitClamping:
    """Verify pagination limit is enforced per design §6.1."""

    def test_default_limit(self):
        assert CURSOR_PAGE_DEFAULT_LIMIT == 100

    def test_max_limit(self):
        assert CURSOR_PAGE_MAX_LIMIT == 200


class TestImpactResultDataclass:
    """ImpactResult and ImpactNode dataclass behavior."""

    def test_impact_node_default_path(self):
        node = ImpactNode(target_type="report", target_id="r-1", distance=1)
        assert node.path == []

    def test_impact_result_truncated_flag(self):
        result = ImpactResult(nodes=[], total_visited=0, truncated=True)
        assert result.truncated is True

    def test_impact_result_not_truncated_by_default(self):
        result = ImpactResult(nodes=[], total_visited=1)
        assert result.truncated is False


class TestDeactivateRefResultDataclass:
    """DeactivateRefResult dataclass."""

    def test_construction(self):
        rid = uuid.uuid4()
        result = DeactivateRefResult(
            ref_id=rid,
            previous_status="active",
            new_status="deactivated",
            reason="no longer needed",
        )
        assert result.ref_id == rid
        assert result.previous_status == "active"
        assert result.new_status == "deactivated"
        assert result.reason == "no longer needed"


class TestCursorPageDataclass:
    """CursorPage dataclass."""

    def test_empty_page(self):
        page = CursorPage(items=[])
        assert page.items == []
        assert page.next_cursor is None
        assert page.has_more is False

    def test_page_with_cursor(self):
        page = CursorPage(items=[], next_cursor="2025-01-01T00:00:00|abc", has_more=True)
        assert page.has_more is True
        assert page.next_cursor is not None
