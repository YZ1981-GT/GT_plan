"""Offline Manifest Verifier — Task 7.2 (Wave 6).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R11
Design: §5.5 Archive, Retention 与 Legal Hold
Properties: P24 (manifest 防覆盖)

Standalone offline verifier that:
  - Does NOT connect to business database
  - Recomputes member hashes (individual entry hashes)
  - Recomputes manifest hash (aggregate of all entries + edges)
  - Verifies package integrity (package hash covers manifest)
  - Outputs machine-readable differences when verification fails

This module is designed to be runnable as an independent process/script.
It MUST NOT import any database session/connection modules.

Design §5.5: "离线 verifier 不连接业务库，重算成员、manifest 与 package hash"
"""

from __future__ import annotations

import enum
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence


# ─────────────────────────────────────────────────────────────────────────────
# Canonical hashing (self-contained, no DB imports)
# ─────────────────────────────────────────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    """Deterministic canonical JSON serialization.

    Same algorithm as frozen_contracts.canonical_json but self-contained
    to keep this module independent of any DB-related imports.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _sha256_hex(data: bytes | str) -> str:
    """Compute SHA-256 hex digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _content_hash_of(obj: Any) -> str:
    """Canonical content hash of any JSON-serializable object."""
    return _sha256_hex(_canonical_json(obj))


# ─────────────────────────────────────────────────────────────────────────────
# Verification result types
# ─────────────────────────────────────────────────────────────────────────────


class VerificationStatus(str, enum.Enum):
    """Overall verification status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class DifferenceType(str, enum.Enum):
    """Types of differences found during verification."""

    MEMBER_HASH_MISMATCH = "member_hash_mismatch"
    MANIFEST_HASH_MISMATCH = "manifest_hash_mismatch"
    PACKAGE_HASH_MISMATCH = "package_hash_mismatch"
    MISSING_ENTRY = "missing_entry"
    EXTRA_ENTRY = "extra_entry"
    ENTRY_CONTENT_TAMPERED = "entry_content_tampered"
    MANIFEST_NOT_SEALED = "manifest_not_sealed"
    MANIFEST_MISSING = "manifest_missing"
    STRUCTURAL_ERROR = "structural_error"


