"""把同时通过 runtime probe 与 representation 预检的 pending entry 写入 overlay。

批准集合严格取 `runtime_ready ∩ already_consistent`。单独通过 adapter/contract 注册、
但冻结结构或 ``_GT_SYNC`` 坐标漂移的条目必须保持 pending。该动作只终裁静态
capability 并登记两份 evidence；browser/OnlyOffice acceptance 仍为空，不得据此宣称
bidirectional_verified。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OVERLAY_PATH = ROOT / "backend/data/workpaper_sync_entry_overlay.json"
MANIFEST_PATH = ROOT / "backend/data/workpaper_sync_entry_manifest.json"
RUNTIME_EVIDENCE_PATH = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
    "evidence/phase4-pending-runtime-adjudication-batch1.json"
)
PREFLIGHT_EVIDENCE_PATH = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
    "evidence/phase4-representation-preflight.json"
)
RUNTIME_EVIDENCE_REF = str(RUNTIME_EVIDENCE_PATH.relative_to(ROOT)).replace("\\", "/")
PREFLIGHT_EVIDENCE_REF = str(PREFLIGHT_EVIDENCE_PATH.relative_to(ROOT)).replace("\\", "/")
_MANAGED_RUNTIME_EVIDENCE_REFS = frozenset({
    RUNTIME_EVIDENCE_REF,
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
    "evidence/phase4-pending-runtime-readiness.json",
})
PRECEDENCE = (
    "GtOnlyOfficeSheet", "OnlyOfficeWordDialog", "WorkpaperWordEditor",
    "WorkpaperSyncEditorHost",
)


class ApplyAdjudicationError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ApplyAdjudicationError(f"JSON root must be object: {path}")
    return value


def primary_component(entry: dict[str, Any]) -> str:
    components = {str(row.get("component") or "") for row in entry.get("mounts") or []}
    for component in PRECEDENCE:
        if component in components:
            return component
    raise ApplyAdjudicationError(
        f"entry {entry['entry_id']} has no supported physical mount component"
    )


def expected_rows() -> list[dict[str, Any]]:
    manifest = load(MANIFEST_PATH)
    runtime_evidence = load(RUNTIME_EVIDENCE_PATH)
    preflight_evidence = load(PREFLIGHT_EVIDENCE_PATH)
    if preflight_evidence.get("mode") != "check":
        raise ApplyAdjudicationError(
            "representation preflight must be a read-only --check report"
        )

    by_id = {str(row["entry_id"]): row for row in manifest["entries"]}
    preflight_by_id = {
        str(row["entry_id"]): row for row in preflight_evidence.get("entries") or []
    }
    runtime_ready = [
        row
        for row in runtime_evidence.get("results") or []
        if row.get("verdict") == "runtime_ready"
    ]
    missing_preflight = sorted(
        str(row["entry_id"])
        for row in runtime_ready
        if str(row["entry_id"]) not in preflight_by_id
    )
    if missing_preflight:
        raise ApplyAdjudicationError(
            "runtime-ready entries missing representation preflight: "
            + ", ".join(missing_preflight)
        )

    rows = []
    for result in runtime_ready:
        entry_id = str(result["entry_id"])
        if preflight_by_id[entry_id].get("state") != "already_consistent":
            continue
        entry = by_id.get(entry_id)
        already_applied = (
            entry is not None
            and entry.get("capability") == "bidirectional"
            and entry.get("adapter_id") == result.get("adapter_id")
        )
        if entry is None or (entry.get("capability") is not None and not already_applied):
            raise ApplyAdjudicationError(
                f"runtime-ready entry {entry_id} is absent or has a conflicting terminal verdict"
            )
        if entry.get("html_counterpart_verdict") != "exists":
            raise ApplyAdjudicationError(
                f"runtime-ready entry {entry_id} lacks an HTML counterpart"
            )
        rows.append({
            "file_glob": entry["host_path"],
            "component": primary_component(entry),
            "html_store": (
                entry["html_store"]
                if entry.get("html_store") not in {None, "", "unresolved"}
                else "projection_contract"
            ),
            "canonical_resolver": "workpaper_sync_published_representation",
            "adapter_id": result["adapter_id"],
            "capability": "bidirectional",
            "migration_state": "adapter_registered",
            "reason": (
                f"{entry_id} 同时通过 {RUNTIME_EVIDENCE_REF} 的 provider/bundle/"
                f"contract/registry 判据与 {PREFLIGHT_EVIDENCE_REF} 的冻结结构及"
                " _GT_SYNC 坐标一致性判据；真实 OnlyOffice required scenarios 仍待执行。"
            ),
            "evidence_patch": {
                "review_status": "runtime_registration_verified",
                "contract_test": RUNTIME_EVIDENCE_REF,
                "representation_preflight": PREFLIGHT_EVIDENCE_REF,
                "browser_case": None,
                "legacy_reasons": ["real_onlyoffice_acceptance_pending"],
            },
        })
    if not rows:
        raise ApplyAdjudicationError(
            "runtime-ready and representation-consistent intersection is empty"
        )
    return sorted(rows, key=lambda row: (row["file_glob"], row["component"]))


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("file_glob") or ""), str(row.get("component") or "")


def _is_managed_runtime_row(row: dict[str, Any]) -> bool:
    contract_test = str(
        (row.get("evidence_patch") or {}).get("contract_test") or ""
    )
    return contract_test in _MANAGED_RUNTIME_EVIDENCE_REFS


def check(overlay: dict[str, Any], expected: list[dict[str, Any]]) -> list[str]:
    actual = {row_key(row): row for row in overlay.get("overrides") or []}
    expected_by_key = {row_key(row): row for row in expected}
    errors = []
    for key, row in expected_by_key.items():
        if key not in actual:
            errors.append(f"missing override {key}")
        elif actual[key] != row:
            errors.append(f"drifted override {key}")
    unexpected = sorted(
        row_key(row)
        for row in overlay.get("overrides") or []
        if _is_managed_runtime_row(row) and row_key(row) not in expected_by_key
    )
    errors.extend(f"unsafe stale runtime override {key}" for key in unexpected)
    return errors


def apply(overlay: dict[str, Any], expected: list[dict[str, Any]]) -> dict[str, Any]:
    expected_keys = {row_key(row) for row in expected}
    original = list(overlay.get("overrides") or [])
    removed = [
        row
        for row in original
        if _is_managed_runtime_row(row) and row_key(row) not in expected_keys
    ]
    overrides = [
        row
        for row in original
        if not (_is_managed_runtime_row(row) and row_key(row) not in expected_keys)
    ]
    by_key = {row_key(row): index for index, row in enumerate(overrides)}
    for row in expected:
        key = row_key(row)
        if key in by_key:
            existing = overrides[by_key[key]]
            if existing != row:
                same_adjudication = all(
                    existing.get(field) == row.get(field)
                    for field in ("file_glob", "component", "adapter_id", "capability")
                )
                old_ref = str(
                    (existing.get("evidence_patch") or {}).get("contract_test") or ""
                )
                if same_adjudication and old_ref in _MANAGED_RUNTIME_EVIDENCE_REFS:
                    overrides[by_key[key]] = row
                else:
                    raise ApplyAdjudicationError(
                        f"existing reviewed override differs for {key}; manual re-review required"
                    )
            continue
        overrides.append(row)
    overlay["overrides"] = overrides
    note = (
        f"2026-11-01 runtime pending 双判据更正：{len(expected)} 条 entry 同时通过 "
        f"{RUNTIME_EVIDENCE_REF} 与 {PREFLIGHT_EVIDENCE_REF} 后终裁 capability；"
        f"撤回 {len(removed)} 条仅通过 registry probe、但 representation 不自洽的旧裁决；"
        "browser evidence 仍为空。"
    )
    basis = str(overlay.get("review_basis") or "")
    if note not in basis:
        overlay["review_basis"] = f"{basis} || {note}" if basis else note
    return overlay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        overlay = load(OVERLAY_PATH)
        expected = expected_rows()
        errors = check(overlay, expected)
        if args.check:
            if errors:
                print("[FAIL] " + "; ".join(errors))
                return 1
            print(f"[OK] runtime-ready overrides={len(expected)}")
            return 0
        updated = apply(overlay, expected)
        OVERLAY_PATH.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"[OK] applied runtime-ready overrides={len(expected)}")
        return 0
    except ApplyAdjudicationError as exc:
        print(f"[FAIL] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
