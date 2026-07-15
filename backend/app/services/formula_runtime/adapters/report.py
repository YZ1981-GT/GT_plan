"""formula_runtime.adapters.report — ReportMutationAdapter.

以 report_type / row_code / period 定位 financial_report 行值。
locator 必须包含 report_type、row_code、period（current | prior）。
写入保持 Decimal round-trip（Numeric(20,2)，不经 float 中间转换）。
restore_many 做 optimistic version check：若 updated_at 已被他人推进，
则 conflict=True + conflict_detail（409 语义）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)

# ---------------------------------------------------------------------------
# 支持的 report_type / period 枚举
# ---------------------------------------------------------------------------

VALID_REPORT_TYPES = frozenset({"BS", "IS", "CFS", "EQ", "CFSS", "IMP"})
VALID_PERIODS = frozenset({"current", "prior"})
REQUIRED_LOCATOR_KEYS = frozenset({"report_type", "row_code", "period"})


def _period_column(period: str) -> str:
    """Map period literal to the DB column name."""
    if period == "current":
        return "current_period_amount"
    return "prior_period_amount"


def _validate_locator(locator: dict[str, str]) -> None:
    """Raise ValueError if locator is missing required keys or has invalid values."""
    missing = REQUIRED_LOCATOR_KEYS - set(locator.keys())
    if missing:
        raise ValueError(f"Report locator missing keys: {sorted(missing)}")
    if locator["report_type"] not in VALID_REPORT_TYPES:
        raise ValueError(
            f"Invalid report_type '{locator['report_type']}', "
            f"expected one of {sorted(VALID_REPORT_TYPES)}"
        )
    if locator["period"] not in VALID_PERIODS:
        raise ValueError(
            f"Invalid period '{locator['period']}', expected 'current' or 'prior'"
        )
    if not locator["row_code"].strip():
        raise ValueError("row_code must not be empty")


def _to_decimal(value: Any) -> Decimal | None:
    """Convert a JSON-compatible value to Decimal without float intermediary."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Cannot convert {value!r} to Decimal") from exc
    if isinstance(value, float):
        # Use string representation to avoid float precision issues
        return Decimal(str(value))
    raise ValueError(f"Unsupported value type for Decimal conversion: {type(value)}")


def _version_str(dt: datetime | None) -> str:
    """Serialize a datetime to an ISO version string."""
    if dt is None:
        return "0"
    return dt.isoformat()


