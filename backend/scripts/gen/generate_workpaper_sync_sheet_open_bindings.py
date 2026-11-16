"""生成 Sheet → published sync entry 的显式绑定清单。

Usage from repository root::

    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --apply
    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --check

本生成器只把当前 manifest 的 source-backed 事实投影为待审核 binding；它不会在运行时
读取模板目录、按 sheet 名猜父级编码，也不会把 `xlsx-sheet/*` 伪造进 manifest。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "backend" / "data"
MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
ADJUDICATION = DATA / "workpaper_sync_entry_wp_code_adjudication.json"
OUTPUT = DATA / "workpaper_sync_sheet_open_bindings.json"
SCHEMA_VERSION = "sheet-open-binding:v1"
STATUSES = {"pending", "ready", "migrated", "draining", "retired", "out_of_scope"}
MAPPING_KINDS = {"exact", "provider", "whole_workbook", "ambiguous", "out_of_scope"}


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), digest_bytes(raw)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_digest(path: Path) -> str | None:
    return digest_bytes(path.read_bytes()) if path.is_file() else None


def mount_text(entry: dict[str, Any]) -> str:
    return canonical_json(entry.get("mounts") or [])


def has_whole_workbook_marker(entry: dict[str, Any]) -> bool:
    text = mount_text(entry).lower()
    return any(marker in text for marker in ("whole-workbook", "whole_workbook", "wholeworkbook"))


def binding_for(entry: dict[str, Any], *, input_digest: str) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "").strip()
    effective_id = str(entry.get("effective_entry_id") or entry_id).strip()
    document_type = str(entry.get("document_type") or "").strip()
    wp_match = entry.get("wp_match") or {}
    wp_patterns = [str(x).strip() for x in (wp_match.get("wp_code_patterns") or []) if str(x).strip()]
    sheet_literals = [str(x).strip() for x in (wp_match.get("sheet_literals") or []) if str(x).strip()]
    sheet_expressions = [str(x).strip() for x in (wp_match.get("sheet_expressions") or []) if str(x).strip()]
    source_host = str(wp_match.get("source_host") or entry.get("host_path") or "").strip() or None

    if document_type != "xlsx":
        kind = "out_of_scope"
        status = "out_of_scope"
        reason = "document_type_out_of_scope"
        scope = "out_of_scope"
    elif has_whole_workbook_marker(entry):
        kind = "whole_workbook"
        status = "pending"
        reason = "whole_workbook_target_requires_reviewed_binding"
        scope = "whole_workbook"
    elif len(sheet_literals) == 1 and len(wp_patterns) == 1:
        kind = "exact"
        status = "pending"
        reason = "exact_candidate_requires_published_artifact_review"
        scope = "single_sheet"
    elif sheet_expressions or wp_patterns:
        kind = "provider"
        status = "pending"
        reason = "runtime_sheet_name_requires_provider_binding"
        scope = "single_sheet"
    else:
        kind = "ambiguous"
        status = "pending"
        reason = "sheet_target_not_declared"
        scope = "single_sheet"

    row: dict[str, Any] = {
        "entry_id": entry_id,
        "effective_entry_id": effective_id,
        "source_wp_code": wp_patterns[0] if len(wp_patterns) == 1 else None,
        "document_scope": scope,
        "target_sheet": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "sheet_key": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "mapping_kind": kind,
        "status": status,
        "reason": reason,
        "manifest_entry_digest": digest_bytes(canonical_json(entry).encode("utf-8")),
        "source_refs": [source_host] if source_host else [],
        "owner": None,
        "input_digest": input_digest,
        "independent_entry": bool(entry.get("independent_entry", False)),
        "document_type": document_type,
        "capability": entry.get("capability"),
        "wp_code_patterns": wp_patterns,
        "sheet_expressions": sheet_expressions,
        "sheet_literals": sheet_literals,
    }
    binding_material = {k: v for k, v in row.items() if k != "binding_id"}
    row["binding_id"] = "sha256:" + digest_bytes(canonical_json(binding_material).encode("utf-8"))
    return row


def build() -> dict[str, Any]:
    manifest, manifest_digest = read_json(MANIFEST)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise RuntimeError("manifest 缺少 entries 数组")
    overlay_digest = source_digest(OVERLAY)
    adjudication_digest = source_digest(ADJUDICATION)
    input_material = {
        "manifest_digest": manifest_digest,
        "overlay_digest": overlay_digest,
        "adjudication_digest": adjudication_digest,
        "schema_version": SCHEMA_VERSION,
    }
    input_digest = digest_bytes(canonical_json(input_material).encode("utf-8"))
    rows = [binding_for(dict(entry), input_digest=input_digest) for entry in manifest["entries"]]
    rows.sort(key=lambda row: (row["entry_id"], row["effective_entry_id"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "manifest": str(MANIFEST.relative_to(REPO)).replace("\\", "/"),
            "manifest_digest": manifest_digest,
            "overlay": str(OVERLAY.relative_to(REPO)).replace("\\", "/"),
            "overlay_digest": overlay_digest,
            "adjudication": str(ADJUDICATION.relative_to(REPO)).replace("\\", "/"),
            "adjudication_digest": adjudication_digest,
        },
        "input_digest": input_digest,
        "summary": {"entry_count": len(rows), "status_counts": counts},
        "bindings": rows,
    }


def render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render(build())
    current = OUTPUT.read_bytes() if OUTPUT.is_file() else None
    if args.check:
        if current != expected:
            print(f"[FAIL] {OUTPUT}: generated binding projection is stale or missing")
            return 1
        print(f"[OK] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
        return 0
    OUTPUT.write_bytes(expected)
    print(f"[APPLIED] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
