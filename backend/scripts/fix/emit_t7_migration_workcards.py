#!/usr/bin/env python
"""Emit Task 7 migration work cards from catalog / static inventory.

Does NOT invent nine-section body text. Cards list identity, missing sections,
source_ref gaps, and unmapped section titles for human review → publication.

Usage:
  python backend/scripts/fix/emit_t7_migration_workcards.py
  python backend/scripts/fix/emit_t7_migration_workcards.py --limit 50
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.guidance_inventory import (  # noqa: E402
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    build_static_guidance_inventory,
)
from app.services.guidance_inventory_snapshots import (  # noqa: E402
    build_catalog_snapshot,
)

OUT_DIR = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T07-workcards"
)


def _load_document(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _card_for_entry(entry: Any, doc: dict[str, Any] | None) -> dict[str, Any] | None:
    status = str(getattr(entry, "exact_status", "missing") or "missing")
    if status == "exact":
        return None  # already closed for catalog exact gate
    missing = list(getattr(entry, "missing_sections", ()) or ())
    unmapped: list[str] = []
    mapped_keys: list[str] = []
    if doc:
        for sec in doc.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            key = str(sec.get("key") or "").strip()
            title = str(sec.get("title") or sec.get("heading") or "").strip()
            if key in CANONICAL_SECTION_KEYS:
                mapped_keys.append(key)
            elif title:
                unmapped.append(title)
        for sec in doc.get("unmapped_sections") or []:
            if isinstance(sec, dict):
                title = str(sec.get("title") or sec.get("heading") or "").strip()
                if title:
                    unmapped.append(title)
    refs_empty = []
    if doc:
        for sec in doc.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            key = str(sec.get("key") or "").strip()
            if key in CANONICAL_SECTION_KEYS:
                refs = sec.get("source_refs") or []
                if not refs:
                    refs_empty.append(key)

    return {
        "wp_code": getattr(entry, "wp_code", None),
        "path": getattr(entry, "path", None),
        "exact_status": status,
        "source_ref_status": getattr(entry, "source_ref_status", None),
        "missing_sections": missing,
        "mapped_canonical_keys": sorted(set(mapped_keys)),
        "unmapped_section_titles": unmapped,
        "sections_missing_source_refs": refs_empty,
        "reason": getattr(entry, "reason", None),
        "next_actions": [
            "review_unmapped_titles_into_canonical_keys",
            "attach_SourceRef_via_registry",
            "submit_candidate_then_independent_publication",
            "do_not_autofill_generic_boilerplate",
        ],
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="max cards (0=all incomplete)")
    args = ap.parse_args()

    entries = build_static_guidance_inventory()
    snap = build_catalog_snapshot(static_entries=entries)
    cards: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(str(getattr(entry, "path", "") or ""))
        if not path.is_absolute():
            # inventory paths may be relative to repo or GUIDANCE_DIR
            candidates = [
                ROOT / path,
                GUIDANCE_DIR / path.name,
                Path(str(getattr(entry, "path", ""))),
            ]
            path = next((p for p in candidates if p.is_file()), path)
        doc = _load_document(path) if path.is_file() else None
        card = _card_for_entry(entry, doc)
        if card is None:
            continue
        cards.append(card)
        if args.limit and len(cards) >= args.limit:
            break

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    recorded = datetime.now(UTC).isoformat()
    summary = {
        "task": 7,
        "recordedAt": recorded,
        "catalogRunId": snap.run_id,
        "catalogDigest": snap.inventory_digest,
        "stageAccounting": {
            "counters": dict(snap.stage_accounting.counters),
            "pass": bool(snap.stage_accounting.pass_),
        },
        "workcardCount": len(cards),
        "staticEntryCount": len(entries),
        "policy": "no_generic_autofill",
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "workcards.json").write_text(
        json.dumps({"recordedAt": recorded, "cards": cards}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "INDEX.md").write_text(
        "\n".join(
            [
                "# T07 Migration Work Cards",
                "",
                f"**Cards:** {len(cards)} / static entries {len(entries)}",
                f"**Catalog digest:** `{snap.inventory_digest}`",
                f"**Accounting:** {json.dumps(snap.stage_accounting.to_public_dict(), ensure_ascii=False)}",
                "",
                "Cards list gaps only — reviewers must supply real nine-section content + SourceRefs.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        f"T7 workcards={len(cards)} "
        f"pending={snap.stage_accounting.counters.get('pending')} "
        f"blocked={snap.stage_accounting.counters.get('blocked')} "
        f"complete={snap.stage_accounting.counters.get('complete')}"
    )
    print(f"out={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
