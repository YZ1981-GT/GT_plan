"""Typed Evidence Adapters — Task 4.1 (Wave 3).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R3, R4, R6, R10
Design: §3.2 统一 Facade 与服务职责 — typed adapter

Each adapter resolves a specific evidence type (Controlled Module) to its actual DB model
and verifies scope/permissions. The contract:

    resolve/can_read/can_edit/locate/lock_for_update

Must NOT use FK-less generic raw insert to fake objects. Each adapter validates that the
target belongs to the correct project/year scope.

Supported evidence types (Controlled Modules):
 1. workpaper_cell    — 底稿单元格 (Workpaper Cell)
 2. sampling_item     — 抽样项 (Sampling Item)
 3. voucher           — 凭证 (Voucher)
 4. confirmation      — 函证 (Confirmation)
 5. review_opinion    — 复核 (Review Opinion)
 6. disclosure_note   — 附注 (Disclosure Note)
 7. report            — 报告 (Report)
 8. ai_content        — AI (AI Content)
 9. deliverable       — 交付件 (Deliverable)
10. attachment_version — 附件版本 (Attachment Version)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedTarget:
    """Resolved evidence target with verified scope."""

    target_id: str
    project_id: uuid.UUID
    audit_year: int
    target_version: int | None = None
    target_hash: str | None = None
    display_label: str | None = None


@dataclass(frozen=True)
class LocatorInfo:
    """Locator info for navigating to a specific evidence target."""

    target_id: str
    evidence_type: str
    route: str | None = None
    version: int | None = None
    # Opaque locator or controlled URL — never absolute path
    locator: str | None = None
    page: int | None = None
    region: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Protocol — typed adapter contract
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class EvidenceAdapter(Protocol):
    """Typed evidence adapter protocol.

    Each adapter resolves a specific evidence_type to its actual DB model and
    verifies scope/permissions. Must NOT use FK-less generic raw insert.
    """

    @property
    def evidence_type(self) -> str:
        """Canonical evidence type string."""
        ...

    async def resolve(
        self,
        target_id: str,
        *,
        project_id: uuid.UUID,
        audit_year: int,
        db: AsyncSession,
    ) -> ResolvedTarget | None:
        """Resolve target_id to its actual DB model row, verifying project/year scope.

        Returns None if target does not exist or does not belong to the given scope.
        """
        ...

    async def can_read(
        self,
        target_id: str,
        *,
        actor: ActorContext,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        """Check if actor can read the target (exists + scope + permission)."""
        ...

    async def can_edit(
        self,
        target_id: str,
        *,
        actor: ActorContext,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        """Check if actor can edit the target (exists + scope + permission + state)."""
        ...

    async def locate(
        self,
        target_id: str,
        *,
        version: int | None = None,
        db: AsyncSession,
    ) -> LocatorInfo | None:
        """Return locator info for navigating to the target (or specific version)."""
        ...

    async def lock_for_update(
        self,
        target_id: str,
        *,
        db: AsyncSession,
    ) -> bool:
        """Acquire FOR UPDATE lock on the target row. Returns False if not found."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

# Roles with global project visibility (aligned with scope_guard)
_GLOBAL_VISIBILITY_ROLES: frozenset[str] = frozenset({"admin", "partner"})

# Roles that can edit workpapers (aligned with capability matrix)
_EDIT_ROLES: frozenset[str] = frozenset({"admin", "partner", "manager", "auditor"})


def _as_uuid(value: str | None) -> str | None:
    """Validate & normalize a UUID string for binding to UUID-typed columns.

    Every adapter binds ``target_id`` (or a parsed part of it) to a ``uuid`` column
    (``WHERE id = :tid``). asyncpg rejects a non-UUID string with ``DataError:
    invalid input for query argument`` which propagates as HTTP 500. A non-UUID
    ``target_id`` is not a server error — it simply resolves to "not found".

    Returns the canonical UUID string when ``value`` is a valid UUID, otherwise
    ``None`` so callers can short-circuit to None/False (clean desensitized 404)
    BEFORE running any UUID-keyed SQL. Does NOT swallow DB errors — it only screens
    the id shape; genuine DB failures still surface.
    """
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


# Composite workpaper_cell target separator: "{wp_id}::{item_id}".
_CELL_COMPOSITE_SEP = "::"


