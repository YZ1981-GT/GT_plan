"""Canonical review thread keys + legacy migration (formula-toolbar Task 10).

Canonical wire: ``projectId/wpId/(sheetUid|whole-workbook|page)/anchorId``
Legacy wire: ``wpId:sectionId``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


KEY_VERSION = "1.0"
LEGACY_SEP = ":"


@dataclass(frozen=True)
class CanonicalReviewThreadKey:
    project_id: str
    wp_id: str
    sheet_scope: str
    anchor_id: str

    @property
    def wire(self) -> str:
        return f"{self.project_id}/{self.wp_id}/{self.sheet_scope}/{self.anchor_id}"


def build_canonical_review_thread_key(
    *,
    project_id: str,
    wp_id: str,
    anchor_id: str,
    sheet_uid: str | None = None,
    whole_workbook: bool = False,
) -> CanonicalReviewThreadKey:
    if not project_id.strip() or not wp_id.strip() or not anchor_id.strip():
        raise ValueError("project_id, wp_id, and anchor_id are required")
    if whole_workbook:
        scope = "whole-workbook"
    elif sheet_uid and sheet_uid.strip():
        scope = sheet_uid.strip()
    else:
        # Honest degradation — do not fabricate a cell identity.
        scope = "page"
    return CanonicalReviewThreadKey(
        project_id=project_id.strip(),
        wp_id=wp_id.strip(),
        sheet_scope=scope,
        anchor_id=anchor_id.strip(),
    )


def build_legacy_review_thread_key(wp_id: str, section_id: str) -> str:
    return f"{wp_id}{LEGACY_SEP}{section_id}"


def parse_legacy_review_thread_key(legacy: str) -> tuple[str, str] | None:
    if LEGACY_SEP not in legacy:
        return None
    wp_id, section_id = legacy.split(LEGACY_SEP, 1)
    if not wp_id or not section_id:
        return None
    return wp_id, section_id


MigrationStatus = Literal["mapped", "collision", "orphan", "unmapped"]


@dataclass
class MigrationRow:
    legacy_key: str
    canonical_wire: str | None
    status: MigrationStatus
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacyKey": self.legacy_key,
            "canonicalWire": self.canonical_wire,
            "status": self.status,
            "detail": self.detail,
        }


def dry_run_review_key_migration(
    *,
    project_id: str,
    legacy_keys: list[str],
    existing_canonical: list[str] | None = None,
) -> dict[str, Any]:
    existing = set(existing_canonical or [])
    rows: list[MigrationRow] = []
    target_to_legacies: dict[str, list[str]] = {}

    for legacy in legacy_keys:
        parsed = parse_legacy_review_thread_key(legacy)
        if parsed is None:
            rows.append(
                MigrationRow(legacy, None, "orphan", "unparseable legacy key"),
            )
            continue
        wp_id, section_id = parsed
        canonical = build_canonical_review_thread_key(
            project_id=project_id,
            wp_id=wp_id,
            anchor_id=section_id,
            sheet_uid=None,
        )
        target_to_legacies.setdefault(canonical.wire, []).append(legacy)
        detail = "target already exists (idempotent)" if canonical.wire in existing else "ok"
        rows.append(MigrationRow(legacy, canonical.wire, "mapped", detail))

    for wire, legacies in target_to_legacies.items():
        if len(legacies) > 1:
            for row in rows:
                if row.canonical_wire == wire:
                    row.status = "collision"
                    row.detail = f"collision among {', '.join(legacies)}"

    return {
        "dryRun": True,
        "keyVersion": KEY_VERSION,
        "scanned": len(legacy_keys),
        "mapped": sum(1 for r in rows if r.status == "mapped"),
        "collisions": sum(1 for r in rows if r.status == "collision"),
        "orphans": sum(1 for r in rows if r.status == "orphan"),
        "rows": [r.to_dict() for r in rows],
        "rollbackEvidence": [
            {"legacyKey": r.legacy_key, "previousCanonical": None}
            for r in rows
            if r.canonical_wire
        ],
    }


def apply_review_key_migration(report: dict[str, Any]) -> dict[str, Any]:
    """Idempotent apply — collisions/orphans skipped; mapped → applied."""
    if not report.get("dryRun", True):
        return report
    rows = []
    for r in report.get("rows", []):
        row = dict(r)
        if row.get("status") == "mapped" and "idempotent" not in str(row.get("detail", "")):
            row["detail"] = "applied"
        rows.append(row)
    out = dict(report)
    out["dryRun"] = False
    out["rows"] = rows
    return out
