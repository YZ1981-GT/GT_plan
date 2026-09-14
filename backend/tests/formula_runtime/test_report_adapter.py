"""Tests for ReportMutationAdapter.

Covers:
- P3: prepare→apply Decimal round-trip (after apply, read == after_value as Decimal)
- P4: version conflict on restore returns conflict=True (409 semantic)
- Invalid locator rejection (missing report_type/row_code/period)
- Project isolation (different project_id sees no data)

Uses SQLite in-memory with compat patches.
PBT max_examples=5 (global Hypothesis fast profile).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import Column, Integer, Numeric, String, Text, Boolean, Uuid, text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.services.formula_runtime.adapters.report import (
    ReportMutationAdapter,
    VALID_PERIODS,
    VALID_REPORT_TYPES,
    _validate_locator,
)
from app.services.formula_runtime.contracts import (
    CanonicalFormulaTarget,
    FormulaMutation,
)

# ---------------------------------------------------------------------------
# SQLite compat patches (must be before model definition)
# ---------------------------------------------------------------------------

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[assignment]
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid  # type: ignore[assignment]
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Minimal in-memory FinancialReport model (mirrors production schema)
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class FinancialReportTest(_Base):
    """Minimal FinancialReport for SQLite testing.

    Uses SQLAlchemy Uuid type (works on SQLite via visit_UUID compat patch).
    """

    __tablename__ = "financial_report"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)
    row_code: Mapped[str] = mapped_column(String, nullable=False)
    row_name: Mapped[str | None] = mapped_column(String, nullable=True)
    current_period_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    prior_period_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    formula_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("0"), nullable=False)
    is_total_row: Mapped[bool] = mapped_column(Boolean, server_default=text("0"), nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, server_default=text("0"), nullable=False)
    indent_level: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _run(coro):
    """Run async coroutine synchronously for Hypothesis compatibility."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_target(
    project_id: uuid.UUID | None = None,
    report_type: str = "BS",
    row_code: str = "BS-01",
    period: str = "current",
) -> CanonicalFormulaTarget:
    """Create a canonical target for the report domain."""
    return CanonicalFormulaTarget(
        domain="report",
        project_id=project_id or uuid.uuid4(),
        year=2025,
        addr_id=f"report/{report_type}/{row_code}/{period}",
        locator={"report_type": report_type, "row_code": row_code, "period": period},
    )


