"""生成底稿双向回写的当前静态事实投影。

报告只描述 source/manifest/contract/provider/deletion-plan 的静态事实；数据库中的
current representation、运行时注册与真实 OO evidence 在 Phase 2/6 接入前明确记为
``unknown``，不得由代码文件存在性推断成功。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
MANIFEST = BACKEND / "data/workpaper_sync_entry_manifest.json"
OVERLAY = BACKEND / "data/workpaper_sync_entry_overlay.json"
DELETION_PLAN = BACKEND / "data/workpaper_sync_task66_legacy_deletion_plan.json"
OUTPUT = BACKEND / "data/workpaper_sync_current_state.json"
SPEC = ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")


class CurrentStateError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise CurrentStateError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CurrentStateError(f"JSON root must be an object: {path}")
    return value


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_report() -> dict[str, Any]:
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
        build_manifest_registration_plan,
    )
    from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

    manifest = load(MANIFEST)
    overlay = load(OVERLAY)
    entries = list(manifest.get("entries") or [])
    if not entries:
        raise CurrentStateError("manifest entry denominator is empty")
    by_id = manifest_entries_by_id(manifest)
    plan = build_manifest_registration_plan(by_id)
    plan_by_id = {item.entry_id: item for item in plan}
    ledger_by_id = {
        str(row["entry_id"]): row for row in DELIVERED_PER_ENTRY_CONTRACTS
    }
    if len(ledger_by_id) != len(DELIVERED_PER_ENTRY_CONTRACTS):
        raise CurrentStateError("delivered contract ledger has duplicate entry_id")

    rows: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: item["entry_id"]):
        entry_id = str(entry["entry_id"])
        plan_item = plan_by_id[entry_id]
        ledger = ledger_by_id.get(entry_id)
        rows.append({
            "entry_id": entry_id,
            "effective_entry_id": entry["effective_entry_id"],
            "independent_entry": bool(entry["independent_entry"]),
            "parent_entry_id": entry["parent_entry_id"],
            "document_type": entry["document_type"],
            "host_path": entry["host_path"],
            "capability": entry["capability"],
            "adjudication_state": entry["adjudication_state"],
            "capability_target": entry.get("capability_target"),
            "capability_target_blocked_by": entry.get("capability_target_blocked_by") or [],
            "html_counterpart_verdict": entry["html_counterpart_verdict"],
            "adapter_id": entry["adapter_id"],
            "migration_state": entry["migration_state"],
            "contract_id": None if ledger is None else ledger.get("contract_id"),
            "provider_module": None if ledger is None else ledger.get("provider_module"),
            "static_registration_blocked_reason": plan_item.blocked_reason,
            "runtime_readiness": "unknown",
            "acceptance_state": "unknown",
        })

    independent = [row for row in rows if row["independent_entry"]]
    capability_counts = Counter(
        row["capability"] for row in independent if row["capability"] is not None
    )
    counterpart_counts = Counter(
        str(row["html_counterpart_verdict"]) for row in independent
    )
    deletion = load(DELETION_PLAN) if DELETION_PLAN.is_file() else {}
    report: dict[str, Any] = {
        "schema_version": "workpaper-sync-current-state:v1",
        "snapshot_date": str(overlay.get("source_reviewed_at") or "unknown"),
        "spec": SPEC,
        "source_review_ref": overlay.get("source_review_ref"),
        "source_digest": manifest.get("source_digest"),
        "manifest_digest": manifest.get("manifest_digest"),
        "overlay_digest": manifest.get("overlay_digest"),
        "adjudication_source_digest": manifest.get("adjudication_source_digest"),
        "wp_code_adjudication_digest": manifest.get("wp_code_adjudication_digest"),
        "counts": {
            "entries": len(rows),
            "independent": len(independent),
            "parent_duplicates": sum(row["parent_entry_id"] is not None for row in rows),
            "pending": sum(row["capability"] is None for row in independent),
            "capabilities": dict(sorted(capability_counts.items())),
            "counterparts": dict(sorted(counterpart_counts.items())),
            "legacy_fake_bidirectional": sum(
                row["migration_state"] == "legacy_fake_bidirectional" for row in independent
            ),
            "declared_adapters": sum(bool(row["adapter_id"]) for row in independent),
            "delivered_contracts": len(ledger_by_id),
            "statically_registrable": sum(
                item.blocked_reason is None for item in plan if by_id[item.entry_id].get("independent_entry")
            ),
        },
        "runtime_scope": {
            "database_queried": False,
            "onlyoffice_queried": False,
            "meaning": "runtime_readiness/acceptance_state are unknown, not failed or passed",
        },
        "deletion_plan": {
            "available": bool(deletion),
            "sha256": None if not deletion else digest(deletion),
        },
        "entries": rows,
    }
    report["report_digest"] = digest(report)
    return report


def render(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report()
        expected = render(report)
    except CurrentStateError as exc:
        print(f"[FAIL] {exc}")
        return 2
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else None
        if actual != expected:
            print(f"[FAIL] stale current-state projection: {OUTPUT.relative_to(ROOT)}")
            return 1
        print(f"[OK] current-state projection {report['report_digest'][:16]}")
        return 0
    atomic_write(OUTPUT, expected)
    counts = report["counts"]
    print(
        f"[OK] wrote {OUTPUT.relative_to(ROOT)} entries={counts['entries']} "
        f"independent={counts['independent']} pending={counts['pending']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
