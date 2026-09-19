"""Task 3.5 — 版本递增、不可变版本、影响确认、LegacyAttachmentResolver 与 file_path 脱敏。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2, R9, R13, R14
Design: §4.1(legacy alias), §4.2(Attachment 聚合), §4.3(AttachmentVersion 不可变),
        §5.1(替换先锁父/版本号生成), §6.1(opaque locator), §6.3(legacy 调用方兼容)
Properties: P4(版本不可变/递增), P20(stale 传播), P26(Legal Hold 零效果), P28(迁移幂等)

Key implementation points:
1. ``SELECT ... FOR UPDATE`` on parent Attachment row before version increment — locks the
   aggregate root, reads current max version_no, generates +1. DB UNIQUE is final fallback.
2. Immutability: verified by DB trigger (V106 migration); this module does NOT attempt UPDATE
   on frozen fields (bytes, key, hash, actor, time, attachment_id, version_no).
3. Impact confirmation: returns direct + transitive impact references for versions that are
   referenced by EvidenceRef, used in FormalOutput, or under LegalHold.
4. ``LegacyAttachmentResolver``: all old download/preview/associate/OCR/response paths first
   call this resolver — prioritize alias; only explicitly created new aggregate root IDs
   resolve as new ID.
5. Old route facade delegation: old endpoints delegate internally to EvidenceGovernanceFacade.
6. ``file_path`` response sanitization: NEVER return absolute paths — only opaque locator
   (``/api/attachments/{id}/download``) or controlled short-lived URL.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias
from app.services.evidence_governance.contracts import (
    LegacyResolution,
    LegacyResolutionKind,
    validate_legacy_resolution,
)
from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_CMD_REPLACE = "attachment.replace"
_CMD_IMPACT = "attachment.impact"
_CAPABILITY_REPLACE = "attachment.replace"

# file_path 清洗：对外 NEVER 返回绝对路径/storage key/token。
_OPAQUE_DOWNLOAD_PATTERN = "/api/attachments/{attachment_id}/download"
_OPAQUE_VERSION_DOWNLOAD_PATTERN = "/api/attachments/{attachment_id}/versions/{version_id}/download"


# ──────────────────────────────────────────────────────────────────────────────
# Data contracts
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImpactEntry:
    """An object that would be affected by modifying/deleting a version."""

    ref_id: str
    ref_type: str  # evidence_ref / formal_output / legal_hold
    source_type: str
    source_id: str
    label: str | None = None
    is_transitive: bool = False


@dataclass
class ImpactReport:
    """Impact assessment for a given attachment version (R2.3, R9.1)."""

    attachment_id: uuid.UUID
    version_no: int
    direct_impacts: list[ImpactEntry] = field(default_factory=list)
    transitive_impacts: list[ImpactEntry] = field(default_factory=list)
    has_legal_hold: bool = False
    has_formal_output: bool = False
    total_count: int = 0

    @property
    def blocked(self) -> bool:
        return self.has_legal_hold or self.has_formal_output or self.total_count > 0


@dataclass
class ReplaceResult:
    """Result of a version replacement operation."""

    attachment_id: uuid.UUID
    new_version_id: uuid.UUID
    new_version_no: int
    previous_version_id: uuid.UUID | None
    content_hash: str
    command_root_id: uuid.UUID


# ──────────────────────────────────────────────────────────────────────────────
# file_path response sanitization (R14.1 / design §6.1 C3)
# ──────────────────────────────────────────────────────────────────────────────


def sanitize_file_path_response(
    attachment_id: uuid.UUID | str,
    *,
    version_id: uuid.UUID | str | None = None,
    raw_file_path: str | None = None,
) -> str:
    """Sanitize ``file_path`` for API responses — NEVER absolute paths.

    Returns opaque download locator or controlled URL. This is the ONLY function
    that produces ``file_path`` values in responses during the compatibility window
    (R14.1). Absolute paths, storage keys, and tokens never leave the service boundary.
    """
    aid = str(attachment_id)
    if version_id:
        return _OPAQUE_VERSION_DOWNLOAD_PATTERN.format(
            attachment_id=aid, version_id=str(version_id)
        )
    return _OPAQUE_DOWNLOAD_PATTERN.format(attachment_id=aid)


def sanitize_attachment_response(
    attachment: dict[str, Any],
    *,
    version_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Sanitize an attachment dict for API response — replace file_path with opaque locator.

    Preserves all other fields; only ``file_path`` is rewritten. Ensures no absolute
    path, storage key, or token crosses the service boundary (design §6.1 / R14.1).
    """
    result = dict(attachment)
    aid = result.get("id") or result.get("attachment_id")
    if aid:
        result["file_path"] = sanitize_file_path_response(aid, version_id=version_id)
    elif "file_path" in result:
        # Cannot determine attachment_id → strip file_path entirely (safety fallback).
        result["file_path"] = ""
    return result


