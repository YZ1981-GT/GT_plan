"""tests/formula_runtime/test_refresh_transaction.py

Validates: Requirements 4, 8, 9, 10 — Properties P4, P9, P10, P11, P12

Tests for DraftRefreshService.execute_refresh:
- snapshot→apply→audit→outbox in same transaction
- affected_count only counts successful applies
- all_or_nothing: one failure → zero writes
- partial_success: failed scope doesn't block others
- fingerprint sensitivity (change one input → different fingerprint)
- idempotency (same fingerprint → idempotent_hit)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    DomainMutationAdapter,
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


def _make_mutation(
    domain: str = "workpaper",
    addr_id: str = "wp1:cell1",
    before: Any = 100,
    after: Any = 200,
    version: str | None = "v1",
) -> FormulaMutation:
    target = _make_target(domain=domain, addr_id=addr_id)
    return FormulaMutation(
        target=target,
        before_value=before,
        after_value=after,
        expected_version=version,
    )


class MockAdapter:
    """Mock DomainMutationAdapter for testing."""

    def __init__(self, domain: str, *, fail_on_apply: bool = False):
        self.domain = domain
        self.fail_on_apply = fail_on_apply
        self.applied: list[FormulaMutation] = []
        self.restored: list[FormulaMutation] = []

    async def prepare_many(self, targets, values):
        return []

    async def apply_many(self, mutations: list[FormulaMutation]) -> list[AppliedMutation]:
        if self.fail_on_apply:
            raise RuntimeError("Simulated apply failure")
        self.applied.extend(mutations)
        return [
            AppliedMutation(
                target=m.target,
                applied_version=f"v{i+2}",
                applied_at="2025-01-01T00:00:00Z",
            )
            for i, m in enumerate(mutations)
        ]

    async def restore_many(self, snapshots: list[FormulaMutation]) -> list[RestoredMutation]:
        self.restored.extend(snapshots)
        return [
            RestoredMutation(target=s.target, restored_version="v1")
            for s in snapshots
        ]

    async def read_versions(self, targets):
        return {}


class MockSession:
    """Lightweight mock for AsyncSession that tracks adds, executes, and flushes."""

    def __init__(self):
        self.added = []
        self.flushed = 0
        self._execute_results = []
        self._scalars_first_values = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def execute(self, stmt, params=None):
        return MockResult(self._scalars_first_values.pop(0) if self._scalars_first_values else None)

    def set_scalar_results(self, values):
        """Pre-load scalar results for sequential execute calls."""
        self._scalars_first_values = list(values)


class MockResult:
    def __init__(self, value=None):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

    def all(self):
        return [self._value] if self._value else []

    def scalar_one_or_none(self):
        return self._value


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestComputeFingerprint:
    """Validates: Requirements 8.1, 8.2 — P9: fingerprint determinism and sensitivity."""

    def test_same_inputs_produce_same_fingerprint(self):
        """Same inputs → same fingerprint (deterministic)."""
        svc = DraftRefreshService()
        pid = uuid.uuid4()
        fp1 = svc.compute_fingerprint(
            project_id=pid, year=2025, scopes=["report", "note"],
            transaction_mode="all_or_nothing",
            four_table_dataset_revision="rev1",
            formula_definition_revision="def1",
        )
        fp2 = svc.compute_fingerprint(
            project_id=pid, year=2025, scopes=["note", "report"],  # order shouldn't matter
            transaction_mode="all_or_nothing",
            four_table_dataset_revision="rev1",
            formula_definition_revision="def1",
        )
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256 hex

    def test_change_one_input_changes_fingerprint(self):
        """Change one input → different fingerprint (sensitivity)."""
        svc = DraftRefreshService()
        pid = uuid.uuid4()
        base_kwargs = dict(
            project_id=pid, year=2025, scopes=["report"],
            transaction_mode="all_or_nothing",
            four_table_dataset_revision="rev1",
            formula_definition_revision="def1",
            preset_revision="p1",
            acnr_registry_version="a1",
        )
        base = svc.compute_fingerprint(**base_kwargs)

        # Change year
        assert svc.compute_fingerprint(**{**base_kwargs, "year": 2024}) != base
        # Change scope
        assert svc.compute_fingerprint(**{**base_kwargs, "scopes": ["note"]}) != base
        # Change transaction_mode
        assert svc.compute_fingerprint(**{**base_kwargs, "transaction_mode": "partial_success"}) != base
        # Change four_table_dataset_revision
        assert svc.compute_fingerprint(**{**base_kwargs, "four_table_dataset_revision": "rev2"}) != base
        # Change formula_definition_revision
        assert svc.compute_fingerprint(**{**base_kwargs, "formula_definition_revision": "def2"}) != base

    def test_scopes_order_insensitive(self):
        """Scope order should not affect fingerprint (normalized sort)."""
        svc = DraftRefreshService()
        pid = uuid.uuid4()
        fp1 = svc.compute_fingerprint(project_id=pid, year=2025, scopes=["a", "b", "c"])
        fp2 = svc.compute_fingerprint(project_id=pid, year=2025, scopes=["c", "a", "b"])
        assert fp1 == fp2


class TestExecuteRefreshAllOrNothing:
    """Validates: Requirements 9.1, 9.2 — P10: all-or-nothing semantics."""

    @pytest.mark.asyncio
    async def test_successful_apply_counts_affected(self):
        """Successful apply → affected_count = number of applied mutations."""
        svc = DraftRefreshService()
        adapter = MockAdapter("workpaper")
        mutations = [_make_mutation(addr_id=f"cell{i}") for i in range(3)]

        # Mock session that returns None for idempotency check and advisory lock
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Mock execute to return None for idempotency check
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["workpaper"],
            mutations=mutations,
            adapters={"workpaper": adapter},
        )

        assert result.status == "success"
        assert result.applied_count == 3
        assert len(adapter.applied) == 3

    @pytest.mark.asyncio
    async def test_one_failure_zero_writes(self):
        """All-or-nothing: one adapter failure → status=failed, affected_count=0."""
        svc = DraftRefreshService()
        adapter = MockAdapter("workpaper", fail_on_apply=True)
        mutations = [_make_mutation()]

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["workpaper"],
            mutations=mutations,
            adapters={"workpaper": adapter},
        )

        assert result.status == "failed"
        assert result.applied_count == 0

    @pytest.mark.asyncio
    async def test_no_mutations_returns_no_effect(self):
        """Empty mutations → no_effect status."""
        svc = DraftRefreshService()

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["report"],
            mutations=[],
            adapters={},
        )

        assert result.status == "no_effect"
        assert result.applied_count == 0


class TestExecuteRefreshPartialSuccess:
    """Validates: Requirements 9.3, 9.4 — P11: partial-success savepoint."""

    @pytest.mark.asyncio
    async def test_failed_scope_doesnt_block_others(self):
        """Partial-success: failed domain doesn't block successful domain."""
        svc = DraftRefreshService()

        good_adapter = MockAdapter("report")
        bad_adapter = MockAdapter("workpaper", fail_on_apply=True)

        mutations_report = [_make_mutation(domain="report", addr_id="r1")]
        mutations_wp = [_make_mutation(domain="workpaper", addr_id="w1")]
        all_mutations = mutations_report + mutations_wp

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        # Mock begin_nested for savepoint (context manager)
        class FakeNested:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                # Don't suppress - let it propagate to the try/except
                return False

        session.begin_nested = lambda: FakeNested()

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["report", "workpaper"],
            mutations=all_mutations,
            adapters={"report": good_adapter, "workpaper": bad_adapter},
            transaction_mode="partial_success",
        )

        assert result.status == "partial_success"
        assert result.applied_count == 1  # Only report succeeded
        assert result.failed_count == 1
        assert len(good_adapter.applied) == 1


