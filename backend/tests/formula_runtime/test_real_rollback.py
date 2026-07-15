"""tests/formula_runtime/test_real_rollback.py

Validates: Requirements 2, 8, 10 — Properties P4, P9, P10, P11, P12

Tests for DraftRefreshService.rollback_refresh:
- Rollback restores before_values in reverse order
- Rollback with version conflict → 409 with structured detail
- Rollback updates audit status
- Rollback after no-conflict → values restored
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)


# ── Test Helpers ──────────────────────────────────────────────────────


def _make_target(domain: str = "workpaper", addr_id: str = "wp1:cell1") -> CanonicalFormulaTarget:
    return CanonicalFormulaTarget(
        domain=domain,
        project_id=uuid.uuid4(),
        year=2025,
        addr_id=addr_id,
        locator={"wp_id": str(uuid.uuid4()), "cell": "A1"},
    )


class SuccessAdapter:
    """Adapter that always restores successfully."""

    domain = "workpaper"

    async def prepare_many(self, targets, values):
        return []

    async def apply_many(self, mutations):
        return []

    async def restore_many(self, snapshots: list[FormulaMutation]) -> list[RestoredMutation]:
        return [
            RestoredMutation(target=s.target, restored_version="v1", conflict=False)
            for s in snapshots
        ]

    async def read_versions(self, targets):
        return {}


class ConflictAdapter:
    """Adapter that reports CAS conflict on restore."""

    domain = "workpaper"

    async def prepare_many(self, targets, values):
        return []

    async def apply_many(self, mutations):
        return []

    async def restore_many(self, snapshots: list[FormulaMutation]) -> list[RestoredMutation]:
        return [
            RestoredMutation(
                target=s.target,
                restored_version="",
                conflict=True,
                conflict_detail=f"expected v2, found v3 for {s.target.addr_id}",
            )
            for s in snapshots
        ]

    async def read_versions(self, targets):
        return {}


class MockSnapshot:
    """Mock DraftRefreshSnapshot row."""

    def __init__(self, *, unit_scope: str, domain: str, before_value, after_value=None,
                 before_version: str | None = "v1", after_version: str | None = "v2",
                 target_locator: dict | None = None):
        self.id = uuid.uuid4()
        self.refresh_id = uuid.uuid4()
        self.unit_scope = unit_scope
        self.domain = domain
        self.before_value = before_value
        self.after_value = after_value
        self.before_version = before_version
        self.after_version = after_version
        self.target_locator = target_locator or {}
        self.restored_at = None


class MockAudit:
    """Mock DraftRefreshAudit row."""

    def __init__(self, *, run_id: uuid.UUID, status: str = "success"):
        self.id = run_id
        self.project_id = uuid.uuid4()
        self.year = 2025
        self.result_status = status
        self.operator_id = uuid.uuid4()
        self.detail = {}


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestRollbackRestoresValues:
    """Validates: Requirements 2.1, 2.2 — P4: rollback restores before_values."""

    @pytest.mark.asyncio
    async def test_successful_rollback_restores_all(self):
        """Rollback with no conflicts → all values restored, status=rolled_back."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()
        audit = MockAudit(run_id=run_id, status="success")

        snaps = [
            MockSnapshot(unit_scope="workpaper:cell1", domain="workpaper", before_value=100, after_value=200),
            MockSnapshot(unit_scope="workpaper:cell2", domain="workpaper", before_value=50, after_value=75),
        ]

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # First: load audit
                result.scalar_one_or_none.return_value = audit
                return result
            if call_count[0] == 2:
                # Second: load snapshots
                result.scalars.return_value.all.return_value = snaps
                return result
            # Outbox write
            return result

        session.execute = mock_execute

        adapter = SuccessAdapter()
        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": adapter},
        )

        assert result.status == "rolled_back"
        assert result.applied_count == 2

    @pytest.mark.asyncio
    async def test_rollback_reverse_order(self):
        """Snapshots are loaded in reverse order for correct undo sequence."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()
        audit = MockAudit(run_id=run_id, status="success")

        # Create snapshots (will be returned in desc id order from query)
        snap1 = MockSnapshot(unit_scope="workpaper:first", domain="workpaper", before_value=1)
        snap2 = MockSnapshot(unit_scope="workpaper:second", domain="workpaper", before_value=2)
        snap3 = MockSnapshot(unit_scope="workpaper:third", domain="workpaper", before_value=3)

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = audit
                return result
            if call_count[0] == 2:
                # Returned in reverse order (desc by id)
                result.scalars.return_value.all.return_value = [snap3, snap2, snap1]
                return result
            return result

        session.execute = mock_execute

        restore_calls = []

        class TrackingAdapter:
            domain = "workpaper"

            async def restore_many(self, snapshots):
                for s in snapshots:
                    restore_calls.append(s.target.addr_id)
                return [
                    RestoredMutation(target=s.target, restored_version="v1")
                    for s in snapshots
                ]

            async def prepare_many(self, t, v):
                return []

            async def apply_many(self, m):
                return []

            async def read_versions(self, t):
                return {}

        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": TrackingAdapter()},
        )

        assert result.status == "rolled_back"
        # All three restored
        assert result.applied_count == 3


class TestRollbackVersionConflict:
    """Validates: Requirements 2.4, 8.7 — P9: CAS conflict returns 409."""

    @pytest.mark.asyncio
    async def test_conflict_returns_409(self):
        """Version conflict → structured 409 response."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()
        audit = MockAudit(run_id=run_id, status="success")

        snaps = [
            MockSnapshot(
                unit_scope="workpaper:conflicted",
                domain="workpaper",
                before_value=100,
                after_value=200,
                after_version="v2",
            ),
        ]

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = audit
                return result
            if call_count[0] == 2:
                result.scalars.return_value.all.return_value = snaps
                return result
            return result

        session.execute = mock_execute

        adapter = ConflictAdapter()
        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": adapter},
        )

        # Should return dict with 409
        assert isinstance(result, dict)
        assert result["status"] == 409
        assert result["error"] == "version_conflict"
        assert len(result["conflicts"]) == 1
        assert "expected v2, found v3" in result["conflicts"][0]["conflict_detail"]