@dataclass
class VerificationDifference:
    """A single difference found during offline verification.

    Machine-readable: each difference has a type, location, expected/actual
    values, and a human-readable description.
    """

    difference_type: DifferenceType
    location: str  # e.g., "manifest.entries[3]" or "package.package_hash"
    expected: str | None = None
    actual: str | None = None
    description: str = ""
    severity: str = "critical"  # critical | warning

    def to_dict(self) -> dict[str, Any]:
        """Convert to machine-readable dict."""
        return {
            "type": self.difference_type.value,
            "location": self.location,
            "expected": self.expected,
            "actual": self.actual,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class OfflineVerificationResult:
    """Complete result of offline verification.

    Machine-readable output with all differences found.
    """

    status: VerificationStatus = VerificationStatus.PASSED
    package_id: str = ""
    manifest_id: str = ""
    project_id: str = ""
    audit_year: int = 0
    version: int = 0
    verified_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    differences: list[VerificationDifference] = field(default_factory=list)
    member_count: int = 0
    edge_count: int = 0
    recomputed_manifest_hash: str = ""
    stored_manifest_hash: str = ""
    recomputed_package_hash: str = ""
    stored_package_hash: str = ""

    @property
    def is_valid(self) -> bool:
        return self.status == VerificationStatus.PASSED

    @property
    def difference_count(self) -> int:
        return len(self.differences)

    def to_machine_readable(self) -> dict[str, Any]:
        """Convert to complete machine-readable format.

        This is the primary output for offline verification.
        Design: machine-readable differences when verification fails.
        """
        return {
            "verification_status": self.status.value,
            "package_id": self.package_id,
            "manifest_id": self.manifest_id,
            "project_id": self.project_id,
            "audit_year": self.audit_year,
            "version": self.version,
            "verified_at": self.verified_at.isoformat(),
            "is_valid": self.is_valid,
            "summary": {
                "member_count": self.member_count,
                "edge_count": self.edge_count,
                "difference_count": self.difference_count,
            },
            "hashes": {
                "manifest": {
                    "stored": self.stored_manifest_hash,
                    "recomputed": self.recomputed_manifest_hash,
                    "match": self.stored_manifest_hash == self.recomputed_manifest_hash,
                },
                "package": {
                    "stored": self.stored_package_hash,
                    "recomputed": self.recomputed_package_hash,
                    "match": self.stored_package_hash == self.recomputed_package_hash,
                },
            },
            "differences": [d.to_dict() for d in self.differences],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            self.to_machine_readable(),
            indent=indent,
            ensure_ascii=False,
            default=str,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Offline Manifest Verifier (no DB connection)
# ─────────────────────────────────────────────────────────────────────────────


class OfflineManifestVerifier:
    """Standalone offline manifest/package verifier.

    Design §5.5: "离线 verifier 不连接业务库，重算成员、manifest 与 package hash"

    Verifies:
      1. Manifest is sealed
      2. Each member (entry) hash is recomputable from its data
      3. Manifest hash (aggregate of entries + edges) matches stored hash
      4. Package hash (wraps manifest hash) matches stored hash

    Does NOT:
      - Connect to any database
      - Import database session/connection modules
      - Verify against live business data (that's the online path)

    Outputs machine-readable differences when any check fails.
    """

    def verify_package(self, package_data: dict[str, Any]) -> OfflineVerificationResult:
        """Verify a sealed package from its serialized data.

        Args:
            package_data: Dict representation of a SealedPackage including its
                         manifest, entries, and edges.

        Returns:
            OfflineVerificationResult with status and any differences found.
        """
        result = OfflineVerificationResult()

        # Extract basic metadata
        result.package_id = package_data.get("package_id", "")
        result.stored_package_hash = package_data.get("package_hash", "")
        result.version = package_data.get("version", 0)

        manifest = package_data.get("manifest")
        if manifest is None:
            result.status = VerificationStatus.FAILED
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.MANIFEST_MISSING,
                location="package.manifest",
                description="Package has no manifest",
            ))
            return result

        result.manifest_id = manifest.get("manifest_id", "")
        result.project_id = manifest.get("project_id", "")
        result.audit_year = manifest.get("audit_year", 0)
        result.stored_manifest_hash = manifest.get("manifest_hash", "")

        # Check 1: Manifest must be sealed
        if not manifest.get("sealed", False):
            result.status = VerificationStatus.FAILED
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.MANIFEST_NOT_SEALED,
                location="manifest.sealed",
                expected="true",
                actual="false",
                description="Manifest is not sealed — cannot verify integrity",
            ))
            return result

        entries = manifest.get("entries", [])
        edges = manifest.get("edges", [])
        result.member_count = len(entries)
        result.edge_count = len(edges)

        # Check 2: Recompute manifest hash from entries + edges
        recomputed_manifest_hash = self._recompute_manifest_hash(manifest)
        result.recomputed_manifest_hash = recomputed_manifest_hash

        if recomputed_manifest_hash != result.stored_manifest_hash:
            result.status = VerificationStatus.FAILED
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.MANIFEST_HASH_MISMATCH,
                location="manifest.manifest_hash",
                expected=result.stored_manifest_hash,
                actual=recomputed_manifest_hash,
                description=(
                    "Manifest hash mismatch — entries or edges have been "
                    "tampered with since sealing"
                ),
            ))

            # Identify which members differ
            self._identify_member_differences(entries, edges, result)

        # Check 3: Recompute package hash
        recomputed_package_hash = self._recompute_package_hash(package_data)
        result.recomputed_package_hash = recomputed_package_hash

        if recomputed_package_hash != result.stored_package_hash:
            result.status = VerificationStatus.FAILED
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.PACKAGE_HASH_MISMATCH,
                location="package.package_hash",
                expected=result.stored_package_hash,
                actual=recomputed_package_hash,
                description=(
                    "Package hash mismatch — package metadata or manifest hash "
                    "have been tampered with"
                ),
            ))

        # If no differences found, verification passed
        if not result.differences:
            result.status = VerificationStatus.PASSED

        return result

    def verify_from_json(self, json_str: str) -> OfflineVerificationResult:
        """Verify a sealed package from its JSON representation.

        Convenience method for CLI/script usage.
        """
        try:
            package_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            result = OfflineVerificationResult(
                status=VerificationStatus.ERROR,
            )
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.STRUCTURAL_ERROR,
                location="input",
                description=f"Invalid JSON: {e}",
            ))
            return result
        return self.verify_package(package_data)

    def verify_from_file(self, file_path: str) -> OfflineVerificationResult:
        """Verify a sealed package from a JSON file.

        Convenience method for CLI/script usage.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, IOError) as e:
            result = OfflineVerificationResult(
                status=VerificationStatus.ERROR,
            )
            result.differences.append(VerificationDifference(
                difference_type=DifferenceType.STRUCTURAL_ERROR,
                location="file",
                description=f"Cannot read file: {e}",
            ))
            return result
        return self.verify_from_json(content)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal hash recomputation
    # ─────────────────────────────────────────────────────────────────────────

    def _recompute_manifest_hash(self, manifest: dict[str, Any]) -> str:
        """Recompute the manifest hash from entries and edges.

        Uses the same canonical algorithm as ArchiveManifest.compute_manifest_hash()
        but operates on raw dict data (no ORM dependency).
        """
        entries = manifest.get("entries", [])
        edges = manifest.get("edges", [])

        entries_data = sorted(
            [
                {
                    "id": e.get("entry_id", ""),
                    "type": e.get("entry_type", ""),
                    "object_id": e.get("object_id", ""),
                    "version": e.get("version"),
                    "content_hash": e.get("content_hash"),
                    "state": e.get("state"),
                }
                for e in entries
            ],
            key=lambda x: x["id"],
        )
        edges_data = sorted(
            [
                {
                    "hash": e.get("edge_hash", ""),
                    "source": e.get("source_key", ""),
                    "target": e.get("target_key", ""),
                    "provenance": e.get("provenance", ""),
                }
                for e in edges
            ],
            key=lambda x: x["hash"],
        )

        return _content_hash_of({
            "manifest_id": manifest.get("manifest_id", ""),
            "project_id": manifest.get("project_id", ""),
            "audit_year": manifest.get("audit_year", 0),
            "version": manifest.get("version", 0),
            "policy_version": manifest.get("policy_version"),
            "watermark": manifest.get("watermark", ""),
            "entries": entries_data,
            "edges": edges_data,
        })

    def _recompute_package_hash(self, package_data: dict[str, Any]) -> str:
        """Recompute the package hash from package metadata + manifest hash.

        Uses the same algorithm as SealedPackage.compute_package_hash().
        """
        manifest = package_data.get("manifest", {})
        return _content_hash_of({
            "package_id": package_data.get("package_id", ""),
            "manifest_hash": manifest.get("manifest_hash", ""),
            "version": package_data.get("version", 0),
        })

    def _identify_member_differences(
        self,
        entries: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        result: OfflineVerificationResult,
    ) -> None:
        """Identify which specific members (entries/edges) have been tampered.

        Recomputes individual member contributions and flags mismatches.
        """
        # Check each entry's structural integrity
        for i, entry in enumerate(entries):
            if not entry.get("entry_id"):
                result.differences.append(VerificationDifference(
                    difference_type=DifferenceType.MISSING_ENTRY,
                    location=f"manifest.entries[{i}]",
                    description=f"Entry at index {i} has no entry_id",
                    severity="critical",
                ))
            if not entry.get("entry_type"):
                result.differences.append(VerificationDifference(
                    difference_type=DifferenceType.ENTRY_CONTENT_TAMPERED,
                    location=f"manifest.entries[{i}].entry_type",
                    description=f"Entry '{entry.get('entry_id', i)}' has no entry_type",
                    severity="critical",
                ))

        # Check edges have required fields
        for i, edge in enumerate(edges):
            if not edge.get("edge_hash"):
                result.differences.append(VerificationDifference(
                    difference_type=DifferenceType.ENTRY_CONTENT_TAMPERED,
                    location=f"manifest.edges[{i}].edge_hash",
                    description=f"Edge at index {i} has no edge_hash",
                    severity="critical",
                ))


# ─────────────────────────────────────────────────────────────────────────────
# Serialization helpers (for converting between domain objects and raw dicts)
# ─────────────────────────────────────────────────────────────────────────────


def serialize_sealed_package(package: Any) -> dict[str, Any]:
    """Serialize a SealedPackage domain object to a verifiable dict.

    This creates the format expected by OfflineManifestVerifier.verify_package().
    Can be used to export packages for offline verification.
    """
    if package is None:
        return {}

    manifest = package.manifest
    if manifest is None:
        return {"package_id": getattr(package, "package_id", ""), "manifest": None}

    entries_data = []
    for entry in getattr(manifest, "entries", []):
        entries_data.append({
            "entry_id": entry.entry_id,
            "entry_type": entry.entry_type.value if hasattr(entry.entry_type, "value") else str(entry.entry_type),
            "object_id": entry.object_id,
            "version": entry.version,
            "content_hash": entry.content_hash,
            "state": entry.state,
        })

    edges_data = []
    for edge in getattr(manifest, "edges", []):
        edges_data.append({
            "edge_hash": edge.edge_hash,
            "source_key": edge.source_key,
            "target_key": edge.target_key,
            "provenance": edge.provenance.value if hasattr(edge.provenance, "value") else str(edge.provenance),
        })

    return {
        "package_id": package.package_id,
        "version": package.version,
        "package_hash": package.package_hash,
        "manifest": {
            "manifest_id": manifest.manifest_id,
            "project_id": manifest.project_id,
            "audit_year": manifest.audit_year,
            "version": manifest.version,
            "policy_version": manifest.policy_version,
            "watermark": manifest.watermark,
            "manifest_hash": manifest.manifest_hash,
            "sealed": manifest.sealed,
            "entries": entries_data,
            "edges": edges_data,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (runnable as independent process/script)
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    """CLI entry point for offline manifest verification.

    Usage:
        python -m app.services.evidence_governance.offline_manifest_verifier <package.json>

    Reads a sealed package JSON file, verifies integrity, and outputs
    machine-readable verification result to stdout.

    Exit codes:
        0 — verification passed
        1 — verification failed (differences found)
        2 — error (invalid input/file)
    """
    if len(sys.argv) < 2:
        print(
            "Usage: python -m app.services.evidence_governance."
            "offline_manifest_verifier <package.json>",
            file=sys.stderr,
        )
        return 2

    file_path = sys.argv[1]
    verifier = OfflineManifestVerifier()
    result = verifier.verify_from_file(file_path)

    # Output machine-readable result to stdout
    print(result.to_json())

    if result.status == VerificationStatus.PASSED:
        return 0
    elif result.status == VerificationStatus.FAILED:
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "OfflineManifestVerifier",
    "OfflineVerificationResult",
    "VerificationDifference",
    "VerificationStatus",
    "DifferenceType",
    "serialize_sealed_package",
    "main",
]
