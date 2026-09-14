"""Generate source-backed legacy dual-mode characterization for workpaper sync entries.

This is deliberately a debt baseline, not an allowlist. The generated facts record why an
entry is not yet bidirectional; `check_workpaper_sync_closure.py` remains non-zero until the
facts and manifest prove closure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_BASELINE_PATH = _REPO / "backend" / "data" / "workpaper_sync_legacy_baseline.json"
_FRONTEND_PATH = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncLegacyBaseline.generated.ts"
)

_MODE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("segmented_mode_switch", re.compile(r"<el-segmented\b", re.I)),
    ("dual_mode_component", re.compile(r"<(?:[A-Z][\w]*DualMode[\w]*|[A-Z][\w]*ModeSwitch[\w]*)\b")),
    (
        "dual_mode_state",
        re.compile(
            r"\b(?:use[A-Za-z0-9]*DualMode|dualMode|currentMode|genericViewMode|renderMode|showOO)\b"
        ),
    ),
    ("whole_excel_entry", re.compile(r"\bWHOLE_EXCEL_TAB\b")),
)
_RELOAD_PATTERN = re.compile(
    r"\b(?:reloadAll|reloadAllResponses|loadStructuredData|reloadAllSections|reload)\s*\(",
)
_MATERIALIZE_PATTERN = re.compile(
    r"(?:/workpaper-sync/.*/materialize|/sync/.*/materialize|\bmaterializeWorkpaper\s*\(|"
    r"\buseWorkpaperSyncBridge\s*\()",
)
_FORCE_SAVE_PATTERN = re.compile(
    r"(?:/workpaper-sync/.*/forcesave|/sync/.*/forcesave|\brequestForceSave\s*\(|\.forceSave\s*\()",
)
_DURABLE_ACK_PATTERN = re.compile(
    r"(?:\bcallbackAck\b|\bawaitOperationTerminal\s*\(|\bdurableAck\b|"
    r"\boperation(?:State|Status)\b[^\n]{0,100}\b(?:applied|conflict)\b)",
    re.I,
)


class LegacyBaselineError(RuntimeError):
    """Raised when the characterization cannot be produced deterministically."""


def strip_source_comments(source: str) -> str:
    """Remove Vue/JS comments before token characterization.

    This is intentionally conservative: it preserves line count so evidence line numbers stay
    useful and does not try to parse string literals. Structural mount conditions still come
    from the Vue AST manifest; text tokens are only supporting UI characterization.
    """

    def preserve_lines(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    without_html = re.sub(r"<!--[\s\S]*?-->", preserve_lines, source)
    without_blocks = re.sub(r"/\*[\s\S]*?\*/", preserve_lines, without_html)
    return re.sub(r"(?m)^\s*//.*$", "", without_blocks)


def _assert_comment_stripping() -> None:
    probe = "<!-- <el-segmented /> -->\n// dualMode\nconst live = usePilotDualMode()\n"
    stripped = strip_source_comments(probe)
    if "el-segmented" in stripped or "// dualMode" in stripped or "usePilotDualMode" not in stripped:
        raise LegacyBaselineError("strip_source_comments reverse self-check failed")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise LegacyBaselineError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LegacyBaselineError(f"JSON root must be an object: {path}")
    return value


def _source_paths(entry: dict[str, Any]) -> list[str]:
    paths = {entry["host_path"]}
    for mount in entry.get("mounts") or []:
        canonical = mount.get("canonicalComponentFile")
        if isinstance(canonical, str):
            paths.add(canonical)
    return sorted(paths)


def _read_source(relative: str) -> str:
    path = (_REPO / relative).resolve()
    try:
        path.relative_to(_REPO.resolve())
    except ValueError as exc:
        raise LegacyBaselineError(f"source path escapes repository: {relative}") from exc
    if not path.is_file():
        raise LegacyBaselineError(f"source file does not exist: {relative}")
    return path.read_text(encoding="utf-8")


def _line_evidence(source: str, pattern: re.Pattern[str], source_path: str, label: str) -> dict[str, Any] | None:
    match = pattern.search(source)
    if not match:
        return None
    line = source.count("\n", 0, match.start()) + 1
    snippet = source.splitlines()[line - 1].strip()[:180]
    return {"kind": label, "file": source_path, "line": line, "snippet": snippet}


def _entry_characterization(entry: dict[str, Any]) -> dict[str, Any]:
    sources: list[tuple[str, str]] = []
    for relative in _source_paths(entry):
        sources.append((relative, strip_source_comments(_read_source(relative))))

    mode_evidence: list[dict[str, Any]] = []
    for relative, source in sources:
        for label, pattern in _MODE_PATTERNS:
            evidence = _line_evidence(source, pattern, relative, label)
            if evidence and evidence not in mode_evidence:
                mode_evidence.append(evidence)

    mount_condition_mode = any(
        re.search(
            r"(?:dualMode|currentMode|onlyoffice|OnlyOffice|renderMode|showOO|genericViewMode)",
            str(mount.get("condition") or ""),
        )
        for mount in entry.get("mounts") or []
    )
    if mount_condition_mode:
        mount = next(
            mount
            for mount in entry["mounts"]
            if re.search(
                r"(?:dualMode|currentMode|onlyoffice|OnlyOffice|renderMode|showOO|genericViewMode)",
                str(mount.get("condition") or ""),
            )
        )
        mode_evidence.append(
            {
                "kind": "mount_condition_mode_gate",
                "file": mount["file"],
                "line": mount["sourceSpan"]["startLine"],
                "snippet": mount["condition"],
            }
        )

    joined = "\n".join(source for _, source in sources)
    has_materialize = bool(_MATERIALIZE_PATTERN.search(joined))
    has_force_save_command = bool(_FORCE_SAVE_PATTERN.search(joined))
    has_durable_ack = bool(_DURABLE_ACK_PATTERN.search(joined))
    has_reload = bool(_RELOAD_PATTERN.search(joined))
    has_adapter = bool(entry.get("adapter_id"))
    is_independent = bool(entry.get("independent_entry"))
    is_unreachable = entry.get("capability") == "unreachable"

    flags = {
        "template_only_open": is_independent and not is_unreachable and not has_materialize,
        "html_reload_only": is_independent and not is_unreachable and has_reload and not has_durable_ack,
        "no_forcesave_command": is_independent and not is_unreachable and not has_force_save_command,
        "no_durable_forcesave_ack": is_independent and not is_unreachable and not has_durable_ack,
        "missing_adapter": is_independent and not is_unreachable and not has_adapter,
        "single_mode_switch_visible": (
            is_independent
            and entry.get("capability") in {"single_html", "single_onlyoffice"}
            and bool(mode_evidence)
        ),
        "claimed_bidirectional_without_adapter": entry.get("capability") == "bidirectional" and not has_adapter,
    }
    reason_codes = sorted(name for name, value in flags.items() if value)
    return {
        "entry_id": entry["entry_id"],
        "host_path": entry["host_path"],
        "document_type": entry["document_type"],
        "capability": entry["capability"],
        "migration_state": entry["migration_state"],
        "independent_entry": is_independent,
        "source_paths": [relative for relative, _ in sources],
        "source_sha256": {
            relative: _sha256(source.encode("utf-8")) for relative, source in sources
        },
        "flags": flags,
        "reason_codes": reason_codes,
        "ui_characterization": {
            "mode_switch_visible": bool(mode_evidence),
            "evidence": sorted(mode_evidence, key=lambda item: (item["file"], item["line"], item["kind"])),
        },
    }


def build_baseline(manifest: dict[str, Any]) -> dict[str, Any]:
    _assert_comment_stripping()
    entries = [_entry_characterization(entry) for entry in manifest.get("entries") or []]
    if not entries:
        raise LegacyBaselineError("manifest entry denominator is empty")
    independent = [entry for entry in entries if entry["independent_entry"]]
    source_digest = _sha256(
        json.dumps(
            [(entry["entry_id"], entry["source_sha256"]) for entry in entries],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    stats = {
        "entry_count": len(entries),
        "independent_entry_count": len(independent),
        "template_only_open_count": sum(entry["flags"]["template_only_open"] for entry in independent),
        "html_reload_only_count": sum(entry["flags"]["html_reload_only"] for entry in independent),
        "no_forcesave_command_count": sum(entry["flags"]["no_forcesave_command"] for entry in independent),
        "no_durable_forcesave_ack_count": sum(
            entry["flags"]["no_durable_forcesave_ack"] for entry in independent
        ),
        "missing_adapter_count": sum(entry["flags"]["missing_adapter"] for entry in independent),
        "single_mode_switch_visible_count": sum(
            entry["flags"]["single_mode_switch_visible"] for entry in independent
        ),
        "claimed_bidirectional_without_adapter_count": sum(
            entry["flags"]["claimed_bidirectional_without_adapter"] for entry in independent
        ),
    }
    baseline: dict[str, Any] = {
        "schema_version": 1,
        "manifest_digest": manifest.get("manifest_digest"),
        "source_digest": source_digest,
        "stats": stats,
        "entries": sorted(entries, key=lambda item: item["entry_id"]),
    }
    baseline["baseline_digest"] = _sha256(
        json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return baseline


def render_json(baseline: dict[str, Any]) -> str:
    return json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_frontend(baseline: dict[str, Any]) -> str:
    entries = [
        {
            "entryId": entry["entry_id"],
            "capability": entry["capability"],
            "migrationState": entry["migration_state"],
            "independentEntry": entry["independent_entry"],
            "reasonCodes": entry["reason_codes"],
            "modeSwitchVisible": entry["ui_characterization"]["mode_switch_visible"],
            "modeSwitchEvidence": entry["ui_characterization"]["evidence"],
        }
        for entry in baseline["entries"]
    ]
    return f"""/**
 * Generated by `backend/scripts/gen/generate_workpaper_sync_legacy_baseline.py`.
 * This file records open migration debt; it is not an allowlist or success baseline.
 */