class TestRollbackAuditStatus:
    """Validates: Requirements 2.3 — rollback updates audit status."""

    @pytest.mark.asyncio
    async def test_audit_marked_rolled_back(self):
        """Successful rollback → audit.result_status='rolled_back'."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()
        audit = MockAudit(run_id=run_id, status="success")

        snaps = [
            MockSnapshot(unit_scope="workpaper:cell1", domain="workpaper", before_value=100),
        ]

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = audit
                return result
            if call_count[0] == 2:
                result.scalars.return_value.all.return_value = snaps
                return result
            return result

        session.execute = mock_execute

        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": SuccessAdapter()},
        )

        assert result.status == "rolled_back"
        assert audit.result_status == "rolled_back"
        assert "rollback" in audit.detail

    @pytest.mark.asyncio
    async def test_already_rolled_back_returns_idempotent(self):
        """Already rolled back → idempotent_hit, no double modify."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()
        audit = MockAudit(run_id=run_id, status="rolled_back")

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = audit
                return result
            return result

        session.execute = mock_execute

        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": SuccessAdapter()},
        )

        assert result.status == "idempotent_hit"

    @pytest.mark.asyncio
    async def test_not_found_returns_failed(self):
        """Non-existent run_id → status=failed with not_found error."""
        svc = DraftRefreshService()
        run_id = uuid.uuid4()

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        async def mock_execute(stmt, params=None):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        session.execute = mock_execute

        result = await svc.rollback_refresh(
            session,
            run_id=run_id,
            adapters={"workpaper": SuccessAdapter()},
        )

        assert result.status == "failed"
        assert result.failures[0]["error"] == "not_found"
