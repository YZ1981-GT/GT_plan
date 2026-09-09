"""Materialized guidance inventory snapshots (Task 5).

Catalog vs runtime are separate scopes. Snapshots are immutable once written;
readers use latest pointer + digest-addressed bounded cache. Request paths must
NOT rescan the whole catalog — they load a snapshot by digest/pointer.

Stage accounting (design §4):

    gross_required = complete ⊎ pending ⊎ blocked ⊎ valid_exempted
    effective_required = gross_required - valid_exempted
    PASS ⇔ complete == effective_required ∧ pending == ∅ ∧ blocked == ∅

platform_guidance_health reflects the *latest* runtime snapshot only; it never
mutates a historical C1/C2 milestone run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4

from app.services.guidance_inventory import (
    GuidanceInventoryEntry,
    RuntimeGuidanceInventory,
    RuntimeGuidanceInventoryEntry,
    build_static_guidance_inventory,
    stable_digest,
)

__all__ = [
    "CatalogEntryKey",
    "RuntimeEntryKey",
    "GuidanceInventorySnapshot",
    "StageAccounting",
    "PlatformGuidanceHealth",
    "SnapshotStore",
    "get_snapshot_store",
    "reset_snapshot_store_for_tests",
    "build_catalog_snapshot",
    "build_runtime_snapshot_from_inventory",
    "compute_stage_accounting",
    "evaluate_platform_guidance_health",
    "map_runtime_entry_bucket",
]

SnapshotScope = Literal["catalog", "runtime"]
StageBucket = Literal["complete", "pending", "blocked", "valid_exempted", "out_of_scope"]
HealthStatus = Literal["HEALTHY", "DEGRADED", "BLOCKED"]


@dataclass(frozen=True)
class CatalogEntryKey:
    template_lineage_id: str
    template_version_id: str
    wp_code: str
    sheet_uid: str | None


@dataclass(frozen=True)
class RuntimeEntryKey:
    organization_id: str
    project_id: str
    wp_id: str
    entry_id: str
    sheet_uid: str | None


@dataclass(frozen=True)
class StageAccounting:
    gross_required: frozenset[str]
    effective_required: frozenset[str]
    complete: frozenset[str]
    pending: frozenset[str]
    blocked: frozenset[str]
    valid_exempted: frozenset[str]
    out_of_scope: frozenset[str]
    counters: Mapping[str, int]
    pass_: bool = field(metadata={"alias": "pass"})

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "gross_required": sorted(self.gross_required),
            "effective_required": sorted(self.effective_required),
            "complete": sorted(self.complete),
            "pending": sorted(self.pending),
            "blocked": sorted(self.blocked),
            "valid_exempted": sorted(self.valid_exempted),
            "out_of_scope": sorted(self.out_of_scope),
            "counters": dict(self.counters),
            "pass": self.pass_,
        }


@dataclass(frozen=True)
class GuidanceInventorySnapshot:
    run_id: str
    scope: SnapshotScope
    cutoff_at: str
    input_digests: Mapping[str, str]
    entries: tuple[Any, ...]
    inventory_digest: str
    stage_accounting: StageAccounting
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "scope": self.scope,
            "cutoff_at": self.cutoff_at,
            "input_digests": dict(self.input_digests),
            "entries": list(self.entries),
            "inventory_digest": self.inventory_digest,
            "stage_accounting": self.stage_accounting.to_public_dict(),
        }


@dataclass(frozen=True)
class PlatformGuidanceHealth:
    status: HealthStatus
    latest_runtime_digest: str | None
    reason_codes: tuple[str, ...]
    c2_reevaluation_requested: bool
    evaluated_at: str


def map_runtime_entry_bucket(entry: RuntimeGuidanceInventoryEntry) -> StageBucket:
    """Map a runtime inventory entry into a stage-accounting bucket."""
    if not entry.required:
        return "out_of_scope"

    stale = tuple(entry.stale_reasons or ())
    exemption_errors = tuple(s for s in stale if s.startswith("exemption_"))
    if entry.exemption is not None and not exemption_errors and entry.exact_status != "invalid":
        return "valid_exempted"

    if entry.exact_status == "exact":
        return "complete"
    if entry.exact_status in ("invalid", "stale"):
        return "blocked"
    return "pending"


def _map_catalog_entry_bucket(entry: GuidanceInventoryEntry) -> StageBucket:
    required = bool(getattr(entry, "required", True))
    status = str(getattr(entry, "exact_status", "missing") or "missing")
    if not required:
        return "out_of_scope"
    if status == "exact":
        return "complete"
    if status in ("invalid", "stale"):
        return "blocked"
    return "pending"


def compute_stage_accounting(entry_buckets: Mapping[str, StageBucket]) -> StageAccounting:
    buckets: dict[StageBucket, set[str]] = {
        "complete": set(),
        "pending": set(),
        "blocked": set(),
        "valid_exempted": set(),
        "out_of_scope": set(),
    }
    for entry_id, bucket in entry_buckets.items():
        buckets[bucket].add(entry_id)

    complete = frozenset(buckets["complete"])
    pending = frozenset(buckets["pending"])
    blocked = frozenset(buckets["blocked"])
    valid_exempted = frozenset(buckets["valid_exempted"])
    out_of_scope = frozenset(buckets["out_of_scope"])

    seen: set[str] = set()
    for part in (complete, pending, blocked, valid_exempted):
        overlap = seen & part
        if overlap:
            raise ValueError(
                f"illegal three-axis overlap in stage accounting: {sorted(overlap)[:5]}"
            )
        seen |= set(part)

    gross_required = frozenset(seen)
    effective_required = frozenset(gross_required - valid_exempted)
    passed = complete == effective_required and not pending and not blocked
    counters = {
        "gross_required": len(gross_required),
        "effective_required": len(effective_required),
        "complete": len(complete),
        "pending": len(pending),
        "blocked": len(blocked),
        "valid_exempted": len(valid_exempted),
        "out_of_scope": len(out_of_scope),
    }
    return StageAccounting(
        gross_required=gross_required,
        effective_required=effective_required,
        complete=complete,
        pending=pending,
        blocked=blocked,
        valid_exempted=valid_exempted,
        out_of_scope=out_of_scope,
        counters=counters,
        pass_=passed,
    )


def _snapshot_digest(
    *,
    scope: SnapshotScope,
    cutoff_at: str,
    input_digests: Mapping[str, str],
    entry_payloads: Sequence[Mapping[str, Any]],
    accounting: StageAccounting,
) -> str:
    return stable_digest(
        {
            "scope": scope,
            "cutoff_at": cutoff_at,
            "input_digests": dict(sorted(input_digests.items())),
            "entries": list(entry_payloads),
            "stage_accounting": accounting.to_public_dict(),
        }
    )


def build_catalog_snapshot(
    *,
    static_entries: Sequence[GuidanceInventoryEntry] | None = None,
    template_lineage_id: str = "lineage:standard",
    template_version_id: str = "version:active",
    cutoff_at: datetime | None = None,
    run_id: str | None = None,
    extra_input_digests: Mapping[str, str] | None = None,
) -> GuidanceInventorySnapshot:
    """Materialize an immutable catalog snapshot from static inventory entries."""
    entries = tuple(
        static_entries if static_entries is not None else build_static_guidance_inventory()
    )
    cutoff = (cutoff_at or datetime.now(UTC)).isoformat()
    buckets: dict[str, StageBucket] = {}
    keyed: list[dict[str, Any]] = []
    for entry in entries:
        wp = str(getattr(entry, "parent_wp_code", "") or getattr(entry, "wp_code", "") or "")
        sheet_uid = getattr(entry, "sheet_uid", None)
        if sheet_uid is None:
            sheet_uid = getattr(entry, "sheet_code", None)
        key = CatalogEntryKey(
            template_lineage_id=template_lineage_id,
            template_version_id=template_version_id,
            wp_code=wp,
            sheet_uid=str(sheet_uid) if sheet_uid is not None else None,
        )
        entry_id = (
            f"catalog:{key.template_lineage_id}:{key.template_version_id}:"
            f"{key.wp_code}:{key.sheet_uid or 'whole'}"
        )
        bucket = _map_catalog_entry_bucket(entry)
        buckets[entry_id] = bucket
        entry_digest = getattr(entry, "entry_digest", None) or stable_digest(
            {
                "wp": wp,
                "sheet": key.sheet_uid,
                "status": getattr(entry, "exact_status", None),
            }
        )
        keyed.append(
            {
                "entry_id": entry_id,
                "key": asdict(key),
                "bucket": bucket,
                "exact_status": getattr(entry, "exact_status", None),
                "entry_digest": entry_digest,
            }
        )
    accounting = compute_stage_accounting(buckets)
    input_digests = {
        "static_entries": stable_digest([row["entry_digest"] for row in keyed]),
        "template_lineage_id": template_lineage_id,
        "template_version_id": template_version_id,
        **dict(extra_input_digests or {}),
    }
    digest = _snapshot_digest(
        scope="catalog",
        cutoff_at=cutoff,
        input_digests=input_digests,
        entry_payloads=keyed,
        accounting=accounting,
    )
    return GuidanceInventorySnapshot(
        run_id=run_id or str(uuid4()),
        scope="catalog",
        cutoff_at=cutoff,
        input_digests=input_digests,
        entries=tuple(keyed),
        inventory_digest=digest,
        stage_accounting=accounting,
    )


def build_runtime_snapshot_from_inventory(
    inventory: RuntimeGuidanceInventory,
    *,
    organization_id: str,
    project_id: str,
    wp_id: str,
    cutoff_at: datetime | None = None,
    run_id: str | None = None,
    extra_input_digests: Mapping[str, str] | None = None,
) -> GuidanceInventorySnapshot:
    """Project a RuntimeGuidanceInventory into an immutable runtime snapshot."""
    cutoff = (cutoff_at or datetime.now(UTC)).isoformat()
    buckets: dict[str, StageBucket] = {}
    keyed: list[dict[str, Any]] = []
    for entry in inventory.entries:
        key = RuntimeEntryKey(
            organization_id=organization_id,
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry.entry_id,
            sheet_uid=entry.sheet_code,
        )
        bucket = map_runtime_entry_bucket(entry)
        buckets[entry.entry_id] = bucket
        keyed.append(
            {
                "entry_id": entry.entry_id,
                "key": asdict(key),
                "bucket": bucket,
                "exact_status": entry.exact_status,
                "required": entry.required,
                "entry_digest": entry.entry_digest,
                "stale_reasons": list(entry.stale_reasons),
            }
        )
    accounting = compute_stage_accounting(buckets)
    input_digests = {
        "runtime_facts_digest": inventory.facts_digest,
        "organization_id": organization_id,
        "project_id": project_id,
        "wp_id": wp_id,
        **dict(extra_input_digests or {}),
    }
    digest = _snapshot_digest(
        scope="runtime",
        cutoff_at=cutoff,
        input_digests=input_digests,
        entry_payloads=keyed,
        accounting=accounting,
    )
    return GuidanceInventorySnapshot(
        run_id=run_id or inventory.run_id or str(uuid4()),
        scope="runtime",
        cutoff_at=cutoff,
        input_digests=input_digests,
        entries=tuple(keyed),
        inventory_digest=digest,
        stage_accounting=accounting,
    )


def evaluate_platform_guidance_health(
    latest: GuidanceInventorySnapshot | None,
    *,
    now: datetime | None = None,
) -> PlatformGuidanceHealth:
    """Continuous health over the latest *runtime* snapshot only."""
    evaluated_at = (now or datetime.now(UTC)).isoformat()
    if latest is None or latest.scope != "runtime":
        return PlatformGuidanceHealth(
            status="BLOCKED",
            latest_runtime_digest=None,
            reason_codes=("runtime_snapshot_missing",),
            c2_reevaluation_requested=True,
            evaluated_at=evaluated_at,
        )
    acct = latest.stage_accounting
    if acct.blocked:
        return PlatformGuidanceHealth(
            status="BLOCKED",
            latest_runtime_digest=latest.inventory_digest,
            reason_codes=("blocked_entries_present",),
            c2_reevaluation_requested=True,
            evaluated_at=evaluated_at,
        )
    if acct.pending or not acct.pass_:
        return PlatformGuidanceHealth(
            status="DEGRADED",
            latest_runtime_digest=latest.inventory_digest,
            reason_codes=("pending_or_incomplete",),
            c2_reevaluation_requested=True,
            evaluated_at=evaluated_at,
        )
    return PlatformGuidanceHealth(
        status="HEALTHY",
        latest_runtime_digest=latest.inventory_digest,
        reason_codes=(),
        c2_reevaluation_requested=False,
        evaluated_at=evaluated_at,
    )


class SnapshotStore:
    """Digest-addressed bounded cache + latest pointer per scope."""

    def __init__(self, *, max_entries: int = 32) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max = max_entries
        self._by_digest: dict[str, GuidanceInventorySnapshot] = {}
        self._latest: dict[SnapshotScope, str] = {}
        self._order: list[str] = []
        self._lock = RLock()

    def put(self, snapshot: GuidanceInventorySnapshot) -> GuidanceInventorySnapshot:
        with self._lock:
            existing = self._by_digest.get(snapshot.inventory_digest)
            if existing is not None:
                self._latest[snapshot.scope] = snapshot.inventory_digest
                return existing
            self._by_digest[snapshot.inventory_digest] = snapshot
            self._latest[snapshot.scope] = snapshot.inventory_digest
            self._order.append(snapshot.inventory_digest)
            self._evict()
            return snapshot

    def get(self, digest: str) -> GuidanceInventorySnapshot | None:
        with self._lock:
            return self._by_digest.get(digest)

    def latest(self, scope: SnapshotScope) -> GuidanceInventorySnapshot | None:
        with self._lock:
            dig = self._latest.get(scope)
            return self._by_digest.get(dig) if dig else None

    def _evict(self) -> None:
        protected = set(self._latest.values())
        guard = 0
        while len(self._by_digest) > self._max and self._order and guard < self._max * 2:
            guard += 1
            candidate = self._order.pop(0)
            if candidate in protected:
                self._order.append(candidate)
                if set(self._order) <= protected:
                    break
                continue
            self._by_digest.pop(candidate, None)


_STORE: SnapshotStore | None = None
_STORE_LOCK = RLock()


def get_snapshot_store() -> SnapshotStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = SnapshotStore()
        return _STORE


def reset_snapshot_store_for_tests() -> None:
    global _STORE
    with _STORE_LOCK:
        _STORE = SnapshotStore()
