"""EvidenceRefQueryService — Task 4.3 (Wave 3).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R3, R4, R9, R15
Design: §4.4 EvidenceRef 与统一依赖图 / §6.1 通用约定

Implements:
  1. Intent idempotency verification (end-to-end, per design partial unique)
  2. Bidirectional cursor queries:
     - query_refs_from_source: find all refs originating from a source
     - query_refs_to_evidence: find all refs targeting this evidence
  3. Deactivation flow:
     - deactivate_ref: sets status='deactivated', preserves history, triggers outbox
  4. Active EvidenceDependency queries:
     - query_dependencies: direct edges from source
  5. Impact API (direct + transitive):
     - query_impact: bounded BFS over active dependencies, deduped, scope-filtered

All results:
  - Deduplicated (by ref_id for refs, by target for impact)
  - Filtered to only include objects the current actor can read (scope + permission)
  - NEVER include cross-project objects
  - Use typed adapters can_read() for permission filtering
  - Cursor-based pagination: limit default 100, max 200 (design §6.1)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.frozen_contracts import (
    CURSOR_PAGE_DEFAULT_LIMIT,
    CURSOR_PAGE_MAX_LIMIT,
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.typed_adapters import (
    SUPPORTED_EVIDENCE_TYPES,
    get_adapter,
)


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceRefRow:
    """A single EvidenceRef record returned from queries."""

    id: uuid.UUID
    project_id: uuid.UUID
    audit_year: int
    source_type: str
    source_id: str
    source_version: int | None
    evidence_type: str
    evidence_id: str
    attachment_version_id: uuid.UUID | None
    target_version: int | None
    target_hash: str | None
    label: str | None
    context: str | None
    intent_hash: str
    status: str
    created_at: Any  # datetime


@dataclass(frozen=True)
class CursorPage:
    """Cursor-based pagination result."""

    items: list[EvidenceRefRow]
    next_cursor: str | None = None
    has_more: bool = False


@dataclass(frozen=True)
class DependencyRow:
    """A single EvidenceDependency edge."""

    id: uuid.UUID
    project_id: uuid.UUID
    audit_year: int
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    source_version: int | None
    target_version: int | None
    edge_hash: str
    status: str
    evidence_ref_id: uuid.UUID | None


@dataclass(frozen=True)
class DependencyPage:
    """Cursor-based pagination result for dependencies."""

    items: list[DependencyRow]
    next_cursor: str | None = None
    has_more: bool = False


@dataclass(frozen=True)
class ImpactNode:
    """A node in the impact result set (direct or transitive)."""

    target_type: str
    target_id: str
    distance: int  # 1 = direct, 2+ = transitive
    path: list[str] = field(default_factory=list)  # edge ids forming the path


@dataclass(frozen=True)
class ImpactResult:
    """Deduplicated impact result with only readable objects."""

    nodes: list[ImpactNode]
    total_visited: int
    truncated: bool = False  # True if BFS hit the bound limit


@dataclass(frozen=True)
class DeactivateRefResult:
    """Result of deactivating a ref."""

    ref_id: uuid.UUID
    previous_status: str
    new_status: str
    reason: str


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

# Maximum BFS depth for transitive impact to prevent unbounded graph traversal (R15)
_MAX_IMPACT_BFS_DEPTH = 50
_MAX_IMPACT_NODES = 1000


class EvidenceRefQueryService:
    """Query service for EvidenceRef, bidirectional lookup, deactivation,
    dependency graph, and impact analysis.

    All queries enforce:
      - Scope isolation (project_id + audit_year)
      - Permission filtering via typed adapters can_read()
      - Deduplication
      - Cursor-based pagination (limit default 100, max 200)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Intent idempotency — verify existing active ref
    # ─────────────────────────────────────────────────────────────────────────

    async def find_active_ref_by_intent(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int,
        intent_hash: str,
    ) -> EvidenceRefRow | None:
        """Find an existing active EvidenceRef with the same intent_hash (P7).

        Uses the partial unique index (project_id, audit_year, intent_hash)
        WHERE status='active'. Returns None if not found.
        """
        row = (
            await self._db.execute(
                sa.text("""
                    SELECT id, project_id, audit_year,
                           source_type, source_id, source_version,
                           evidence_type, evidence_id, attachment_version_id,
                           target_version, target_hash,
                           label, context, intent_hash, status, created_at
                    FROM evidence_refs
                    WHERE project_id = :pid
                      AND audit_year = :yr
                      AND intent_hash = :ih
                      AND status = 'active'
                    LIMIT 1
                """),
                {"pid": str(project_id), "yr": audit_year, "ih": intent_hash},
            )
        ).mappings().first()
        if row is None:
            return None
        return _map_ref_row(row)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Bidirectional cursor queries
    # ─────────────────────────────────────────────────────────────────────────

    async def query_refs_from_source(
        self,
        *,
        source_type: str,
        source_id: str,
        project_id: uuid.UUID,
        audit_year: int,
        actor: ActorContext,
        status: str = "active",
        cursor: str | None = None,
        limit: int = CURSOR_PAGE_DEFAULT_LIMIT,
    ) -> CursorPage:
        """Find all refs originating from a specific source (source→*).

        Bidirectional query direction 1: from source_type/source_id → find all refs.
        Results filtered by actor's read permission on the target (evidence side).
        """
        limit = _clamp_limit(limit)

        # Build keyset cursor condition
        cursor_cond, cursor_params = _parse_cursor(cursor)

        stmt = sa.text(f"""
            SELECT id, project_id, audit_year,
                   source_type, source_id, source_version,
                   evidence_type, evidence_id, attachment_version_id,
                   target_version, target_hash,
                   label, context, intent_hash, status, created_at
            FROM evidence_refs
            WHERE project_id = :pid
              AND audit_year = :yr
              AND source_type = :stype
              AND source_id = :sid
              AND status = :status
              {cursor_cond}
            ORDER BY created_at ASC, id ASC
            LIMIT :lim
        """)
        params = {
            "pid": str(project_id),
            "yr": audit_year,
            "stype": source_type,
            "sid": source_id,
            "status": status,
            "lim": limit + 1,  # fetch one extra to detect has_more
            **cursor_params,
        }
        rows = (await self._db.execute(stmt, params)).mappings().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        # Filter by actor can_read on evidence/target side
        items: list[EvidenceRefRow] = []
        for r in rows:
            ref_row = _map_ref_row(r)
            if await self._actor_can_read_target(
                actor=actor,
                evidence_type=ref_row.evidence_type,
                evidence_id=ref_row.evidence_id,
                project_id=project_id,
            ):
                items.append(ref_row)

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = f"{last.created_at.isoformat()}|{last.id}"

        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def query_refs_to_evidence(
        self,
        *,
        evidence_type: str,
        evidence_id: str,
        project_id: uuid.UUID,
        audit_year: int,
        actor: ActorContext,
        status: str = "active",
        cursor: str | None = None,
        limit: int = CURSOR_PAGE_DEFAULT_LIMIT,
    ) -> CursorPage:
        """Find all refs targeting this evidence (→evidence).

        Bidirectional query direction 2: from evidence_type/evidence_id → find all refs.
        Results filtered by actor's read permission on the source side.
        """
        limit = _clamp_limit(limit)

        cursor_cond, cursor_params = _parse_cursor(cursor)

        stmt = sa.text(f"""
            SELECT id, project_id, audit_year,
                   source_type, source_id, source_version,
                   evidence_type, evidence_id, attachment_version_id,
                   target_version, target_hash,
                   label, context, intent_hash, status, created_at
            FROM evidence_refs
            WHERE project_id = :pid
              AND audit_year = :yr
              AND evidence_type = :etype
              AND evidence_id = :eid
              AND status = :status
              {cursor_cond}
            ORDER BY created_at ASC, id ASC
            LIMIT :lim
        """)
        params = {
            "pid": str(project_id),
            "yr": audit_year,
            "etype": evidence_type,
            "eid": evidence_id,
            "status": status,
            "lim": limit + 1,
            **cursor_params,
        }
        rows = (await self._db.execute(stmt, params)).mappings().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        # Filter by actor can_read on source side
        items: list[EvidenceRefRow] = []
        for r in rows:
            ref_row = _map_ref_row(r)
            if await self._actor_can_read_target(
                actor=actor,
                evidence_type=ref_row.source_type,
                evidence_id=ref_row.source_id,
                project_id=project_id,
            ):
                items.append(ref_row)

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = f"{last.created_at.isoformat()}|{last.id}"

        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Deactivation flow (R3.4)
    # ─────────────────────────────────────────────────────────────────────────

    async def deactivate_ref(
        self,
        *,
        ref_id: uuid.UUID,
        reason: str,
        actor: ActorContext,
        project_id: uuid.UUID,
        audit_year: int,
    ) -> DeactivateRefResult:
        """Deactivate an EvidenceRef (R3.4).

        Requirements:
          - Requires reason (R3.4)
          - Preserves history record (status change, not delete)
          - Stops participating in new FormalOutput
          - Triggers impact assessment via outbox
          - Updates associated EvidenceDependency edge status
        """
        if not reason or not reason.strip():
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                "deactivation reason is required",
            )

        # Fetch the ref within scope
        row = (
            await self._db.execute(
                sa.text("""
                    SELECT id, status, project_id, audit_year,
                           source_type, source_id, evidence_type, evidence_id
                    FROM evidence_refs
                    WHERE id = :rid
                      AND project_id = :pid
                      AND audit_year = :yr
                    FOR UPDATE
                """),
                {"rid": str(ref_id), "pid": str(project_id), "yr": audit_year},
            )
        ).mappings().first()

        if row is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "reference not found or forbidden",
            )

        current_status = row["status"]
        if current_status == "deactivated":
            # Already deactivated — idempotent return
            return DeactivateRefResult(
                ref_id=ref_id,
                previous_status="deactivated",
                new_status="deactivated",
                reason=reason,
            )

        if current_status != "active":
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"cannot deactivate ref in status '{current_status}'",
            )

        # Deactivate the ref (preserve history — update, NOT delete)
        await self._db.execute(
            sa.text("""
                UPDATE evidence_refs
                SET status = 'deactivated',
                    deactivated_reason = :reason,
                    deactivated_at = NOW(),
                    deactivated_by_user_id = :uid
                WHERE id = :rid
            """),
            {
                "rid": str(ref_id),
                "reason": reason.strip(),
                "uid": str(actor.actor_user_id) if actor.actor_user_id else None,
            },
        )

        # Update associated EvidenceDependency edge status
        await self._db.execute(
            sa.text("""
                UPDATE evidence_dependencies
                SET status = 'deactivated'
                WHERE evidence_ref_id = :rid
                  AND status = 'active'
            """),
            {"rid": str(ref_id)},
        )

        # Enqueue outbox event for impact assessment / stale propagation
        outbox_id = uuid.uuid4()
        await self._db.execute(
            sa.text("""
                INSERT INTO evidence_outbox (
                    id, event_type, payload, status, created_at
                ) VALUES (
                    :id, :event_type, :payload::jsonb, 'pending', NOW()
                )
            """),
            {
                "id": str(outbox_id),
                "event_type": "evidence_ref.deactivated",
                "payload": _json_dumps({
                    "ref_id": str(ref_id),
                    "project_id": str(project_id),
                    "audit_year": audit_year,
                    "source_type": row["source_type"],
                    "source_id": row["source_id"],
                    "evidence_type": row["evidence_type"],
                    "evidence_id": row["evidence_id"],
                    "reason": reason.strip(),
                }),
            },
        )

        await self._db.flush()

        return DeactivateRefResult(
            ref_id=ref_id,
            previous_status=current_status,
            new_status="deactivated",
            reason=reason.strip(),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Active EvidenceDependency queries
    # ─────────────────────────────────────────────────────────────────────────

    async def query_dependencies(
        self,
        *,
        source_type: str,
        source_id: str,
        project_id: uuid.UUID,
        audit_year: int,
        actor: ActorContext,
        cursor: str | None = None,
        limit: int = CURSOR_PAGE_DEFAULT_LIMIT,
    ) -> DependencyPage:
        """Query direct active EvidenceDependency edges from a source.

        Returns only edges whose target the actor can read.
        """
        limit = _clamp_limit(limit)
        cursor_cond, cursor_params = _parse_cursor(cursor, id_col="ed.id", ts_col="ed.created_at")

        stmt = sa.text(f"""
            SELECT ed.id, ed.project_id, ed.audit_year,
                   ed.source_type, ed.source_id,
                   ed.target_type, ed.target_id,
                   ed.source_version, ed.target_version,
                   ed.edge_hash, ed.status,
                   ed.evidence_ref_id, ed.created_at
            FROM evidence_dependencies ed
            WHERE ed.project_id = :pid
              AND ed.audit_year = :yr
              AND ed.source_type = :stype
              AND ed.source_id = :sid
              AND ed.status = 'active'
              {cursor_cond}
            ORDER BY ed.created_at ASC, ed.id ASC
            LIMIT :lim
        """)
        params = {
            "pid": str(project_id),
            "yr": audit_year,
            "stype": source_type,
            "sid": source_id,
            "lim": limit + 1,
            **cursor_params,
        }
        rows = (await self._db.execute(stmt, params)).mappings().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[DependencyRow] = []
        for r in rows:
            dep = _map_dep_row(r)
            # Permission filter: actor must be able to read the target
            if await self._actor_can_read_target(
                actor=actor,
                evidence_type=dep.target_type,
                evidence_id=dep.target_id,
                project_id=project_id,
            ):
                items.append(dep)

        next_cursor = None
        if has_more and items:
            last_r = rows[limit - 1] if len(rows) >= limit else rows[-1]
            next_cursor = f"{last_r['created_at'].isoformat()}|{last_r['id']}"

        return DependencyPage(items=items, next_cursor=next_cursor, has_more=has_more)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Impact API — direct + transitive (bounded BFS)
    # ─────────────────────────────────────────────────────────────────────────

    async def query_impact(
        self,
        *,
        target_type: str,
        target_id: str,
        project_id: uuid.UUID,
        audit_year: int,
        actor: ActorContext,
        max_depth: int = _MAX_IMPACT_BFS_DEPTH,
    ) -> ImpactResult:
        """Query direct and transitive impact of a change to a given source node.

        Uses bounded BFS over active EvidenceDependency edges within the same
        project and year. Deduplicates by (target_type, target_id) visited set.

        Returns only nodes the actor can read in the current scope.
        NEVER includes cross-project objects.

        Design: §4.4 — source→target direction means "source变化使target stale"
        So we traverse edges WHERE (source_type, source_id) = target to find
        what would become stale if target changes.
        """
        visited: set[tuple[str, str]] = set()
        result_nodes: list[ImpactNode] = []
        truncated = False

        # BFS frontier: (type, id, distance, path)
        frontier: list[tuple[str, str, int, list[str]]] = [
            (target_type, target_id, 0, [])
        ]
        visited.add((target_type, target_id))

        while frontier:
            next_frontier: list[tuple[str, str, int, list[str]]] = []

            for src_type, src_id, dist, path in frontier:
                if dist >= max_depth:
                    truncated = True
                    continue

                if len(result_nodes) >= _MAX_IMPACT_NODES:
                    truncated = True
                    break

                # Find all active edges where this node is the source
                # (source changes → targets become stale)
                edges = (
                    await self._db.execute(
                        sa.text("""
                            SELECT id, target_type, target_id
                            FROM evidence_dependencies
                            WHERE project_id = :pid
                              AND audit_year = :yr
                              AND source_type = :stype
                              AND source_id = :sid
                              AND status = 'active'
                        """),
                        {
                            "pid": str(project_id),
                            "yr": audit_year,
                            "stype": src_type,
                            "sid": src_id,
                        },
                    )
                ).mappings().all()

                for edge in edges:
                    t_type = edge["target_type"]
                    t_id = edge["target_id"]
                    edge_id = str(edge["id"])
                    key = (t_type, t_id)

                    if key in visited:
                        continue  # Dedup by visited set
                    visited.add(key)

                    new_path = path + [edge_id]
                    new_dist = dist + 1

                    result_nodes.append(
                        ImpactNode(
                            target_type=t_type,
                            target_id=t_id,
                            distance=new_dist,
                            path=new_path,
                        )
                    )
                    next_frontier.append((t_type, t_id, new_dist, new_path))

            if truncated:
                break
            frontier = next_frontier

        # Filter: only include nodes the actor can read in scope
        readable_nodes: list[ImpactNode] = []
        for node in result_nodes:
            if await self._actor_can_read_target(
                actor=actor,
                evidence_type=node.target_type,
                evidence_id=node.target_id,
                project_id=project_id,
            ):
                readable_nodes.append(node)

        return ImpactResult(
            nodes=readable_nodes,
            total_visited=len(visited),
            truncated=truncated,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Deactivation history query
    # ─────────────────────────────────────────────────────────────────────────

    async def query_deactivation_history(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int,
        actor: ActorContext,
        cursor: str | None = None,
        limit: int = CURSOR_PAGE_DEFAULT_LIMIT,
    ) -> CursorPage:
        """Query deactivated refs with history (reason, when, who).

        Returns deactivated refs the actor can read. Preserves full history.
        """
        limit = _clamp_limit(limit)
        cursor_cond, cursor_params = _parse_cursor(cursor)

        stmt = sa.text(f"""
            SELECT id, project_id, audit_year,
                   source_type, source_id, source_version,
                   evidence_type, evidence_id, attachment_version_id,
                   target_version, target_hash,
                   label, context, intent_hash, status, created_at
            FROM evidence_refs
            WHERE project_id = :pid
              AND audit_year = :yr
              AND status = 'deactivated'
              {cursor_cond}
            ORDER BY created_at ASC, id ASC
            LIMIT :lim
        """)
        params = {
            "pid": str(project_id),
            "yr": audit_year,
            "lim": limit + 1,
            **cursor_params,
        }
        rows = (await self._db.execute(stmt, params)).mappings().all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[EvidenceRefRow] = []
        for r in rows:
            ref_row = _map_ref_row(r)
            # Filter: actor must be able to read at least one end
            source_readable = await self._actor_can_read_target(
                actor=actor,
                evidence_type=ref_row.source_type,
                evidence_id=ref_row.source_id,
                project_id=project_id,
            )
            target_readable = await self._actor_can_read_target(
                actor=actor,
                evidence_type=ref_row.evidence_type,
                evidence_id=ref_row.evidence_id,
                project_id=project_id,
            )
            if source_readable or target_readable:
                items.append(ref_row)

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = f"{last.created_at.isoformat()}|{last.id}"

        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _actor_can_read_target(
        self,
        *,
        actor: ActorContext,
        evidence_type: str,
        evidence_id: str,
        project_id: uuid.UUID,
    ) -> bool:
        """Check if actor can read the given evidence target using typed adapters.

        Returns False for unsupported types (silently filtered out).
        """
        if evidence_type not in SUPPORTED_EVIDENCE_TYPES:
            # Unknown types are filtered out — never exposed
            return False
        try:
            adapter = get_adapter(evidence_type)
            return await adapter.can_read(
                evidence_id,
                actor=actor,
                project_id=project_id,
                db=self._db,
            )
        except EvidenceGovernanceError:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _clamp_limit(limit: int) -> int:
    """Clamp pagination limit to [1, CURSOR_PAGE_MAX_LIMIT]."""
    if limit < 1:
        return CURSOR_PAGE_DEFAULT_LIMIT
    return min(limit, CURSOR_PAGE_MAX_LIMIT)


def _parse_cursor(
    cursor: str | None,
    *,
    id_col: str = "id",
    ts_col: str = "created_at",
) -> tuple[str, dict[str, Any]]:
    """Parse a keyset cursor string 'iso_timestamp|uuid' into SQL condition + params.

    Returns (sql_fragment, param_dict). If cursor is None, returns empty condition.
    """
    if not cursor:
        return "", {}

    parts = cursor.split("|", 1)
    if len(parts) != 2:
        return "", {}

    ts_str, id_str = parts
    try:
        cursor_id = str(uuid.UUID(id_str))
    except (ValueError, TypeError):
        return "", {}

    # Keyset pagination: (created_at, id) > (cursor_ts, cursor_id)
    cond = f"AND ({ts_col} > :cursor_ts OR ({ts_col} = :cursor_ts AND {id_col} > :cursor_id))"
    return cond, {"cursor_ts": ts_str, "cursor_id": cursor_id}


def _map_ref_row(r: Any) -> EvidenceRefRow:
    """Map a database row mapping to an EvidenceRefRow dataclass."""
    return EvidenceRefRow(
        id=uuid.UUID(str(r["id"])),
        project_id=uuid.UUID(str(r["project_id"])),
        audit_year=r["audit_year"],
        source_type=r["source_type"],
        source_id=r["source_id"],
        source_version=r.get("source_version"),
        evidence_type=r["evidence_type"],
        evidence_id=r["evidence_id"],
        attachment_version_id=(
            uuid.UUID(str(r["attachment_version_id"]))
            if r.get("attachment_version_id")
            else None
        ),
        target_version=r.get("target_version"),
        target_hash=r.get("target_hash"),
        label=r.get("label"),
        context=r.get("context"),
        intent_hash=r["intent_hash"],
        status=r["status"],
        created_at=r["created_at"],
    )


def _map_dep_row(r: Any) -> DependencyRow:
    """Map a database row mapping to a DependencyRow dataclass."""
    return DependencyRow(
        id=uuid.UUID(str(r["id"])),
        project_id=uuid.UUID(str(r["project_id"])),
        audit_year=r["audit_year"],
        source_type=r["source_type"],
        source_id=r["source_id"],
        target_type=r["target_type"],
        target_id=r["target_id"],
        source_version=r.get("source_version"),
        target_version=r.get("target_version"),
        edge_hash=r["edge_hash"],
        status=r["status"],
        evidence_ref_id=(
            uuid.UUID(str(r["evidence_ref_id"]))
            if r.get("evidence_ref_id")
            else None
        ),
    )


def _json_dumps(obj: Any) -> str:
    """Deterministic JSON serialization for outbox payloads."""
    import json

    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "EvidenceRefQueryService",
    "EvidenceRefRow",
    "CursorPage",
    "DependencyRow",
    "DependencyPage",
    "ImpactNode",
    "ImpactResult",
    "DeactivateRefResult",
]