async def _setup_session():
    """Create a fresh in-memory SQLite engine+session with schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    # Monkey-patch report_models.FinancialReport to use our test model
    # by ensuring the adapter's import resolves to our test table
    import app.models.report_models as rm
    _original_model = rm.FinancialReport

    # We need to patch the model the adapter imports
    rm.FinancialReport = FinancialReportTest  # type: ignore[assignment,misc]

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = async_session()
    return engine, session, _original_model, rm


async def _teardown(engine, rm, original_model):
    """Restore original model and dispose engine."""
    rm.FinancialReport = original_model
    await engine.dispose()


async def _seed_report_row(
    session: AsyncSession,
    project_id: uuid.UUID,
    year: int = 2025,
    report_type: str = "BS",
    row_code: str = "BS-01",
    current_amount: Decimal | None = Decimal("1000.50"),
    prior_amount: Decimal | None = Decimal("800.25"),
) -> FinancialReportTest:
    """Insert a test financial_report row."""
    now = datetime.now(timezone.utc)
    row = FinancialReportTest(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        report_type=report_type,
        row_code=row_code,
        row_name=f"Test {row_code}",
        current_period_amount=current_amount,
        prior_period_amount=prior_amount,
        is_deleted=False,
        updated_at=now,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestLocatorValidation:
    """Test invalid locator rejection."""

    def test_missing_report_type(self):
        with pytest.raises(ValueError, match="missing keys"):
            _validate_locator({"row_code": "BS-01", "period": "current"})

    def test_missing_row_code(self):
        with pytest.raises(ValueError, match="missing keys"):
            _validate_locator({"report_type": "BS", "period": "current"})

    def test_missing_period(self):
        with pytest.raises(ValueError, match="missing keys"):
            _validate_locator({"report_type": "BS", "row_code": "BS-01"})

    def test_invalid_report_type(self):
        with pytest.raises(ValueError, match="Invalid report_type"):
            _validate_locator({"report_type": "INVALID", "row_code": "X-1", "period": "current"})

    def test_invalid_period(self):
        with pytest.raises(ValueError, match="Invalid period"):
            _validate_locator({"report_type": "BS", "row_code": "BS-01", "period": "future"})

    def test_empty_row_code(self):
        with pytest.raises(ValueError, match="row_code must not be empty"):
            _validate_locator({"report_type": "BS", "row_code": "  ", "period": "current"})

    def test_valid_locator_passes(self):
        # Should not raise
        _validate_locator({"report_type": "IS", "row_code": "IS-03", "period": "prior"})


class TestPrepareApplyDecimalRoundTrip:
    """P3: after apply, read value == after_value as Decimal."""

    def test_decimal_roundtrip_current(self):
        """prepare→apply round-trip for current_period_amount."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid = uuid.uuid4()
                await _seed_report_row(session, pid, current_amount=Decimal("12345.67"))

                adapter = ReportMutationAdapter(session)
                target = _make_target(project_id=pid, period="current")

                # prepare
                mutations = await adapter.prepare_many(
                    [target], {target.addr_id: "99999.99"}
                )
                assert len(mutations) == 1
                assert mutations[0].before_value == "12345.67"
                assert mutations[0].after_value == "99999.99"

                # apply
                applied = await adapter.apply_many(mutations)
                assert len(applied) == 1

                # verify by reading again
                mutations2 = await adapter.prepare_many(
                    [target], {target.addr_id: "0"}
                )
                assert mutations2[0].before_value == "99999.99"
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())

    def test_decimal_roundtrip_prior(self):
        """prepare→apply round-trip for prior_period_amount."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid = uuid.uuid4()
                await _seed_report_row(session, pid, prior_amount=Decimal("500.00"))

                adapter = ReportMutationAdapter(session)
                target = _make_target(project_id=pid, period="prior")

                mutations = await adapter.prepare_many(
                    [target], {target.addr_id: "777.77"}
                )
                assert mutations[0].before_value == "500.00"
                assert mutations[0].after_value == "777.77"

                applied = await adapter.apply_many(mutations)
                assert len(applied) == 1

                # Read back
                mutations2 = await adapter.prepare_many(
                    [target], {target.addr_id: "0"}
                )
                assert mutations2[0].before_value == "777.77"
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())


class TestVersionConflictRestore:
    """P4: version conflict on restore returns conflict=True (409 semantic)."""

    def test_restore_no_conflict(self):
        """When value hasn't changed, restore succeeds."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid = uuid.uuid4()
                await _seed_report_row(session, pid, current_amount=Decimal("100.00"))

                adapter = ReportMutationAdapter(session)
                target = _make_target(project_id=pid, period="current")

                # prepare + apply
                mutations = await adapter.prepare_many(
                    [target], {target.addr_id: "200.00"}
                )
                await adapter.apply_many(mutations)

                # restore (no one else changed it)
                restored = await adapter.restore_many(mutations)
                assert len(restored) == 1
                assert restored[0].conflict is False

                # Verify value is back to original
                mutations2 = await adapter.prepare_many(
                    [target], {target.addr_id: "0"}
                )
                assert mutations2[0].before_value == "100.00"
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())

    def test_restore_version_conflict(self):
        """When value was changed by another user, restore returns conflict=True."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid = uuid.uuid4()
                await _seed_report_row(session, pid, current_amount=Decimal("100.00"))

                adapter = ReportMutationAdapter(session)
                target = _make_target(project_id=pid, period="current")

                # prepare + apply (sets value to 200)
                mutations = await adapter.prepare_many(
                    [target], {target.addr_id: "200.00"}
                )
                await adapter.apply_many(mutations)

                # Simulate another user changing the value to 300
                from sqlalchemy import update as sa_update
                await session.execute(
                    sa_update(FinancialReportTest)
                    .where(
                        FinancialReportTest.project_id == pid,
                        FinancialReportTest.row_code == "BS-01",
                    )
                    .values(current_period_amount=Decimal("300.00"))
                )
                await session.flush()

                # Now try to restore — should conflict because current != after_value
                restored = await adapter.restore_many(mutations)
                assert len(restored) == 1
                assert restored[0].conflict is True
                assert "409" in (restored[0].conflict_detail or "")
                assert "Version conflict" in (restored[0].conflict_detail or "")
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())

    def test_restore_deleted_row_conflict(self):
        """When row was deleted, restore returns conflict=True."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid = uuid.uuid4()
                await _seed_report_row(session, pid, current_amount=Decimal("100.00"))

                adapter = ReportMutationAdapter(session)
                target = _make_target(project_id=pid, period="current")

                # prepare + apply
                mutations = await adapter.prepare_many(
                    [target], {target.addr_id: "200.00"}
                )
                await adapter.apply_many(mutations)

                # Soft-delete the row
                from sqlalchemy import update as sa_update
                await session.execute(
                    sa_update(FinancialReportTest)
                    .where(
                        FinancialReportTest.project_id == pid,
                        FinancialReportTest.row_code == "BS-01",
                    )
                    .values(is_deleted=True)
                )
                await session.flush()

                # Try to restore — should conflict
                restored = await adapter.restore_many(mutations)
                assert len(restored) == 1
                assert restored[0].conflict is True
                assert "no longer exists" in (restored[0].conflict_detail or "")
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())


