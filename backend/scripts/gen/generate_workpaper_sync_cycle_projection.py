"""生成 D～N 与 A/B/C/S/共享入口的当前 manifest 投影。

历史 cycle slice 保留原调查细节；本生成器给每份 slice 注入同一个 current projection
引用，并把当前独立 entry 按 source-backed 规则一次分组写入 sidecar，避免重排数百 KB
历史 JSON 或复制十二套生成算法。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "backend/data"
MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
OUTPUT = DATA / "workpaper_sync_cycle_current_projection.json"
OUTPUT_REF = "backend/data/workpaper_sync_cycle_current_projection.json"
SCHEMA = "workpaper-sync-cycle-current-projection:v1"
SLICE_PATHS = {
    **{letter.lower(): DATA / f"workpaper_sync_{letter.lower()}_cycle_manifest_slice.json"
       for letter in "DEFGHIJKLMN"},
    "abcs": DATA / "workpaper_sync_abcs_cycle_manifest_slice.json",
}


class CycleProjectionError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise CycleProjectionError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CycleProjectionError(f"JSON root must be an object: {path}")
    return value


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def historical_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for key, path in SLICE_PATHS.items():
        document = load(path)
        entries = document.get("independent_entries")
        if not isinstance(entries, list):
            raise CycleProjectionError(f"slice has no independent_entries: {path}")
        for entry in entries:
            entry_id = str((entry or {}).get("entry_id") or "")
            if not entry_id:
                continue
            previous = owners.get(entry_id)
            if previous is not None and previous != key:
                raise CycleProjectionError(
                    f"historical slices assign {entry_id} to both {previous} and {key}"
                )
            owners[entry_id] = key
    return owners


def infer_owner(entry: dict[str, Any], existing: dict[str, str]) -> str:
    entry_id = str(entry["entry_id"])
    if entry_id in existing:
        return existing[entry_id]
    letters = {
        match.group(1).upper()
        for code in (entry.get("wp_match") or {}).get("wp_code_patterns") or []
        for match in [re.match(r"^([A-N]|S)", str(code).upper())]
        if match
    }
    if not letters:
        match = re.search(r"(?:^|/)(?:gt-)?([a-ns])\d", entry_id.lower())
        if match:
            letters.add(match.group(1).upper())
    if len(letters) == 1:
        letter = next(iter(letters))
        return "abcs" if letter in {"A", "B", "C", "S"} else letter.lower()
    # pattern-less 与真正跨循环的共享宿主统一归 Task 57 的复合 slice。
    return "abcs"


def project_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": entry["entry_id"],
        "effective_entry_id": entry["effective_entry_id"],
        "host_path": entry["host_path"],
        "document_type": entry["document_type"],
        "capability": entry["capability"],
        "adjudication_state": entry["adjudication_state"],
        "capability_verdict_stage": entry.get("capability_verdict_stage"),
        "capability_target": entry.get("capability_target"),
        "capability_target_blocked_by": entry.get("capability_target_blocked_by") or [],
        "html_counterpart_verdict": entry["html_counterpart_verdict"],
        "html_counterpart_source_refs": entry["html_counterpart_source_refs"],
        "adapter_id": entry["adapter_id"],
        "migration_state": entry["migration_state"],
        "scenario_profile_id": entry["scenario_profile"]["profile_id"],
    }


def build_projection() -> dict[str, Any]:
    manifest = load(MANIFEST)
    overlay = load(OVERLAY)
    independent = [
        entry for entry in manifest.get("entries") or [] if entry.get("independent_entry")
    ]
    if not independent:
        raise CycleProjectionError("manifest independent denominator is empty")
    old_owners = historical_owners()
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in SLICE_PATHS}
    for entry in independent:
        owner = infer_owner(entry, old_owners)
        if owner not in groups:
            raise CycleProjectionError(f"entry {entry['entry_id']} has unknown owner {owner}")
        groups[owner].append(project_entry(entry))

    seen = [row["entry_id"] for rows in groups.values() for row in rows]
    if len(seen) != len(set(seen)) or set(seen) != {
        str(entry["entry_id"]) for entry in independent
    }:
        raise CycleProjectionError("cycle grouping must cover each independent entry exactly once")

    rendered_groups: dict[str, Any] = {}
    for key, rows in groups.items():
        rows.sort(key=lambda row: row["entry_id"])
        counts = {
            "entries": len(rows),
            "pending": sum(row["capability"] is None for row in rows),
            "capabilities": dict(sorted(Counter(
                row["capability"] for row in rows if row["capability"] is not None
            ).items())),
            "counterparts": dict(sorted(Counter(
                "pending" if row["html_counterpart_verdict"] is None
                else row["html_counterpart_verdict"]
                for row in rows
            ).items())),
        }
        payload = {
            "historical_slice": str(SLICE_PATHS[key].relative_to(ROOT)).replace("\\", "/"),
            "selection": "historical entry ownership first; wp_code cycle next; pattern-less/shared to abcs",
            "counts": counts,
            "entries": rows,
        }
        payload["projection_digest"] = canonical_digest(payload)
        rendered_groups[key] = payload

    projection: dict[str, Any] = {
        "schema_version": SCHEMA,
        "snapshot_date": str(overlay.get("source_reviewed_at") or "unknown"),
        "manifest_digest": manifest.get("manifest_digest"),
        "source_digest": manifest.get("source_digest"),
        "adjudication_source_digest": manifest.get("adjudication_source_digest"),
        "wp_code_adjudication_digest": manifest.get("wp_code_adjudication_digest"),
        "independent_entry_count": len(independent),
        "groups": rendered_groups,
    }
    projection["projection_digest"] = canonical_digest(projection)
    return projection


def render(projection: dict[str, Any]) -> str:
    return json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def slice_has_pointer(path: Path) -> bool:
    document = load(path)
    return (
        document.get("current_projection_schema_version") == SCHEMA
        and document.get("current_projection_ref") == OUTPUT_REF
    )


def inject_slice_pointer(path: Path) -> None:
    if slice_has_pointer(path):
        return
    raw = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    if not raw.startswith("{" + newline):
        raise CycleProjectionError(f"unexpected JSON prefix: {path}")
    second_line = raw.split(newline, 2)[1]
    indent = second_line[: len(second_line) - len(second_line.lstrip())]
    inserted = (
        "{" + newline
        + f'{indent}"current_projection_schema_version": "{SCHEMA}",' + newline
        + f'{indent}"current_projection_ref": "{OUTPUT_REF}",' + newline
        + raw[len("{" + newline):]
    )
    # Parse before replacing the source file; malformed insertion never reaches disk.
    json.loads(inserted)
    atomic_write(path, inserted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        projection = build_projection()
        expected = render(projection)
        stale_slices = [
            str(path.relative_to(ROOT)) for path in SLICE_PATHS.values()
            if not slice_has_pointer(path)
        ]
    except CycleProjectionError as exc:
        print(f"[FAIL] {exc}")
        return 2
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else None
        if actual != expected or stale_slices:
            print("[FAIL] cycle current projection is stale")
            if actual != expected:
                print(f"  - {OUTPUT.relative_to(ROOT)}")
            for path in stale_slices:
                print(f"  - missing pointer: {path}")
            return 1
        print(f"[OK] cycle projection {projection['projection_digest'][:16]}")
        return 0
    atomic_write(OUTPUT, expected)
    for path in SLICE_PATHS.values():
        inject_slice_pointer(path)
    print(
        f"[OK] wrote {OUTPUT.relative_to(ROOT)} groups={len(SLICE_PATHS)} "
        f"entries={projection['independent_entry_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