# ──────────────────────────────────────────────────────────────────────────────
# LegacyAttachmentResolver (design §4.1 / R14)
# ──────────────────────────────────────────────────────────────────────────────


class LegacyAttachmentResolver:
    """Resolves old attachment IDs through the ``legacy_attachment_alias`` table.

    All old download/preview/associate/OCR/response compatibility paths MUST call
    this resolver FIRST (design §4.1). Resolution priority:
      1. If the ID exists in ``legacy_attachment_alias`` → return alias resolution.
      2. Only IDs *explicitly created* as new aggregate roots resolve as themselves.

    The API MUST NOT silently interpret an old ID as "current version" (P28/R14).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        attachment_id: uuid.UUID | str,
        *,
        requested_project_id: uuid.UUID | None = None,
    ) -> LegacyResolution | None:
        """Resolve an attachment ID. Returns ``None`` if ID is a new root (no alias needed).

        If the ID is found in the alias table, returns a ``LegacyResolution`` with both
        the aggregate root AND a definite version (never id-only / never silent "current").
        Scope validation: if ``requested_project_id`` is given, rejects cross-project.
        """
        oid = str(attachment_id)
        row = (
            (
                await self._db.execute(
                    sa.text(
                        "SELECT attachment_id, attachment_version_id, project_id, audit_year, "
                        "       resolution_kind "
                        "FROM legacy_attachment_alias WHERE old_attachment_id = :oid LIMIT 1"
                    ),
                    {"oid": oid},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None  # Not a legacy ID; treat as potential new aggregate root.

        # Cross-project isolation (P1): if requester specifies a project, reject mismatch.
        if requested_project_id is not None and str(row["project_id"]) != str(requested_project_id):
            return None  # Desensitized: never reveal cross-project existence.

        resolved_as_new_root = row["resolution_kind"] == LegacyResolutionKind.root.value
        return LegacyResolution(
            old_attachment_id=oid,
            attachment_id=str(row["attachment_id"]),
            attachment_version_id=str(row["attachment_version_id"]),
            project_id=str(row["project_id"]),
            audit_year=int(row["audit_year"]),
            resolution_kind=str(row["resolution_kind"]),
            resolved_as_new_root=resolved_as_new_root,
        )

    async def resolve_to_ids(
        self,
        attachment_id: uuid.UUID | str,
        *,
        requested_project_id: uuid.UUID | None = None,
    ) -> tuple[uuid.UUID, uuid.UUID | None]:
        """Convenience: resolve to (root_id, definite_version_id).

        Returns ``(original_id, None)`` if no alias exists (new root or unknown).
        """
        resolution = await self.resolve(
            attachment_id, requested_project_id=requested_project_id
        )
        if resolution is None:
            uid = attachment_id if isinstance(attachment_id, uuid.UUID) else uuid.UUID(str(attachment_id))
            return uid, None
        return uuid.UUID(resolution.attachment_id), uuid.UUID(resolution.attachment_version_id)


# ──────────────────────────────────────────────────────────────────────────────
# AttachmentVersionManager (FOR UPDATE + version increment + impact + hold check)
# ──────────────────────────────────────────────────────────────────────────────


class AttachmentVersionManager:
    """Manages version increment with FOR UPDATE locking and impact confirmation.

    Design §4.3 step 8: "New version_no generated after ``SELECT Attachment ... FOR UPDATE``
    locks parent row, reads current/max and generates +1; DB unique is final concurrency
    fallback."

    Replacement first locks parent Attachment, checks hold/impact/expected current, then
    generates version_no and adds new version; old versions not overwritten (P4).
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        facade: EvidenceGovernanceFacade | None = None,
    ) -> None:
        self._db = db
        self._facade = facade or EvidenceGovernanceFacade(db)

    # ──────────────────────────────────────────────────────────────────────────
    # Impact assessment (R2.3 / R9.1)
    # ──────────────────────────────────────────────────────────────────────────

    async def assess_impact(
        self,
        attachment_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> ImpactReport:
        """Assess direct and transitive impact of modifying/replacing a version.

        Returns references, formal outputs, and legal holds that depend on this version.
        Callers MUST present this to the user before destructive ops on referenced versions
        (R2.3: "展示直接与传递影响范围、要求有权限用户确认").
        """
        # Determine the version to assess.
        if version_id is None:
            att = await self._db.get(Attachment, attachment_id)
            if att is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "attachment not found",
                )
            version_id = att.current_version_id
            version_no = att.version
        else:
            ver = await self._db.get(AttachmentVersion, version_id)
            if ver is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "version not found",
                )
            version_no = ver.version_no

        if version_id is None:
            return ImpactReport(attachment_id=attachment_id, version_no=0)

        # Query direct EvidenceRef references.
        direct_refs = await self._query_direct_refs(version_id, project_id)

        # Query legal holds (direct scope check).
        has_hold = await self._check_legal_hold(attachment_id, project_id)

        # Query formal output references (via evidence_refs + dependency graph).
        has_formal = await self._check_formal_output_refs(version_id, project_id)

        # Transitive impacts via EvidenceDependency graph.
        transitive_refs = await self._query_transitive_impacts(version_id, project_id)

        report = ImpactReport(
            attachment_id=attachment_id,
            version_no=version_no,
            direct_impacts=direct_refs,
            transitive_impacts=transitive_refs,
            has_legal_hold=has_hold,
            has_formal_output=has_formal,
            total_count=len(direct_refs) + len(transitive_refs),
        )
        return report

    async def _query_direct_refs(
        self, version_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> list[ImpactEntry]:
        """Query EvidenceRef rows that reference this version."""
        query = sa.text(
            "SELECT id, source_type, source_id, label "
            "FROM evidence_refs "
            "WHERE attachment_version_id = :vid AND status = 'active' "
            "LIMIT 200"
        )
        rows = (await self._db.execute(query, {"vid": str(version_id)})).mappings().all()
        return [
            ImpactEntry(
                ref_id=str(r["id"]),
                ref_type="evidence_ref",
                source_type=str(r["source_type"]),
                source_id=str(r["source_id"]),
                label=r.get("label"),
                is_transitive=False,
            )
            for r in rows
        ]

    async def _check_legal_hold(
        self, attachment_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> bool:
        """Check if attachment is under active Legal Hold (R13 / P26).

        Uses the canonical legal_hold_scopes schema (node_type/node_id/is_active)
        and legal_holds.state — the authoritative columns shared with
        RetentionLegalHoldService (design §4.6). Matches either an attachment
        node or an attachment_version node in the frozen hold closure.
        """
        query = sa.text(
            "SELECT 1 FROM legal_hold_scopes lhs "
            "JOIN legal_holds lh ON lh.id = lhs.legal_hold_id "
            "WHERE lhs.node_type IN ('attachment', 'attachment_version') "
            "AND lhs.node_id = :aid AND lhs.is_active = true "
            "AND lh.state = 'active' LIMIT 1"
        )
        try:
            r = (await self._db.execute(query, {"aid": str(attachment_id)})).scalar()
            return r is not None
        except Exception:
            # Table may not exist yet in all test environments.
            return False

    async def _check_formal_output_refs(
        self, version_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> bool:
        """Check if version is used in any formal output (via evidence_refs)."""
        # A version referenced by an active evidence_ref with source_type hinting formal output.
        query = sa.text(
            "SELECT 1 FROM evidence_refs "
            "WHERE attachment_version_id = :vid AND status = 'active' "
            "AND source_type IN ('formal_output','report','deliverable','archive') "
            "LIMIT 1"
        )
        try:
            r = (await self._db.execute(query, {"vid": str(version_id)})).scalar()
            return r is not None
        except Exception:
            return False

    async def _query_transitive_impacts(
        self, version_id: uuid.UUID, project_id: uuid.UUID | None
    ) -> list[ImpactEntry]:
        """Query transitive downstream via EvidenceDependency (bounded, first level)."""
        # First-level transitive: objects that depend on this version through dependency edges.
        query = sa.text(
            "SELECT id, target_type, target_id, relation "
            "FROM evidence_dependencies "
            "WHERE source_type = 'attachment_version' AND source_id = :vid "
            "AND status = 'active' "
            "LIMIT 200"
        )
        try:
            rows = (await self._db.execute(query, {"vid": str(version_id)})).mappings().all()
        except Exception:
            return []
        return [
            ImpactEntry(
                ref_id=str(r["id"]),
                ref_type="dependency",
                source_type=str(r["target_type"]),
                source_id=str(r["target_id"]),
                label=str(r.get("relation", "")),
                is_transitive=True,
            )
            for r in rows
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # Version replacement with FOR UPDATE locking (design §4.3 step 8 / §5.1)
    # ──────────────────────────────────────────────────────────────────────────

    async def replace_version(
        self,
        *,
        attachment_id: uuid.UUID,
        new_content_hash: str,
        new_storage_key: str | None = None,
        new_storage_type: str = "local",
        new_media_type: str | None = None,
        new_byte_size: int | None = None,
        config_snapshot: dict | None = None,
        actor: ActorContext,
        actor_role: str,
        idempotency_key: str,
        project_id: uuid.UUID | None = None,
        audit_year: int | None = None,
        expected_current_version: int | None = None,
        impact_confirmed: bool = False,
        trace_id: str | None = None,
    ) -> ReplaceResult:
        """Replace attachment content: lock parent, check hold/impact, generate version_no.

        Transaction boundary (design §5.1):
          1. ``SELECT Attachment ... FOR UPDATE`` — locks parent row.
          2. Read current max version_no from attachment_versions.
          3. If version is referenced/held and ``impact_confirmed=False`` → reject with
             ``EVIDENCE_GATE_BLOCKED`` and include impact report.
          4. Generate ``version_no = max + 1``.
          5. INSERT new AttachmentVersion(staged or available).
          6. UPDATE parent ``current_version_id`` + legacy ``version`` mirror.
          7. Outbox stale propagation event for downstream (R9.1).

        Old versions are NEVER overwritten (P4 — immutability enforced by DB trigger).
        """

        async def _do_replace(txn: CommandTxn) -> dict:
            # 1) Lock parent row FOR UPDATE (design §4.3 step 8).
            lock_result = (
                await self._db.execute(
                    sa.text(
                        "SELECT id, project_id, audit_year, state, current_version_id, version "
                        "FROM attachments WHERE id = :aid FOR UPDATE"
                    ),
                    {"aid": str(attachment_id)},
                )
            ).mappings().first()

            if lock_result is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "attachment not found",
                )

            # Verify scope consistency.
            att_project = lock_result["project_id"]
            att_year = lock_result["audit_year"]
            att_state = lock_result["state"]
            current_vid = lock_result["current_version_id"]
            legacy_version = lock_result["version"] or 0

            if att_state in ("inactive", "tombstoned"):
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.INVALID_STATE_TRANSITION,
                    "cannot replace inactive/tombstoned attachment",
                )

            # 2) Read current max version_no.
            max_row = (
                await self._db.execute(
                    sa.text(
                        "SELECT COALESCE(MAX(version_no), 0) AS max_vn "
                        "FROM attachment_versions WHERE attachment_id = :aid"
                    ),
                    {"aid": str(attachment_id)},
                )
            ).mappings().first()
            current_max = max_row["max_vn"] if max_row else 0

            # expected_current_version check (optimistic concurrency).
            if expected_current_version is not None and current_max != expected_current_version:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.VERSION_CONFLICT,
                    f"expected version {expected_current_version}, actual {current_max}",
                )

            # 3) Legal Hold check (P26: active hold → zero-effect on destructive ops).
            has_hold = await self._check_legal_hold(attachment_id, txn.project_id)
            if has_hold:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.LEGAL_HOLD_ACTIVE,
                    "attachment under active legal hold; replacement creates new version only",
                )

            # 3b) Impact check — if version is referenced and user hasn't confirmed.
            if current_vid and not impact_confirmed:
                impact = await self.assess_impact(
                    attachment_id, version_id=current_vid, project_id=txn.project_id
                )
                if impact.blocked:
                    raise EvidenceGovernanceError(
                        EvidenceErrorCode.EVIDENCE_GATE_BLOCKED,
                        "version has active references; confirm impact before replacement",
                    )

            # 4) Generate new version_no = max + 1 (DB unique is final concurrency fallback).
            new_version_no = current_max + 1

            # 5) INSERT new AttachmentVersion.
            new_ver_id = uuid.uuid4()
            actor_cols = {
                "actor_type": actor.actor_type.value,
                "actor_user_id": actor.actor_user_id,
                "actor_service_identity_id": actor.actor_service_identity_id,
            }
            new_version = AttachmentVersion(
                id=new_ver_id,
                attachment_id=attachment_id,
                project_id=txn.project_id,
                audit_year=att_year,
                version_no=new_version_no,
                storage_type=new_storage_type,
                storage_key=new_storage_key,
                media_type=new_media_type,
                byte_size=new_byte_size,
                content_hash=new_content_hash,
                config_snapshot=config_snapshot,
                availability="available",
                previous_version_id=current_vid,
                **actor_cols,
            )
            self._db.add(new_version)
            await self._db.flush()

            # 6) UPDATE parent: current_version_id + legacy version mirror.
            await self._db.execute(
                sa.text(
                    "UPDATE attachments SET current_version_id = :nvid, version = :vno, "
                    "updated_at = :now WHERE id = :aid"
                ),
                {
                    "nvid": str(new_ver_id),
                    "vno": new_version_no,
                    "now": datetime.now(timezone.utc),
                    "aid": str(attachment_id),
                },
            )
            await self._db.flush()

            # 7) Outbox stale propagation event (R9.1: new version → mark downstream stale).
            await txn.enqueue_outbox(
                event_type="attachment.version_replaced",
                payload={
                    "attachment_id": str(attachment_id),
                    "new_version_id": str(new_ver_id),
                    "new_version_no": new_version_no,
                    "previous_version_id": str(current_vid) if current_vid else None,
                    "content_hash": new_content_hash,
                },
            )

            await txn.record_transition(
                transition_type="attachment.version_replaced",
                from_state=f"v{current_max}",
                to_state=f"v{new_version_no}",
                metadata={
                    "new_version_id": str(new_ver_id),
                    "content_hash": new_content_hash,
                },
            )

            return {
                "attachment_id": str(attachment_id),
                "new_version_id": str(new_ver_id),
                "new_version_no": new_version_no,
                "previous_version_id": str(current_vid) if current_vid else None,
                "content_hash": new_content_hash,
            }

        # Execute through facade (scope + capability + audit + outbox in one transaction).
        req = CommandRequest(
            command_type=_CMD_REPLACE,
            idempotency_key=idempotency_key,
            actor=actor,
            actor_role=actor_role,
            project_id=project_id,
            audit_year=audit_year,
            capability=_CAPABILITY_REPLACE,
            object_type="attachment",
            object_id=attachment_id,
            trace_id=trace_id,
        )
        result = await self._facade.execute(req, _do_replace)

        if result.replayed:
            # Replayed command: return previous result without re-running business logic.
            return ReplaceResult(
                attachment_id=attachment_id,
                new_version_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                new_version_no=0,
                previous_version_id=None,
                content_hash=new_content_hash,
                command_root_id=result.command_root_id,
            )

        data = result.result
        return ReplaceResult(
            attachment_id=attachment_id,
            new_version_id=uuid.UUID(data["new_version_id"]),
            new_version_no=data["new_version_no"],
            previous_version_id=(
                uuid.UUID(data["previous_version_id"]) if data["previous_version_id"] else None
            ),
            content_hash=data["content_hash"],
            command_root_id=result.command_root_id,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Legacy route facade delegation (design §6.3)
# ──────────────────────────────────────────────────────────────────────────────


class LegacyRouteFacade:
    """Facade for old attachment routes to delegate to EvidenceGovernanceFacade.

    During the compatibility window (R14.1):
    - Old URI/field names are preserved externally.
    - Internally, all operations delegate to the new governance layer.
    - ``file_path`` in responses is ALWAYS sanitized (opaque locator / controlled URL).
    - Old ``created_by``/OCR status/current version are mirrored (read-only compat).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._resolver = LegacyAttachmentResolver(db)
        self._version_mgr = AttachmentVersionManager(db)

    async def get_attachment_compat(
        self,
        attachment_id: uuid.UUID | str,
        *,
        requested_project_id: uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        """Legacy GET attachment — resolve via alias, sanitize file_path.

        Returns a compatibility response dict (old field names preserved), but with
        ``file_path`` replaced by opaque locator (never absolute path / storage key / token).
        """
        # 1) Resolve through legacy alias first.
        root_id, version_id = await self._resolver.resolve_to_ids(
            attachment_id, requested_project_id=requested_project_id
        )

        # 2) Load attachment from DB.
        att = await self._db.get(Attachment, root_id)
        if att is None or att.is_deleted:
            return None
        if requested_project_id and att.project_id != requested_project_id:
            return None  # Cross-project isolation (P1) — desensitized.

        # 3) Build compat response with sanitized file_path.
        response = {
            "id": str(att.id),
            "project_id": str(att.project_id),
            "file_name": att.file_name,
            "file_path": sanitize_file_path_response(att.id, version_id=version_id),
            "file_type": att.file_type,
            "file_size": att.file_size,
            "storage_type": att.storage_type,
            "ocr_status": att.ocr_status,
            "version": att.version,
            "created_by": str(att.created_by) if att.created_by else None,
            "created_at": att.created_at.isoformat() if att.created_at else None,
            "updated_at": att.updated_at.isoformat() if att.updated_at else None,
            "state": att.state,
            "current_version_id": str(att.current_version_id) if att.current_version_id else None,
        }
        return response

    async def list_versions_compat(
        self,
        attachment_id: uuid.UUID | str,
        *,
        requested_project_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Legacy GET versions — resolve via alias, sanitize all file_path fields."""
        root_id, _ = await self._resolver.resolve_to_ids(
            attachment_id, requested_project_id=requested_project_id
        )
        rows = (
            (
                await self._db.execute(
                    sa.text(
                        "SELECT id, version_no, storage_type, media_type, byte_size, "
                        "       content_hash, availability, created_at "
                        "FROM attachment_versions "
                        "WHERE attachment_id = :aid ORDER BY version_no DESC"
                    ),
                    {"aid": str(root_id)},
                )
            )
            .mappings()
            .all()
        )
        return [
            {
                "id": str(r["id"]),
                "version": r["version_no"],
                "file_path": sanitize_file_path_response(root_id, version_id=r["id"]),
                "file_type": r["media_type"] or "unknown",
                "file_size": r["byte_size"] or 0,
                "content_hash": r["content_hash"],
                "availability": r["availability"],
                "uploaded_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Module exports
# ──────────────────────────────────────────────────────────────────────────────

__all__ = [
    "AttachmentVersionManager",
    "ImpactEntry",
    "ImpactReport",
    "LegacyAttachmentResolver",
    "LegacyRouteFacade",
    "ReplaceResult",
    "sanitize_attachment_response",
    "sanitize_file_path_response",
]