def _parse_cell_target(target_id: str) -> tuple[str, str] | tuple[str, None] | None:
    """Parse a workpaper_cell target_id into a query strategy.

    A workpaper_cell target may be:
      * ``"{wp_id}::{item_id}"`` composite → returns ``(wp_uuid, item_id)`` where
        ``wp_uuid`` is the validated wp_id UUID and ``item_id`` is free text.
      * a bare ``checklist_responses.id`` UUID → returns ``(cr_uuid, None)``.
      * anything else (non-UUID, non-composite, or composite with non-UUID wp_id)
        → returns ``None`` ("not found").
    """
    if not target_id:
        return None
    if _CELL_COMPOSITE_SEP in target_id:
        wp_part, _, item_part = target_id.partition(_CELL_COMPOSITE_SEP)
        wp_uuid = _as_uuid(wp_part)
        if wp_uuid is None or not item_part:
            return None
        return (wp_uuid, item_part)
    bare = _as_uuid(target_id)
    if bare is None:
        return None
    return (bare, None)


async def _row_exists_in_scope(
    db: AsyncSession,
    *,
    table: str,
    id_col: str,
    target_id: str,
    project_id: uuid.UUID,
    audit_year: int,
    project_col: str = "project_id",
    year_col: str = "audit_year",
    extra_predicate: str | None = None,
) -> bool:
    """Check if a row exists in the given table with matching scope.

    ``id_col`` is a uuid-typed column; a non-UUID ``target_id`` is "not found".
    """
    tid = _as_uuid(target_id)
    if tid is None:
        return False
    where = f"{id_col} = :tid AND {project_col} = :pid AND {year_col} = :yr"
    if extra_predicate:
        where += f" AND {extra_predicate}"
    stmt = sa.text(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1")
    row = (
        await db.execute(
            stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year}
        )
    ).first()
    return row is not None


async def _is_project_member(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID | None
) -> bool:
    if user_id is None:
        return False
    row = (
        await db.execute(
            sa.text(
                "SELECT 1 FROM project_users WHERE project_id = :pid "
                "AND user_id = :uid AND is_deleted = false LIMIT 1"
            ),
            {"pid": str(project_id), "uid": str(user_id)},
        )
    ).first()
    return row is not None


async def _resolve_system_role(
    db: AsyncSession, user_id: uuid.UUID | None
) -> str | None:
    """Resolve the actor's authoritative system role from ``users.role`` (DB is truth).

    Returns the lowercase role string (e.g. ``"admin"``) or ``None`` when the user is
    unknown / the users table is unavailable (test envs). Defensive: never raises —
    an unresolved role simply falls through to the project-membership check.
    """
    if user_id is None:
        return None
    try:
        row = (
            await db.execute(
                sa.text("SELECT role FROM users WHERE id = :uid LIMIT 1"),
                {"uid": str(user_id)},
            )
        ).first()
    except Exception:  # pragma: no cover - users table absent in some unit envs
        return None
    if row is None:
        return None
    val = row[0]
    return val.value if hasattr(val, "value") else str(val)


async def _actor_can_access_project(
    db: AsyncSession,
    actor: ActorContext,
    project_id: uuid.UUID,
    *,
    actor_role: str | None = None,
) -> bool:
    """Check project access for actor.

    Alignment with ``ProjectYearScopeGuard`` (design §3.1): admin/partner have global
    project visibility; every other human role must be a (non-soft-deleted) project
    member. Previously this helper only checked ``project_users`` membership, which
    diverged from the scope guard — since ``project_users`` is empty platform-wide and
    the platform runs on admin/partner global visibility, a valid same-scope EvidenceRef
    create by admin/partner was wrongly denied (404) even though the scope guard admitted
    the very same actor. This does NOT weaken cross-project denial: target belonging is
    still enforced by each adapter's ``resolve`` (project_id filter), so a foreign-scope
    target resolves to None → SCOPE_NOT_FOUND_OR_FORBIDDEN regardless of the caller's role.

    ``actor_role`` (when threaded by a caller) is used directly for exact parity; when not
    provided the authoritative system role is resolved from ``users.role`` (never trusted
    from the client). Service identities keep task-scope access (unchanged).
    """
    if actor.is_service:
        # Service identities have task-scope access — assume authorized
        return True
    role = actor_role
    if role is None:
        role = await _resolve_system_role(db, actor.actor_user_id)
    if role in _GLOBAL_VISIBILITY_ROLES:
        return True
    return await _is_project_member(db, project_id, actor.actor_user_id)


