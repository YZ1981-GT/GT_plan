#!/usr/bin/env python
"""Promote high-confidence unmapped_sections into canonical nine-section keys.

Policy (T7-safe):
* Only move real existing body text — never invent content or source_refs.
* Title → key via ``infer_section_key`` only (expanded aliases).
* Skip when target key already present (keep unmapped for human merge).
* Refresh migration digests; leave empty source_refs as [].

Usage:
  python backend/scripts/fix/promote_unmapped_guidance_sections.py --check
  python backend/scripts/fix/promote_unmapped_guidance_sections.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.guidance_inventory import (  # noqa: E402
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    infer_section_key,
    section_content,
    stable_digest,
)

# Reuse migrate digest projection (same directory).
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "migrate_guidance_canonical_schema",
    Path(__file__).with_name("migrate_guidance_canonical_schema.py"),
)
assert _spec and _spec.loader
_migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migrate)
_canonical_body_payload = _migrate._canonical_body_payload

CANONICAL_TITLES = {
    "purpose": "编制目的",
    "materials": "资料准备",
    "data_sources": "数据来源",
    "steps": "编制步骤",
    "formulas": "公式与逻辑",
    "judgments": "项目判断",
    "evidence": "证据与索引",
    "common_errors": "常见错误",
    "completion": "完成标准",
}

REPORT = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T07-promote-unmapped-report.json"
)


def _canonical_body_digest(document: dict[str, Any]) -> str:
    return stable_digest(_canonical_body_payload(document))


def repair_migration_meta(document: dict[str, Any]) -> dict[str, Any]:
    """Recompute counts/digest after structural edits (idempotent)."""
    out = dict(document)
    sections = [s for s in (out.get("sections") or []) if isinstance(s, dict)]
    remaining = [s for s in (out.get("unmapped_sections") or []) if isinstance(s, dict)]
    migration = dict(out.get("migration") or {})
    migration["canonical_section_count"] = len(sections)
    migration["unmapped_section_count"] = len(remaining)
    migration["canonical_body_digest"] = _canonical_body_digest(out)
    out["migration"] = migration
    if remaining:
        out["unmapped_sections"] = remaining
    else:
        out.pop("unmapped_sections", None)
    return out


def promote_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    sections = [dict(s) for s in (document.get("sections") or []) if isinstance(s, dict)]
    present = {
        str(s.get("key") or "").strip()
        for s in sections
        if str(s.get("key") or "").strip() in CANONICAL_SECTION_KEYS
    }
    remaining: list[dict[str, Any]] = []
    moves: list[dict[str, str]] = []

    for raw in document.get("unmapped_sections") or []:
        if not isinstance(raw, dict):
            remaining.append(raw)
            continue
        title = str(raw.get("title") or raw.get("heading") or "").strip()
        body = section_content(raw)
        key = infer_section_key(title)
        if not key or not body or key in present:
            remaining.append(raw)
            continue
        section = {
            "key": key,
            "title": title or CANONICAL_TITLES[key],
            "content": body,
            "source_refs": list(raw.get("source_refs") or []),
            "promoted_from_unmapped": True,
            "source_index": raw.get("source_index"),
        }
        sections.append(section)
        present.add(key)
        moves.append({"key": key, "title": title})

    if not moves:
        return document, []

    order = {k: i for i, k in enumerate(CANONICAL_SECTION_KEYS)}
    sections.sort(key=lambda s: order.get(str(s.get("key") or ""), 999))

    out = dict(document)
    out["sections"] = sections
    if remaining:
        out["unmapped_sections"] = remaining
    else:
        out.pop("unmapped_sections", None)

    migration = dict(out.get("migration") or {})
    migration["kind"] = "unmapped_promoted"
    migration["version"] = int(migration.get("version") or 2)
    if moves:
        migration["promoted_keys"] = sorted(
            set(list(migration.get("promoted_keys") or []) + [m["key"] for m in moves])
        )
    out["migration"] = migration
    return repair_migration_meta(out), moves


def run(*, apply: bool, repair_only: bool = False) -> dict[str, Any]:
    changed_files: list[dict[str, Any]] = []
    promoted_total = 0
    repaired = 0
    for path in sorted(GUIDANCE_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        if repair_only:
            after = repair_migration_meta(raw)
            moves = []
            if after.get("migration") == raw.get("migration") and after.keys() == raw.keys():
                # still rewrite if digest string differed inside migration
                if json.dumps(after, sort_keys=True) == json.dumps(raw, sort_keys=True):
                    continue
            repaired += 1
        else:
            after, moves = promote_document(raw)
            if not moves:
                # still repair digests on already-promoted docs
                if str((raw.get("migration") or {}).get("kind") or "") == "unmapped_promoted":
                    fixed = repair_migration_meta(raw)
                    if json.dumps(fixed.get("migration"), sort_keys=True) != json.dumps(
                        raw.get("migration"), sort_keys=True
                    ):
                        after = fixed
                        repaired += 1
                    else:
                        continue
                else:
                    continue
            else:
                promoted_total += len(moves)
        changed_files.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "wp_code": after.get("wp_code"),
                "moves": moves,
            }
        )
        if apply:
            path.write_text(
                json.dumps(after, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return {
        "mode": "apply" if apply else "check",
        "repairOnly": repair_only,
        "filesChanged": len(changed_files),
        "sectionsPromoted": promoted_total,
        "digestsRepaired": repaired,
        "files": changed_files,
        "policy": "no_invented_body_or_source_refs",
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--repair-digests", action="store_true")
    args = ap.parse_args()

    if args.repair_digests:
        report = run(apply=True, repair_only=True)
    else:
        report = run(apply=args.apply)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"mode={report['mode']} filesChanged={report['filesChanged']} "
        f"sectionsPromoted={report['sectionsPromoted']} "
        f"digestsRepaired={report.get('digestsRepaired', 0)} report={REPORT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