export const WORKPAPER_SYNC_LEGACY_BASELINE_DIGEST = {json.dumps(baseline['baseline_digest'])}
export const WORKPAPER_SYNC_LEGACY_STATS = {json.dumps(baseline['stats'], ensure_ascii=False, indent=2, sort_keys=True)} as const
export const WORKPAPER_SYNC_LEGACY_ENTRIES = {json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True)} as const
"""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _print_stats(prefix: str, baseline: dict[str, Any]) -> None:
    stats = baseline["stats"]
    print(
        f"[{prefix}] entries={stats['entry_count']} independent={stats['independent_entry_count']} "
        f"template_only={stats['template_only_open_count']} reload_only={stats['html_reload_only_count']} "
        f"no_forcesave={stats['no_forcesave_command_count']} "
        f"no_ack={stats['no_durable_forcesave_ack_count']} "
        f"missing_adapter={stats['missing_adapter_count']} "
        f"single_with_switch={stats['single_mode_switch_visible_count']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    manifest = _load_json(_MANIFEST_PATH)
    baseline = build_baseline(manifest)
    rendered = ((_BASELINE_PATH, render_json(baseline)), (_FRONTEND_PATH, render_frontend(baseline)))
    _print_stats("SOURCE", baseline)
    if args.check:
        stale = [
            str(path.relative_to(_REPO))
            for path, content in rendered
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print(f"[FAIL] stale generated legacy baseline: {stale}")
            return 2
        _print_stats("CHECKED", baseline)
        print(f"[OK] baseline digest {baseline['baseline_digest']}")
        return 0

    for path, content in rendered:
        _atomic_write(path, content)
        print(f"[APPLIED] {path.relative_to(_REPO)} sha256={_sha256(content.encode('utf-8'))[:16]}")
    _print_stats("GENERATED", baseline)
    print(f"[OK] baseline digest {baseline['baseline_digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LegacyBaselineError as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(2) from exc
