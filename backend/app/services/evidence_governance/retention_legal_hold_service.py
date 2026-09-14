"""RetentionLegalHoldService — Task 7.3 (Wave 6).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2, R12, R13
Design: §4.6 (LegalHold/LegalHoldScope/EvidenceTombstone), §5.5 (Archive/Retention/
         Legal Hold), §2.2 (capability 基线 — retention.purge / legal_hold.*)
Properties:
  P26 — Legal Hold 单调保护：active hold 闭包内 delete/purge/overwrite 对任何授权级别
        （任意角色 / admin / Service Identity / 紧急授权）恒零效果且无绕过；内容替换只能
        新增版本，不覆盖受保护历史。
  P27 — 保留期边界：仅 hold 已解除、retention 已届满、主体具备 ``retention.purge`` 且
        无悬空活动 EvidenceRef 时才允许清理；任一条件不满足则清理效果 = 0。

核心职责（design §5.5）：
  1. **激活固化统一图闭包**：Legal Hold 激活时用唯一 ``UnifiedGraphBuilder`` 构造同 scope
     统一图，从受保护种子节点计算 direct + transitive 闭包，固化为 ``legal_hold_scopes``
     行，并记录激活时的 ``graph_watermark``。
  2. **监听新增边**：hold 内新增边若其 source 已在闭包内，则 target 及其下游闭包被单调纳入
     transitive 保护范围（范围只增不减；``is_active`` 单调，历史不物理删除）。
  3. **零效果语义**：闭包内节点的 delete/purge/overwrite 对任何 actor 恒零效果——委托
     ``CapabilityGuard.authorize_destructive_under_hold``（``legal_hold_permits`` 对受保护
     操作恒 False，无紧急绕过通道）。
  4. **解除**：由独立人工 FK（``released_by_user_id NOT NULL``）+ 原因 + 时间记录；范围历史
     不删除（``legal_hold_scopes`` 保留）。
  5. **Purge 四条件**：hold 已解除 ∧ retention 届满 ∧ 主体具 ``retention.purge`` 能力 ∧ 无悬空
     活动 EvidenceRef → 授权清理并保留不可变墓碑（``evidence_tombstones``）；否则 delta=0。

本服务是 Legal Hold 的唯一权威判定源；``UnifiedGraphBuilder`` 是唯一图构造器（design §4.4），
不得由任何单表闭包替代。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.capability_guard import CapabilityGuard
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.role_capability_contract import (
    Capability,
    LEGAL_HOLD_PROTECTED_OPERATIONS,
    SERVICE_IDENTITY,
    is_permitted,
    legal_hold_permits,
)
from app.services.evidence_governance.unified_graph_builder import (
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    UnifiedGraphBuilder,
    normalize_node_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# Node key helpers — bridge between UnifiedGraph "type:id" keys and the
# legal_hold_scopes (node_type, node_id) column pair.
# ─────────────────────────────────────────────────────────────────────────────


def split_node_key(node_key: str) -> tuple[str, str]:
    """Split a normalized ``"{type}:{id}"`` key into ``(node_type, node_id)``.

    Only the FIRST ``:`` separates type from id; ids may themselves contain ``:``
    (e.g. ACNR URIs ``acnr:WP:D2:...``).
    """
    parts = node_key.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"invalid node key: {node_key!r}")
    return parts[0], parts[1]


# ─────────────────────────────────────────────────────────────────────────────
# Pure closure freeze / new-edge monotonic protection (P26)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrozenClosure:
    """The frozen unified-graph closure for a Legal Hold.

    ``direct`` are the explicitly held seed nodes; ``transitive`` are all nodes
    reachable downstream from any seed (excluding the seeds themselves).
    """

    direct: frozenset[str]
    transitive: frozenset[str]

    @property
    def all_keys(self) -> frozenset[str]:
        return self.direct | self.transitive


def freeze_hold_closure(graph: UnifiedGraph, seed_keys: list[str]) -> FrozenClosure:
    """Freeze the direct + transitive downstream closure of ``seed_keys``.

    Uses the UnifiedGraph's BFS closure (no depth truncation, cycle-safe). The
    resulting closure is what a Legal Hold protects (design §5.5).
    """
    direct = {k for k in seed_keys if k}
    transitive: set[str] = set()
    for seed in direct:
        transitive |= graph.downstream_closure(seed)
    transitive -= direct
    return FrozenClosure(direct=frozenset(direct), transitive=frozenset(transitive))


def compute_new_edge_additions(
    protected_keys: frozenset[str] | set[str],
    graph: UnifiedGraph,
    new_edge: NormalizedEdge,
) -> frozenset[str]:
    """Nodes newly pulled into protection by ``new_edge`` (monotonic; P26).

    If the new edge's source is already protected, its target and the target's
    downstream closure become newly protected. Returns ONLY the additions not
    already protected. If the source is not protected, returns empty set —
    protection never shrinks and never spuriously grows.
    """
    if new_edge.source_key not in protected_keys:
        return frozenset()
    additions = {new_edge.target_key} | graph.downstream_closure(new_edge.target_key)
    return frozenset(additions - set(protected_keys))


# ─────────────────────────────────────────────────────────────────────────────
# Purge conditions (P27) — pure decision surface
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PurgeConditions:
    """The four independent conditions required to authorize a purge (R13.4 / P27)."""

    hold_released: bool
    retention_expired: bool
    has_purge_capability: bool
    no_dangling_active_ref: bool


@dataclass(frozen=True)
class PurgeDecision:
    """Outcome of evaluating purge conditions.

    ``delta`` is the number of physical purge effects applied: 1 when authorized
    and executed, 0 otherwise (P27 — any unmet condition ⇒ zero effect).
    """

    allowed: bool
    delta: int
    unmet: tuple[str, ...]


#: Stable unmet-condition reason codes (kept low-cardinality for metrics/audit).
PURGE_UNMET_HOLD_ACTIVE = "hold_active"
PURGE_UNMET_RETENTION = "retention_not_expired"
PURGE_UNMET_CAPABILITY = "missing_purge_capability"
PURGE_UNMET_DANGLING_REF = "dangling_active_ref"


def evaluate_purge_conditions(conditions: PurgeConditions) -> PurgeDecision:
    """Pure evaluation of the four purge conditions (P27).

    Purge is allowed IFF all four conditions hold. Any unmet condition yields
    ``allowed=False`` and ``delta=0`` (zero effect).
    """
    unmet: list[str] = []
    if not conditions.hold_released:
        unmet.append(PURGE_UNMET_HOLD_ACTIVE)
    if not conditions.retention_expired:
        unmet.append(PURGE_UNMET_RETENTION)
    if not conditions.has_purge_capability:
        unmet.append(PURGE_UNMET_CAPABILITY)
    if not conditions.no_dangling_active_ref:
        unmet.append(PURGE_UNMET_DANGLING_REF)
    allowed = not unmet
    return PurgeDecision(allowed=allowed, delta=1 if allowed else 0, unmet=tuple(unmet))


def subject_has_purge_capability(
    actor_role: str, *, actor: ActorContext | None = None
) -> bool:
    """True iff the subject has the ``retention.purge`` capability (design §2.2).

    Service Identity can never purge (``retention.purge`` is denied for the
    service row); ActorContext service always maps to the service row.
    """
    role = actor_role
    if actor is not None and actor.is_service:
        role = SERVICE_IDENTITY
    if role == SERVICE_IDENTITY:
        return False
    return is_permitted(role, Capability.retention_purge.value)


# ─────────────────────────────────────────────────────────────────────────────
# Activation / release results
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HoldActivationResult:
    legal_hold_id: uuid.UUID
    graph_watermark: str
    direct_count: int
    transitive_count: int


@dataclass
class NewEdgeResult:
    added_keys: tuple[str, ...] = field(default_factory=tuple)

    @property
    def added_count(self) -> int:
        return len(self.added_keys)


@dataclass
class PurgeResult:
    decision: PurgeDecision
    tombstone_id: uuid.UUID | None = None


# ─────────────────────────────────────────────────────────────────────────────
# RetentionLegalHoldService
# ─────────────────────────────────────────────────────────────────────────────

#: Tombstone purge-reason codes (aligned with chk_tombstone_purge_reason).
TOMBSTONE_REASON_RETENTION_EXPIRED = "retention_expired"
TOMBSTONE_REASON_MANUAL = "manual_purge"
TOMBSTONE_REASON_COMPLIANCE = "compliance_erasure"


class RetentionLegalHoldService:
    """Authoritative Legal Hold + retention purge service (design §5.5).

    All graph closures use the single ``UnifiedGraphBuilder`` (design §4.4). The
    service ``flush``es (does not ``commit``); when used standalone in tests it
    may ``commit`` via the caller. Under the facade, the facade owns the
    transaction.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        graph_builder: UnifiedGraphBuilder | None = None,
        capability_guard: CapabilityGuard | None = None,
    ) -> None:
        self._db = db
        self._builder = graph_builder or UnifiedGraphBuilder(db)
        self._caps = capability_guard or CapabilityGuard()

    # ── Activation ────────────────────────────────────────────────────────────

    async def activate_hold(
        self,
        *,
        scope: GraphScope,
        reason: str,
        actor: ActorContext,
        seed_nodes: list[tuple[str, str]],
        graph: UnifiedGraph | None = None,
    ) -> HoldActivationResult:
        """Activate a Legal Hold and freeze the unified-graph closure.

        ``seed_nodes`` are ``(node_type, node_id)`` pairs directly protected. The
        service builds the same-scope UnifiedGraph, computes their direct +
        transitive downstream closure, and persists it as ``legal_hold_scopes``.

        The activation records a ``graph_watermark`` derived from the frozen
        closure (stable, deterministic) so later verification/audit can detect
        drift.
        """
        if not reason or not reason.strip():
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE, "legal hold requires a reason"
            )
        if graph is None:
            graph = await self._builder.build(scope)

        seed_keys = [normalize_node_key(t, i) for (t, i) in seed_nodes]
        closure = freeze_hold_closure(graph, seed_keys)
        watermark = self._compute_watermark(closure)

        hold_id = uuid.uuid4()
        await self._db.execute(
            sa.text(
                "INSERT INTO legal_holds "
                "(id, project_id, audit_year, reason, state, graph_watermark, "
                " actor_type, actor_user_id, actor_service_identity_id) "
                "VALUES (:id, :pid, :yr, :reason, 'active', :wm, "
                " :at, :auid, :asid)"
            ),
            {
                "id": hold_id,
                "pid": str(scope.project_id),
                "yr": scope.audit_year,
                "reason": reason,
                "wm": watermark,
                "at": actor.actor_type.value,
                "auid": str(actor.actor_user_id) if actor.actor_user_id else None,
                "asid": (
                    str(actor.actor_service_identity_id)
                    if actor.actor_service_identity_id
                    else None
                ),
            },
        )

        await self._insert_scope_rows(
            hold_id, scope, closure.direct, "direct"
        )
        await self._insert_scope_rows(
            hold_id, scope, closure.transitive, "transitive"
        )
        await self._db.flush()

        return HoldActivationResult(
            legal_hold_id=hold_id,
            graph_watermark=watermark,
            direct_count=len(closure.direct),
            transitive_count=len(closure.transitive),
        )

    async def _insert_scope_rows(
        self,
        hold_id: uuid.UUID,
        scope: GraphScope,
        keys: frozenset[str],
        scope_kind: str,
    ) -> None:
        for key in sorted(keys):
            node_type, node_id = split_node_key(key)
            await self._db.execute(
                sa.text(
                    "INSERT INTO legal_hold_scopes "
                    "(id, legal_hold_id, project_id, audit_year, node_type, node_id, "
                    " scope_kind, is_active) "
                    "VALUES (:id, :hid, :pid, :yr, :nt, :nid, :sk, true)"
                ),
                {
                    "id": uuid.uuid4(),
                    "hid": hold_id,
                    "pid": str(scope.project_id),
                    "yr": scope.audit_year,
                    "nt": node_type,
                    "nid": node_id,
                    "sk": scope_kind,
                },
            )

    @staticmethod
    def _compute_watermark(closure: FrozenClosure) -> str:
        from app.services.evidence_governance.frozen_contracts import content_hash_of

        return content_hash_of(
            {
                "direct": sorted(closure.direct),
                "transitive": sorted(closure.transitive),
            }
        )

    # ── New-edge monotonic protection ──────────────────────────────────────────

    async def register_new_edge(
        self,
        *,
        scope: GraphScope,
        new_edge: NormalizedEdge,
        graph: UnifiedGraph | None = None,
    ) -> NewEdgeResult:
        """Monotonically extend active hold scope when a new edge appears (P26).

        For each active hold in the scope: if the new edge's source is already
        protected, the edge's target and its downstream closure are added as
        ``transitive`` scope. Protection never shrinks.
        """
        active_holds = await self._active_hold_ids(scope)
        if not active_holds:
            return NewEdgeResult()

        if graph is None:
            graph = await self._builder.build(scope)

        all_added: set[str] = set()
        for hold_id in active_holds:
            protected = await self._protected_keys(hold_id)
            additions = compute_new_edge_additions(protected, graph, new_edge)
            if not additions:
                continue
            await self._insert_scope_rows(
                hold_id, scope, frozenset(additions), "transitive"
            )
            all_added |= set(additions)

        if all_added:
            await self._db.flush()
        return NewEdgeResult(added_keys=tuple(sorted(all_added)))

    async def _active_hold_ids(self, scope: GraphScope) -> list[uuid.UUID]:
        result = await self._db.execute(
            sa.text(
                "SELECT id FROM legal_holds "
                "WHERE project_id = :pid AND state = 'active' "
                "AND (audit_year = :yr OR (audit_year IS NULL AND :yr IS NULL))"
            ),
            {"pid": str(scope.project_id), "yr": scope.audit_year},
        )
        return [row[0] for row in result.fetchall()]

    async def _protected_keys(self, hold_id: uuid.UUID) -> frozenset[str]:
        result = await self._db.execute(
            sa.text(
                "SELECT node_type, node_id FROM legal_hold_scopes "
                "WHERE legal_hold_id = :hid AND is_active = true"
            ),
            {"hid": str(hold_id)},
        )
        return frozenset(
            normalize_node_key(row[0], row[1]) for row in result.fetchall()
        )

    # ── Zero-effect enforcement (P26) ──────────────────────────────────────────

    async def is_node_under_active_hold(
        self, *, project_id: uuid.UUID, node_type: str, node_id: str
    ) -> bool:
        """True iff the node is within an active hold's frozen closure."""
        key = normalize_node_key(node_type, node_id)
        nt, nid = split_node_key(key)
        result = await self._db.execute(
            sa.text(
                "SELECT 1 FROM legal_hold_scopes lhs "
                "JOIN legal_holds lh ON lh.id = lhs.legal_hold_id "
                "WHERE lhs.project_id = :pid AND lhs.node_type = :nt "
                "AND lhs.node_id = :nid AND lhs.is_active = true "
                "AND lh.state = 'active' LIMIT 1"
            ),
            {"pid": str(project_id), "nt": nt, "nid": nid},
        )
        return result.scalar() is not None

    async def authorize_destructive(
        self,
        *,
        actor_role: str,
        operation: str,
        project_id: uuid.UUID,
        node_type: str,
        node_id: str,
        actor: ActorContext | None = None,
    ) -> None:
        """Enforce zero-effect for delete/purge/overwrite under an active hold.

        Raises ``LEGAL_HOLD_ACTIVE`` (HTTP 423, destructive delta=0) for ANY
        actor — no role, admin, Service Identity or emergency grant can bypass
        (R13.2 / P26). Non-protected operations and non-held nodes pass through.
        """
        if operation not in LEGAL_HOLD_PROTECTED_OPERATIONS:
            return
        active = await self.is_node_under_active_hold(
            project_id=project_id, node_type=node_type, node_id=node_id
        )
        # Delegate the actual (actor-independent) decision to the CapabilityGuard,
        # which consults legal_hold_permits (always False for protected ops).
        self._caps.authorize_destructive_under_hold(
            actor_role, operation, hold_active=active, actor=actor
        )

    # ── Release ─────────────────────────────────────────────────────────────────

    async def release_hold(
        self,
        *,
        legal_hold_id: uuid.UUID,
        released_by_user_id: uuid.UUID,
        release_reason: str,
        actor: ActorContext,
    ) -> None:
        """Release a Legal Hold (R13.3).

        Requires an independent human FK (``released_by_user_id NOT NULL``),
        reason and time. Service Identity may never release a hold. Scope history
        is retained (``legal_hold_scopes`` rows are NOT deleted). After release,
        retention-not-expired still blocks purge.
        """
        if actor.is_service:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Service Identity 不得解除 Legal Hold",
            )
        if released_by_user_id is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                "hold release requires released_by_user_id",
            )
        if not release_reason or not release_reason.strip():
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                "hold release requires a reason",
            )
        result = await self._db.execute(
            sa.text(
                "UPDATE legal_holds SET state = 'released', "
                "released_by_user_id = :uid, released_at = now(), "
                "release_reason = :reason, updated_at = now() "
                "WHERE id = :id AND state = 'active'"
            ),
            {
                "uid": str(released_by_user_id),
                "reason": release_reason,
                "id": str(legal_hold_id),
            },
        )
        if result.rowcount == 0:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                "legal hold not active or not found",
            )
        await self._db.flush()

    # ── Purge (P27) ───────────────────────────────────────────────────────────

    async def has_dangling_active_ref(
        self, *, project_id: uuid.UUID, node_type: str, node_id: str
    ) -> bool:
        """True iff an active EvidenceRef still points to the node (P27).

        Checks both the typed evidence target (``evidence_type``/``evidence_id``)
        and, for attachment versions, the ``attachment_version_id`` link.
        """
        result = await self._db.execute(
            sa.text(
                "SELECT 1 FROM evidence_refs "
                "WHERE project_id = :pid AND status = 'active' "
                "AND ((evidence_type = :nt AND evidence_id = :nid) "
                "     OR attachment_version_id::text = :nid) LIMIT 1"
            ),
            {"pid": str(project_id), "nt": node_type, "nid": node_id},
        )
        return result.scalar() is not None

    async def evaluate_purge(
        self,
        *,
        project_id: uuid.UUID,
        node_type: str,
        node_id: str,
        actor_role: str,
        retention_expired: bool,
        actor: ActorContext | None = None,
    ) -> PurgeDecision:
        """Gather the four purge conditions from the DB and evaluate them (P27)."""
        under_hold = await self.is_node_under_active_hold(
            project_id=project_id, node_type=node_type, node_id=node_id
        )
        dangling = await self.has_dangling_active_ref(
            project_id=project_id, node_type=node_type, node_id=node_id
        )
        conditions = PurgeConditions(
            hold_released=not under_hold,
            retention_expired=retention_expired,
            has_purge_capability=subject_has_purge_capability(
                actor_role, actor=actor
            ),
            no_dangling_active_ref=not dangling,
        )
        return evaluate_purge_conditions(conditions)

    async def purge(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        node_type: str,
        node_id: str,
        actor_role: str,
        actor: ActorContext,
        retention_expired: bool,
        purged_by_user_id: uuid.UUID,
        purge_reason: str = TOMBSTONE_REASON_RETENTION_EXPIRED,
        content_hash: str | None = None,
        retention_policy_version: str | None = None,
        metadata_redacted: dict[str, Any] | None = None,
    ) -> PurgeResult:
        """Authorize and effect a purge (P27).

        Zero-effect unless all four conditions hold. On authorization, records an
        immutable tombstone (``evidence_tombstones``) and returns ``delta=1``.
        Otherwise returns ``delta=0`` with NO side effects (no tombstone, no
        physical purge).

        NOTE: This method produces the immutable tombstone and authorizes the
        physical erase; the actual byte erase is delegated to the owning engine
        (attachment/OCR/etc.) by the caller once ``decision.allowed`` is True.
        """
        decision = await self.evaluate_purge(
            project_id=project_id,
            node_type=node_type,
            node_id=node_id,
            actor_role=actor_role,
            retention_expired=retention_expired,
            actor=actor,
        )
        if not decision.allowed:
            return PurgeResult(decision=decision, tombstone_id=None)

        tombstone_id = uuid.uuid4()
        await self._db.execute(
            sa.text(
                "INSERT INTO evidence_tombstones "
                "(id, original_object_type, original_object_id, project_id, audit_year, "
                " purge_reason, purged_by_user_id, metadata_redacted, content_hash, "
                " retention_policy_version) "
                "VALUES (:id, :ot, :oid, :pid, :yr, :reason, :uid, "
                " CAST(:meta AS JSONB), :chash, :rpv)"
            ),
            {
                "id": tombstone_id,
                "ot": node_type,
                "oid": node_id,
                "pid": str(project_id),
                "yr": audit_year,
                "reason": purge_reason,
                "uid": str(purged_by_user_id),
                "meta": _json_or_none(metadata_redacted),
                "chash": content_hash,
                "rpv": retention_policy_version,
            },
        )
        await self._db.flush()
        return PurgeResult(decision=decision, tombstone_id=tombstone_id)


def _json_or_none(obj: dict[str, Any] | None) -> str | None:
    if obj is None:
        return None
    import json

    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


__all__ = [
    "RetentionLegalHoldService",
    "FrozenClosure",
    "freeze_hold_closure",
    "compute_new_edge_additions",
    "PurgeConditions",
    "PurgeDecision",
    "evaluate_purge_conditions",
    "subject_has_purge_capability",
    "split_node_key",
    "HoldActivationResult",
    "NewEdgeResult",
    "PurgeResult",
    "PURGE_UNMET_HOLD_ACTIVE",
    "PURGE_UNMET_RETENTION",
    "PURGE_UNMET_CAPABILITY",
    "PURGE_UNMET_DANGLING_REF",
    "TOMBSTONE_REASON_RETENTION_EXPIRED",
    "TOMBSTONE_REASON_MANUAL",
    "TOMBSTONE_REASON_COMPLIANCE",
]