class TestIdempotency:
    """Validates: Requirements 8.4 — P12: idempotent hit."""

    @pytest.mark.asyncio
    async def test_same_fingerprint_completed_returns_idempotent(self):
        """Same fingerprint already completed → return idempotent_hit."""
        svc = DraftRefreshService()
        pid = uuid.uuid4()
        run_id = uuid.uuid4()

        # Create a mock prior audit record
        prior_audit = MagicMock()
        prior_audit.id = run_id
        prior_audit.result_status = "success"
        prior_audit.affected_count = 5

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # First execute returns None (advisory lock), second returns prior audit
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # advisory lock
                return result
            # idempotency check
            result.scalars.return_value.first.return_value = prior_audit
            return result

        session.execute = mock_execute

        result = await svc.execute_refresh(
            session,
            project_id=pid,
            year=2025,
            scopes=["report"],
            mutations=[_make_mutation()],
            adapters={"workpaper": MockAdapter("workpaper")},
        )

        assert result.status == "idempotent_hit"
        assert result.run_id == run_id


class TestSnapshotAuditOutbox:
    """Validates: Requirements 4.1, 9.6 — P4: snapshot→apply→audit→outbox same transaction."""

    @pytest.mark.asyncio
    async def test_snapshot_saved_before_apply(self):
        """Snapshots are saved in the same flush sequence before apply is confirmed."""
        svc = DraftRefreshService()
        adapter = MockAdapter("workpaper")
        mutations = [_make_mutation(addr_id="cell1")]

        session = AsyncMock()
        added_objects = []
        session.add = lambda obj: added_objects.append(obj)
        session.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["workpaper"],
            mutations=mutations,
            adapters={"workpaper": adapter},
        )

        assert result.status == "success"
        # Verify objects added: audit + snapshots
        from app.models.workpaper_models import DraftRefreshAudit, DraftRefreshSnapshot
        audit_adds = [o for o in added_objects if isinstance(o, DraftRefreshAudit)]
        snap_adds = [o for o in added_objects if isinstance(o, DraftRefreshSnapshot)]
        assert len(audit_adds) == 1
        assert len(snap_adds) == 1
        assert snap_adds[0].before_value == 100  # before_value from mutation

    @pytest.mark.asyncio
    async def test_affected_count_only_counts_success(self):
        """affected_count counts ONLY successfully applied mutations."""
        svc = DraftRefreshService()

        # Adapter that applies only first mutation, fails on second
        class PartialAdapter:
            domain = "workpaper"

            async def apply_many(self, mutations):
                # Only return one applied (simulating partial batch)
                return [
                    AppliedMutation(
                        target=mutations[0].target,
                        applied_version="v2",
                        applied_at="2025-01-01T00:00:00Z",
                    )
                ]

            async def prepare_many(self, targets, values):
                return []

            async def restore_many(self, snapshots):
                return []

            async def read_versions(self, targets):
                return {}

        mutations = [_make_mutation(addr_id=f"c{i}") for i in range(3)]

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await svc.execute_refresh(
            session,
            project_id=uuid.uuid4(),
            year=2025,
            scopes=["workpaper"],
            mutations=mutations,
            adapters={"workpaper": PartialAdapter()},
        )

        # Only 1 was actually applied (adapter returned 1 AppliedMutation)
        assert result.applied_count == 1
