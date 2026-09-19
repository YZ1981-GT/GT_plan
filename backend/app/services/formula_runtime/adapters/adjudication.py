"""formula_runtime.adapters.adjudication — AdjudicationMutationAdapter.

只向 trial_balance.audited_amount 写入审定结果。
locator 必须包含 standard_account_code（纯数字科目码如 "1001"、"2211.01"），
拒绝 B5 引用和单元坐标（如 "A1"、"BS!C5"）。

不动 unadjusted_amount。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)

# ─── Locator 校验 ──────────────────────────────────────────────────────────────

# 合法科目码: 纯数字(可含点号分级), 如 "1001", "2211", "2211.01", "6601.01.02"
_RE_VALID_ACCOUNT_CODE = re.compile(r"^\d+(\.\d+)*$")

# B5 引用: "B5" / "B5:xxx" / "b5:anything"
_RE_B5_REF = re.compile(r"(?i)^B\d+[:\-]")

# 单元坐标: "A1", "BS!C5", "AA123", etc. (字母+数字 或 sheet!cell)
_RE_CELL_COORD = re.compile(r"(?i)^[A-Z]{1,3}\d+$|^[A-Z0-9]+![A-Z]{1,3}\d+$")


class InvalidLocatorError(ValueError):
    """Raised when locator is not a valid standard_account_code."""

    pass


def validate_account_code(code: str) -> str:
    """Validate that code is a legitimate standard_account_code.

    Raises InvalidLocatorError if code looks like a B5 reference,
    cell coordinate, or otherwise isn't a valid numeric account code.
    """
    if not code:
        raise InvalidLocatorError("standard_account_code cannot be empty")

    if _RE_B5_REF.match(code):
        raise InvalidLocatorError(
            f"B5-style reference rejected as account code: {code!r}"
        )

    if _RE_CELL_COORD.match(code):
        raise InvalidLocatorError(
            f"Cell coordinate rejected as account code: {code!r}"
        )

    if not _RE_VALID_ACCOUNT_CODE.match(code):
        raise InvalidLocatorError(
            f"Invalid standard_account_code format: {code!r}"
        )

    return code


def _version_hash(amount: Decimal | None, updated_at: datetime | None) -> str:
    """Compute a stable version hash from audited_amount + updated_at."""
    raw = f"{amount}|{updated_at.isoformat() if updated_at else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ─── Adapter ───────────────────────────────────────────────────────────────────


class AdjudicationMutationAdapter:
    """DomainMutationAdapter for trial_balance.audited_amount.

    Protocol compliance:
        domain: str
        prepare_many(targets, values) -> list[FormulaMutation]
        apply_many(mutations) -> list[AppliedMutation]
        restore_many(snapshots) -> list[RestoredMutation]
        read_versions(targets) -> dict[str, str]
    """

    domain: str = "adjudication"

    def __init__(self, session: Any) -> None:
        """Initialize with an async DB session."""
        self._session = session

    # ─── helpers ───────────────────────────────────────────────────────────

    def _extract_account_code(self, target: CanonicalFormulaTarget) -> str:
        """Extract and validate standard_account_code from target locator."""
        code = target.locator.get("standard_account_code")
        if code is None:
            raise InvalidLocatorError(
                "locator must contain 'standard_account_code'"
            )
        return validate_account_code(code)

    async def _fetch_row(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
    ) -> Any | None:
        """Fetch a single trial_balance row by natural key."""
        from sqlalchemy import select, and_
        from app.models.audit_platform_models import TrialBalance

        stmt = select(TrialBalance).where(
            and_(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ─── Protocol methods ──────────────────────────────────────────────────

    async def prepare_many(
        self,
        targets: list[CanonicalFormulaTarget],
        values: dict[str, Any],
    ) -> list[FormulaMutation]:
        """Read current audited_amount and capture before_value + version."""
        mutations: list[FormulaMutation] = []

        for target in targets:
            account_code = self._extract_account_code(target)

            if target.domain != "adjudication":
                raise InvalidLocatorError(
                    f"AdjudicationAdapter only handles 'adjudication' domain, got {target.domain!r}"
                )

            row = await self._fetch_row(target.project_id, target.year, account_code)

            before_value: Decimal | None = None
            expected_version: str | None = None

            if row is not None:
                before_value = row.audited_amount
                expected_version = _version_hash(row.audited_amount, row.updated_at)

            # after_value comes from the computed values dict, keyed by addr_id
            after_value = values.get(target.addr_id)

            mutations.append(
                FormulaMutation(
                    target=target,
                    before_value=before_value,
                    after_value=after_value,
                    expected_version=expected_version,
                )
            )

        return mutations

    async def apply_many(
        self,
        mutations: list[FormulaMutation],
    ) -> list[AppliedMutation]:
        """UPDATE trial_balance SET audited_amount; verify version via CAS."""
        from sqlalchemy import update, and_
        from app.models.audit_platform_models import TrialBalance

        applied: list[AppliedMutation] = []

        for mutation in mutations:
            target = mutation.target
            account_code = self._extract_account_code(target)

            # Re-read for CAS
            row = await self._fetch_row(target.project_id, target.year, account_code)

            if row is None:
                raise ValueError(
                    f"trial_balance row not found for project={target.project_id}, "
                    f"year={target.year}, account={account_code}"
                )

            # CAS check
            current_version = _version_hash(row.audited_amount, row.updated_at)
            if mutation.expected_version is not None and current_version != mutation.expected_version:
                raise ValueError(
                    f"Version conflict for account {account_code}: "
                    f"expected={mutation.expected_version}, current={current_version}"
                )

            # Only write audited_amount — never touch unadjusted_amount
            now = datetime.now(timezone.utc)
            stmt = (
                update(TrialBalance)
                .where(
                    and_(
                        TrialBalance.id == row.id,
                        TrialBalance.is_deleted == False,  # noqa: E712
                    )
                )
                .values(
                    audited_amount=mutation.after_value,
                    updated_at=now,
                )
            )
            await self._session.execute(stmt)
            await self._session.flush()

            new_version = _version_hash(mutation.after_value, now)

            applied.append(
                AppliedMutation(
                    target=target,
                    applied_version=new_version,
                    applied_at=now.isoformat(),
                )
            )

        return applied

    async def restore_many(
        self,
        snapshots: list[FormulaMutation],
    ) -> list[RestoredMutation]:
        """Restore before_value (audited_amount) with optimistic version check."""
        from sqlalchemy import update, and_
        from app.models.audit_platform_models import TrialBalance

        restored: list[RestoredMutation] = []

        for snapshot in snapshots:
            target = snapshot.target
            account_code = self._extract_account_code(target)

            row = await self._fetch_row(target.project_id, target.year, account_code)

            if row is None:
                restored.append(
                    RestoredMutation(
                        target=target,
                        restored_version="",
                        conflict=True,
                        conflict_detail=f"Row not found for account {account_code}",
                    )
                )
                continue

            # CAS: the current value should match after_value from the snapshot
            # (meaning no one else modified it since we applied)
            current_version = _version_hash(row.audited_amount, row.updated_at)

            # We can't easily verify exact version match since updated_at changed,
            # but we can check if the current audited_amount matches what we wrote
            if row.audited_amount != snapshot.after_value:
                restored.append(
                    RestoredMutation(
                        target=target,
                        restored_version=current_version,
                        conflict=True,
                        conflict_detail=(
                            f"audited_amount has been modified since apply: "
                            f"current={row.audited_amount}, expected={snapshot.after_value}"
                        ),
                    )
                )
                continue

            # Restore before_value
            now = datetime.now(timezone.utc)
            stmt = (
                update(TrialBalance)
                .where(
                    and_(
                        TrialBalance.id == row.id,
                        TrialBalance.is_deleted == False,  # noqa: E712
                    )
                )
                .values(
                    audited_amount=snapshot.before_value,
                    updated_at=now,
                )
            )
            await self._session.execute(stmt)
            await self._session.flush()

            new_version = _version_hash(snapshot.before_value, now)
            restored.append(
                RestoredMutation(
                    target=target,
                    restored_version=new_version,
                    conflict=False,
                )
            )

        return restored

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]:
        """Return version hash for each target's current audited_amount."""
        versions: dict[str, str] = {}

        for target in targets:
            account_code = self._extract_account_code(target)
            row = await self._fetch_row(target.project_id, target.year, account_code)

            if row is not None:
                versions[target.addr_id] = _version_hash(
                    row.audited_amount, row.updated_at
                )

        return versions