async def _lock_row(
    db: AsyncSession, table: str, id_col: str, target_id: str
) -> bool:
    """Acquire SELECT ... FOR UPDATE lock on a single row.

    ``id_col`` is uuid-typed in every current caller; a non-UUID ``target_id``
    resolves to "not found" (False) rather than raising asyncpg DataError.
    """
    tid = _as_uuid(target_id)
    if tid is None:
        return False
    stmt = sa.text(f"SELECT 1 FROM {table} WHERE {id_col} = :tid FOR UPDATE")
    row = (await db.execute(stmt, {"tid": tid})).first()
    return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# 1. WorkpaperCellAdapter — 底稿单元格
# ─────────────────────────────────────────────────────────────────────────────


class WorkpaperCellAdapter:
    """Adapter for workpaper cells (checklist_responses rows bound to a working paper)."""

    evidence_type = "workpaper_cell"

    async def resolve(
        self,
        target_id: str,
        *,
        project_id: uuid.UUID,
        audit_year: int,
        db: AsyncSession,
    ) -> ResolvedTarget | None:
        # target_id = "{wp_id}::{item_id}" (composite) or a bare checklist_responses
        # row id (uuid). A non-UUID / non-composite string matches nothing → None.
        # NOTE: working_paper has NO audit_year column — year is derived from
        # projects.audit_year via checklist_responses.project_id.
        parsed = _parse_cell_target(target_id)
        if parsed is None:
            return None
        first, item_id = parsed
        if item_id is None:
            # bare checklist_responses.id (uuid)
            stmt = sa.text(
                "SELECT cr.id, cr.wp_id, cr.item_id, cr.project_id, p.audit_year "
                "FROM checklist_responses cr "
                "JOIN projects p ON p.id = cr.project_id "
                "WHERE cr.id = :tid AND cr.project_id = :pid AND p.audit_year = :yr "
                "LIMIT 1"
            )
            params = {"tid": first, "pid": str(project_id), "yr": audit_year}
        else:
            # composite "{wp_id}::{item_id}": query by wp_id + item_id
            stmt = sa.text(
                "SELECT cr.id, cr.wp_id, cr.item_id, cr.project_id, p.audit_year "
                "FROM checklist_responses cr "
                "JOIN projects p ON p.id = cr.project_id "
                "WHERE cr.wp_id = :wid AND cr.item_id = :iid "
                "AND cr.project_id = :pid AND p.audit_year = :yr "
                "LIMIT 1"
            )
            params = {"wid": first, "iid": item_id, "pid": str(project_id), "yr": audit_year}
        row = (await db.execute(stmt, params)).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
            display_label=f"cell:{row['item_id']}",
        )

    async def can_read(
        self,
        target_id: str,
        *,
        actor: ActorContext,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        return await self._cell_exists_in_project(target_id, project_id=project_id, db=db)

    async def can_edit(
        self,
        target_id: str,
        *,
        actor: ActorContext,
        project_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        if actor.is_service:
            return False  # Service cannot edit user-facing content
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        return await self._cell_exists_in_project(target_id, project_id=project_id, db=db)

    @staticmethod
    async def _cell_exists_in_project(
        target_id: str, *, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        """Existence + project-scope check for a bare-uuid or composite cell target.

        Non-UUID / non-composite target_id → False (not a DB error).
        """
        parsed = _parse_cell_target(target_id)
        if parsed is None:
            return False
        first, item_id = parsed
        if item_id is None:
            stmt = sa.text(
                "SELECT 1 FROM checklist_responses cr "
                "JOIN working_paper wp ON wp.id = cr.wp_id "
                "WHERE cr.id = :tid AND cr.project_id = :pid LIMIT 1"
            )
            params = {"tid": first, "pid": str(project_id)}
        else:
            stmt = sa.text(
                "SELECT 1 FROM checklist_responses cr "
                "JOIN working_paper wp ON wp.id = cr.wp_id "
                "WHERE cr.wp_id = :wid AND cr.item_id = :iid AND cr.project_id = :pid LIMIT 1"
            )
            params = {"wid": first, "iid": item_id, "pid": str(project_id)}
        row = (await db.execute(stmt, params)).first()
        return row is not None

    async def locate(
        self,
        target_id: str,
        *,
        version: int | None = None,
        db: AsyncSession,
    ) -> LocatorInfo | None:
        parsed = _parse_cell_target(target_id)
        if parsed is None:
            return None
        first, item_id = parsed
        if item_id is None:
            stmt = sa.text(
                "SELECT cr.wp_id, cr.item_id FROM checklist_responses cr "
                "WHERE cr.id = :tid LIMIT 1"
            )
            params = {"tid": first}
        else:
            stmt = sa.text(
                "SELECT cr.wp_id, cr.item_id FROM checklist_responses cr "
                "WHERE cr.wp_id = :wid AND cr.item_id = :iid LIMIT 1"
            )
            params = {"wid": first, "iid": item_id}
        row = (await db.execute(stmt, params)).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/workpapers/{row['wp_id']}",
            locator=f"cell:{row['item_id']}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        parsed = _parse_cell_target(target_id)
        if parsed is None:
            return False
        first, item_id = parsed
        if item_id is None:
            return await _lock_row(db, "checklist_responses", "id", target_id)
        # composite: lock the row identified by wp_id + item_id
        stmt = sa.text(
            "SELECT 1 FROM checklist_responses "
            "WHERE wp_id = :wid AND item_id = :iid FOR UPDATE"
        )
        row = (await db.execute(stmt, {"wid": first, "iid": item_id})).first()
        return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. SamplingItemAdapter — 抽样项
# ─────────────────────────────────────────────────────────────────────────────


class SamplingItemAdapter:
    """Adapter for sampling items (voucher sampling results)."""

    evidence_type = "sampling_item"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT sv.id, sv.project_id, sv.year AS audit_year "
            "FROM sampled_vouchers sv "
            "WHERE sv.id = :tid AND sv.project_id = :pid AND sv.year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM sampled_vouchers WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, working_paper_id FROM sampled_vouchers WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/workpapers/{row['working_paper_id']}" if row.get("working_paper_id") else None,
            locator=f"sample:{target_id}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "sampled_vouchers", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. VoucherAdapter — 凭证
# ─────────────────────────────────────────────────────────────────────────────


class VoucherAdapter:
    """Adapter for vouchers (tb_ledger journal entries)."""

    evidence_type = "voucher"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, project_id, year AS audit_year, voucher_no "
            "FROM tb_ledger "
            "WHERE id = :tid AND project_id = :pid AND year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
            display_label=f"voucher:{row.get('voucher_no', '')}",
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text("SELECT 1 FROM tb_ledger WHERE id = :tid AND project_id = :pid LIMIT 1")
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        # Voucher entries are imported data — editing depends on dataset state
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, voucher_no, voucher_date FROM tb_ledger WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            locator=f"voucher:{row.get('voucher_no', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "tb_ledger", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ConfirmationAdapter — 函证
# ─────────────────────────────────────────────────────────────────────────────


class ConfirmationAdapter:
    """Adapter for confirmations (confirmation records)."""

    evidence_type = "confirmation"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        # confirmations has NO year column — scope by projects.audit_year.
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT c.id, c.project_id, p.audit_year "
            "FROM confirmations c "
            "JOIN projects p ON p.id = c.project_id "
            "WHERE c.id = :tid AND c.project_id = :pid AND p.audit_year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text("SELECT 1 FROM confirmations WHERE id = :tid AND project_id = :pid LIMIT 1")
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, counterparty, wp_id FROM confirmations WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/confirmations/{target_id}",
            locator=f"confirmation:{row.get('counterparty', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "confirmations", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ReviewOpinionAdapter — 复核意见
# ─────────────────────────────────────────────────────────────────────────────


class ReviewOpinionAdapter:
    """Adapter for review opinions (review_records / review_conversations)."""

    evidence_type = "review_opinion"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        # review_records has NO project_id and working_paper has NO audit_year:
        # scope is derived via working_paper.project_id → projects.audit_year.
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT rr.id, wp.project_id, p.audit_year "
            "FROM review_records rr "
            "JOIN working_paper wp ON wp.id = rr.working_paper_id "
            "JOIN projects p ON p.id = wp.project_id "
            "WHERE rr.id = :tid AND wp.project_id = :pid AND p.audit_year = :yr "
            "LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        # review_records has NO project_id — join working_paper for scope.
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM review_records rr "
            "JOIN working_paper wp ON wp.id = rr.working_paper_id "
            "WHERE rr.id = :tid AND wp.project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        # Only non-service actors with project access can edit review opinions
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        # review_records has NO section column — use cell_reference for the label.
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, working_paper_id, cell_reference FROM review_records "
            "WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/workpapers/{row['working_paper_id']}",
            locator=f"review:{row.get('cell_reference', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "review_records", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 6. DisclosureNoteAdapter — 附注
# ─────────────────────────────────────────────────────────────────────────────


class DisclosureNoteAdapter:
    """Adapter for disclosure notes (disclosure_notes / note sections)."""

    evidence_type = "disclosure_note"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT dn.id, dn.project_id, dn.year AS audit_year "
            "FROM disclosure_notes dn "
            "WHERE dn.id = :tid AND dn.project_id = :pid AND dn.year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM disclosure_notes WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, section_id, section_title FROM disclosure_notes WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/notes/{target_id}",
            locator=f"note:{row.get('section_id', row.get('section_title', ''))}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "disclosure_notes", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 7. ReportAdapter — 报告
# ─────────────────────────────────────────────────────────────────────────────


class ReportAdapter:
    """Adapter for audit reports (audit_report — project+year scoped report)."""

    evidence_type = "report"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        # "report" evidence = the audit report (audit_report), project+year scoped.
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT rc.id, rc.project_id, rc.year AS audit_year "
            "FROM audit_report rc "
            "WHERE rc.id = :tid AND rc.project_id = :pid AND rc.year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM audit_report WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, opinion_type FROM audit_report WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            route=f"/reports/{target_id}",
            locator=f"report:{row.get('opinion_type', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "audit_report", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 8. AiContentAdapter — AI 内容
# ─────────────────────────────────────────────────────────────────────────────


class AiContentAdapter:
    """Adapter for AI content (ai_content_log — AI output provenance log)."""

    evidence_type = "ai_content"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        # ai_content_log has NO year/status columns — scope via projects.audit_year.
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT acl.id, acl.project_id, p.audit_year "
            "FROM ai_content_log acl "
            "JOIN projects p ON p.id = acl.project_id "
            "WHERE acl.id = :tid AND acl.project_id = :pid AND p.audit_year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM ai_content_log WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        # AI content confirm/reject is a human-only action
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, target_cell FROM ai_content_log WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            locator=f"ai:{row.get('target_cell', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "ai_content_log", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 9. DeliverableAdapter — 交付件
# ─────────────────────────────────────────────────────────────────────────────


class DeliverableAdapter:
    """Adapter for deliverables (deliverable_section_state — section versions)."""

    evidence_type = "deliverable"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        # "deliverable" evidence = deliverable_section_state (version_no, not version).
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT d.id, d.project_id, d.year AS audit_year, d.version_no "
            "FROM deliverable_section_state d "
            "WHERE d.id = :tid AND d.project_id = :pid AND d.year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
            target_version=row.get("version_no"),
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM deliverable_section_state WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if actor.is_service:
            return False
        return await self.can_read(target_id, actor=actor, project_id=project_id, db=db)

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT id, section_code, version_no FROM deliverable_section_state WHERE id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            version=row.get("version_no"),
            route=f"/deliverables/{target_id}",
            locator=f"deliverable:{row.get('section_code', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "deliverable_section_state", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# 10. AttachmentVersionAdapter — 附件版本
# ─────────────────────────────────────────────────────────────────────────────


class AttachmentVersionAdapter:
    """Adapter for attachment versions (attachment_versions via governance model)."""

    evidence_type = "attachment_version"

    async def resolve(
        self, target_id: str, *, project_id: uuid.UUID, audit_year: int, db: AsyncSession
    ) -> ResolvedTarget | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT av.id, av.project_id, av.audit_year, av.version_no, av.content_hash "
            "FROM attachment_versions av "
            "WHERE av.id = :tid AND av.project_id = :pid AND av.audit_year = :yr LIMIT 1"
        )
        row = (
            await db.execute(stmt, {"tid": tid, "pid": str(project_id), "yr": audit_year})
        ).mappings().first()
        if row is None:
            return None
        return ResolvedTarget(
            target_id=target_id,
            project_id=uuid.UUID(str(row["project_id"])),
            audit_year=row["audit_year"],
            target_version=row.get("version_no"),
            target_hash=row.get("content_hash"),
        )

    async def can_read(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        stmt = sa.text(
            "SELECT 1 FROM attachment_versions "
            "WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        return (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).first() is not None

    async def can_edit(
        self, target_id: str, *, actor: ActorContext, project_id: uuid.UUID, db: AsyncSession
    ) -> bool:
        # Attachment versions are immutable — "edit" means replacing (creating new version)
        # which requires edit permission on the parent attachment
        if actor.is_service:
            return False
        if not await _actor_can_access_project(db, actor, project_id):
            return False
        tid = _as_uuid(target_id)
        if tid is None:
            return False
        # Check version availability (only staged/available can be part of replacement flow)
        stmt = sa.text(
            "SELECT availability FROM attachment_versions "
            "WHERE id = :tid AND project_id = :pid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid, "pid": str(project_id)})).mappings().first()
        if row is None:
            return False
        return row.get("availability") in ("staged", "available")

    async def locate(
        self, target_id: str, *, version: int | None = None, db: AsyncSession
    ) -> LocatorInfo | None:
        tid = _as_uuid(target_id)
        if tid is None:
            return None
        stmt = sa.text(
            "SELECT av.id, av.attachment_id, av.version_no, av.media_type "
            "FROM attachment_versions av WHERE av.id = :tid LIMIT 1"
        )
        row = (await db.execute(stmt, {"tid": tid})).mappings().first()
        if row is None:
            return None
        return LocatorInfo(
            target_id=target_id,
            evidence_type=self.evidence_type,
            version=row.get("version_no"),
            route=f"/attachments/{row['attachment_id']}/versions/{row.get('version_no', '')}",
            locator=f"attachment_version:{row['attachment_id']}:v{row.get('version_no', '')}",
        )

    async def lock_for_update(self, target_id: str, *, db: AsyncSession) -> bool:
        return await _lock_row(db, "attachment_versions", "id", target_id)


# ─────────────────────────────────────────────────────────────────────────────
# Registry — evidence_type string → adapter instance
# ─────────────────────────────────────────────────────────────────────────────

#: Singleton adapter instances — one per evidence type.
_ADAPTER_INSTANCES: dict[str, EvidenceAdapter] = {}


def _build_registry() -> dict[str, EvidenceAdapter]:
    """Build the evidence type → adapter registry (called once at module load)."""
    adapters: list[EvidenceAdapter] = [
        WorkpaperCellAdapter(),
        SamplingItemAdapter(),
        VoucherAdapter(),
        ConfirmationAdapter(),
        ReviewOpinionAdapter(),
        DisclosureNoteAdapter(),
        ReportAdapter(),
        AiContentAdapter(),
        DeliverableAdapter(),
        AttachmentVersionAdapter(),
    ]
    return {a.evidence_type: a for a in adapters}


_ADAPTER_INSTANCES = _build_registry()

#: Frozen set of all supported evidence types.
SUPPORTED_EVIDENCE_TYPES: frozenset[str] = frozenset(_ADAPTER_INSTANCES.keys())


def get_adapter(evidence_type: str) -> EvidenceAdapter:
    """Retrieve the typed adapter for the given evidence_type.

    Raises EvidenceGovernanceError if evidence_type is unsupported.
    """
    adapter = _ADAPTER_INSTANCES.get(evidence_type)
    if adapter is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            f"unsupported evidence type",
        )
    return adapter


def list_adapters() -> dict[str, EvidenceAdapter]:
    """Return the full registry (read-only view for testing/introspection)."""
    return dict(_ADAPTER_INSTANCES)


__all__ = [
    "EvidenceAdapter",
    "ResolvedTarget",
    "LocatorInfo",
    "WorkpaperCellAdapter",
    "SamplingItemAdapter",
    "VoucherAdapter",
    "ConfirmationAdapter",
    "ReviewOpinionAdapter",
    "DisclosureNoteAdapter",
    "ReportAdapter",
    "AiContentAdapter",
    "DeliverableAdapter",
    "AttachmentVersionAdapter",
    "SUPPORTED_EVIDENCE_TYPES",
    "get_adapter",
    "list_adapters",
]