class TestProjectIsolation:
    """P13: Different project_id sees no data / returns version '0'."""

    def test_prepare_different_project_gets_none(self):
        """prepare on a different project returns before_value=None."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid_a = uuid.uuid4()
                pid_b = uuid.uuid4()
                await _seed_report_row(session, pid_a, current_amount=Decimal("999.99"))

                adapter = ReportMutationAdapter(session)
                target_b = _make_target(project_id=pid_b, period="current")

                mutations = await adapter.prepare_many(
                    [target_b], {target_b.addr_id: "500.00"}
                )
                assert mutations[0].before_value is None
                assert mutations[0].expected_version == "0"
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())

    def test_read_versions_different_project(self):
        """read_versions for non-existent project returns '0'."""

        async def _run_test():
            engine, session, orig_model, rm = await _setup_session()
            try:
                pid_a = uuid.uuid4()
                pid_b = uuid.uuid4()
                await _seed_report_row(session, pid_a)

                adapter = ReportMutationAdapter(session)
                target_b = _make_target(project_id=pid_b, period="current")

                versions = await adapter.read_versions([target_b])
                assert versions[target_b.addr_id] == "0"
            finally:
                await session.close()
                await _teardown(engine, rm, orig_model)

        _run(_run_test())


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

st_report_type = st.sampled_from(sorted(VALID_REPORT_TYPES))
st_period = st.sampled_from(sorted(VALID_PERIODS))
st_row_code = st.from_regex(r"[A-Z]{2,4}-\d{2}", fullmatch=True)
st_decimal_str = st.decimals(
    min_value=Decimal("-9999999999.99"),
    max_value=Decimal("9999999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(str)


@settings(max_examples=5, deadline=None)
@given(
    report_type=st_report_type,
    row_code=st_row_code,
    period=st_period,
    amount=st_decimal_str,
)
def test_pbt_decimal_roundtrip(
    report_type: str, row_code: str, period: str, amount: str
):
    """**Validates: Requirements 3, P3**

    Property: For any valid locator and Decimal amount, prepare→apply
    preserves the exact Decimal value without float conversion loss.
    """

    async def _inner():
        engine, session, orig_model, rm = await _setup_session()
        try:
            pid = uuid.uuid4()
            # Seed with initial value
            await _seed_report_row(
                session,
                pid,
                report_type=report_type,
                row_code=row_code,
                current_amount=Decimal("0.00"),
                prior_amount=Decimal("0.00"),
            )

            adapter = ReportMutationAdapter(session)
            target = _make_target(
                project_id=pid,
                report_type=report_type,
                row_code=row_code,
                period=period,
            )

            # prepare + apply
            mutations = await adapter.prepare_many(
                [target], {target.addr_id: amount}
            )
            assert len(mutations) == 1
            await adapter.apply_many(mutations)

            # Read back and verify Decimal round-trip
            mutations2 = await adapter.prepare_many(
                [target], {target.addr_id: "0"}
            )
            read_back = mutations2[0].before_value
            expected = str(Decimal(amount).quantize(Decimal("0.01")))
            assert read_back == expected, (
                f"Decimal round-trip failed: wrote {amount}, "
                f"read back {read_back}, expected {expected}"
            )
        finally:
            await session.close()
            await _teardown(engine, rm, orig_model)

    _run(_inner())


@settings(max_examples=5, deadline=None)
@given(
    report_type=st_report_type,
    row_code=st_row_code,
    period=st_period,
    original=st_decimal_str,
    applied_val=st_decimal_str,
    intruder_val=st_decimal_str,
)
def test_pbt_version_conflict_on_restore(
    report_type: str,
    row_code: str,
    period: str,
    original: str,
    applied_val: str,
    intruder_val: str,
):
    """**Validates: Requirements 4, P4**

    Property: If after apply, a third party changes the value to something
    different from after_value, restore_many must return conflict=True.
    """
    # Only meaningful when intruder changes to something != applied_val
    if Decimal(intruder_val).quantize(Decimal("0.01")) == Decimal(applied_val).quantize(
        Decimal("0.01")
    ):
        return  # Skip degenerate case

    async def _inner():
        engine, session, orig_model, rm = await _setup_session()
        try:
            pid = uuid.uuid4()
            await _seed_report_row(
                session,
                pid,
                report_type=report_type,
                row_code=row_code,
                current_amount=Decimal(original).quantize(Decimal("0.01")),
                prior_amount=Decimal(original).quantize(Decimal("0.01")),
            )

            adapter = ReportMutationAdapter(session)
            target = _make_target(
                project_id=pid,
                report_type=report_type,
                row_code=row_code,
                period=period,
            )

            # prepare + apply
            mutations = await adapter.prepare_many(
                [target], {target.addr_id: applied_val}
            )
            await adapter.apply_many(mutations)

            # Simulate intruder changing the value
            from sqlalchemy import update as sa_update
            col = (
                "current_period_amount" if period == "current" else "prior_period_amount"
            )
            await session.execute(
                sa_update(FinancialReportTest)
                .where(
                    FinancialReportTest.project_id == pid,
                    FinancialReportTest.row_code == row_code,
                    FinancialReportTest.report_type == report_type,
                )
                .values(**{col: Decimal(intruder_val).quantize(Decimal("0.01"))})
            )
            await session.flush()

            # restore — should conflict
            restored = await adapter.restore_many(mutations)
            assert len(restored) == 1
            assert restored[0].conflict is True
            assert "409" in (restored[0].conflict_detail or "")
        finally:
            await session.close()
            await _teardown(engine, rm, orig_model)

    _run(_inner())