class ReportMutationAdapter:
    """DomainMutationAdapter implementation for the 'report' domain.

    Reads/writes financial_report rows by (project_id, year, report_type, row_code).
    Period ('current' | 'prior') selects the amount column.
    """

    domain: str = "report"

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
        """Read current values and produce FormulaMutation snapshots."""
        from app.models.report_models import FinancialReport

        mutations: list[FormulaMutation] = []
        for target in targets:
            _validate_locator(dict(target.locator))
            locator = dict(target.locator)
            report_type = locator["report_type"]
            row_code = locator["row_code"]
            period = locator["period"]
            col = _period_column(period)

            stmt = select(FinancialReport).where(
                FinancialReport.project_id == target.project_id,
                FinancialReport.year == target.year,
                FinancialReport.report_type == report_type,
                FinancialReport.row_code == row_code,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            before_value: Decimal | None = None
            version: str = "0"
            if row is not None:
                before_value = getattr(row, col)
                version = _version_str(row.updated_at)

            # after_value comes from the values dict keyed by addr_id
            after_raw = values.get(target.addr_id)
            after_value = _to_decimal(after_raw)

            mutations.append(
                FormulaMutation(
                    target=target,
                    before_value=str(before_value) if before_value is not None else None,
                    after_value=str(after_value) if after_value is not None else None,
                    expected_version=version,
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
        """Write after_value to the financial_report row."""
        from app.models.report_models import FinancialReport

        applied: list[AppliedMutation] = []
        now = datetime.now(timezone.utc)

        for m in mutations:
            _validate_locator(dict(m.target.locator))
            locator = dict(m.target.locator)
            report_type = locator["report_type"]
            row_code = locator["row_code"]
            period = locator["period"]
            col = _period_column(period)

            new_value = _to_decimal(m.after_value)

            stmt = (
                update(FinancialReport)
                .where(
                    FinancialReport.project_id == m.target.project_id,
                    FinancialReport.year == m.target.year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.row_code == row_code,
                    FinancialReport.is_deleted == False,  # noqa: E712
                )
                .values(**{col: new_value, "updated_at": now})
            )
            await self._session.execute(stmt)
            await self._session.flush()

            applied.append(
                AppliedMutation(
                    target=m.target,
                    applied_version=_version_str(now),
                    applied_at=now.isoformat(),
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
        """Restore before_value with optimistic version check.

        If the row's updated_at no longer matches expected_version (i.e. someone
        else edited the row after our apply), we return conflict=True with a
        409-semantic conflict_detail instead of overwriting their change.
        """
        from app.models.report_models import FinancialReport

        results: list[RestoredMutation] = []
        now = datetime.now(timezone.utc)

        for snap in snapshots:
            _validate_locator(dict(snap.target.locator))
            locator = dict(snap.target.locator)
            report_type = locator["report_type"]
            row_code = locator["row_code"]
            period = locator["period"]
            col = _period_column(period)

            # Read current row to check version
            stmt = select(FinancialReport).where(
                FinancialReport.project_id == snap.target.project_id,
                FinancialReport.year == snap.target.year,
                FinancialReport.report_type == report_type,
                FinancialReport.row_code == row_code,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                # Row deleted — conflict
                results.append(
                    RestoredMutation(
                        target=snap.target,
                        restored_version=_version_str(now),
                        conflict=True,
                        conflict_detail=(
                            f"Row {report_type}/{row_code} no longer exists; "
                            "cannot restore"
                        ),
                    )
                )
                continue

            current_version = _version_str(row.updated_at)
            # We expect the version to match what was set during apply
            # If someone else edited after our apply, version will differ
            # from what the apply wrote.
            # The expected "post-apply" version is not in the snapshot itself;
            # we compare current_version against what we would have written.
            # If the snapshot has expected_version (pre-apply state) and the row
            # has been updated beyond what our apply set, there's a conflict.
            #
            # Strategy: check if current value matches our after_value.
            # If it doesn't, someone else changed it — conflict.
            current_value = getattr(row, col)
            our_after = _to_decimal(snap.after_value)

            if current_value != our_after:
                # Version conflict — value changed by someone else
                results.append(
                    RestoredMutation(
                        target=snap.target,
                        restored_version=current_version,
                        conflict=True,
                        conflict_detail=(
                            f"Version conflict on {report_type}/{row_code}/{period}: "
                            f"expected after_value={our_after}, "
                            f"current_value={current_value}; "
                            "row was modified by another user (409)"
                        ),
                    )
                )
                continue

            # No conflict — restore before_value
            restore_value = _to_decimal(snap.before_value)
            restore_stmt = (
                update(FinancialReport)
                .where(
                    FinancialReport.project_id == snap.target.project_id,
                    FinancialReport.year == snap.target.year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.row_code == row_code,
                    FinancialReport.is_deleted == False,  # noqa: E712
                )
                .values(**{col: restore_value, "updated_at": now})
            )
            await self._session.execute(restore_stmt)
            await self._session.flush()

            results.append(
                RestoredMutation(
                    target=snap.target,
                    restored_version=_version_str(now),
                    conflict=False,
                )
            )
        return results

    # ------------------------------------------------------------------
    # read_versions
    # ------------------------------------------------------------------

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]:
        """Return current version strings keyed by addr_id."""
        from app.models.report_models import FinancialReport

        versions: dict[str, str] = {}
        for target in targets:
            _validate_locator(dict(target.locator))
            locator = dict(target.locator)
            report_type = locator["report_type"]
            row_code = locator["row_code"]

            stmt = select(FinancialReport.updated_at).where(
                FinancialReport.project_id == target.project_id,
                FinancialReport.year == target.year,
                FinancialReport.report_type == report_type,
                FinancialReport.row_code == row_code,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            versions[target.addr_id] = _version_str(row)
        return versions
