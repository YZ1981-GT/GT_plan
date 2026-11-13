"""
Scanner: enumerates eligible files, computes scopes, runs parser,
and produces the structured JSON output.

Design reference: §15 A8, §16 F9.
"""
from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rules import (
    INCLUDE_GLOBS,
    EXCLUDE_GLOBS,
    SCAN_SCOPE_DRIFT,
)
from .vue_ts_parser import ParseResult, parse_file


@dataclass
class ScopeResult:
    """Per-scope analysis result."""
    scope: str
    eligible: int = 0
    parsed: int = 0
    skipped: int = 0
    skipped_files: list[str] = field(default_factory=list)
    exempted: int = 0
    candidates: int = 0
    candidate_details: list[dict[str, Any]] = field(default_factory=list)
    core_violations: int = 0
    core_violation_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScanResult:
    """Full scan output."""
    scopes: dict[str, ScopeResult] = field(default_factory=dict)
    total_eligible: int = 0
    total_parsed: int = 0
    total_skipped: int = 0
    total_candidates: int = 0
    total_core_violations: int = 0
    errors: list[str] = field(default_factory=list)
    parser_exemptions: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        scopes_json = {}
        for name, sr in sorted(self.scopes.items()):
            scopes_json[name] = {
                "eligible": sr.eligible,
                "parsed": sr.parsed,
                "skipped": sr.skipped,
                "skipped_files": sr.skipped_files,
                "exempted": sr.exempted,
                "candidates": sr.candidates,
                "candidate_details": sr.candidate_details,
                "core_violations": sr.core_violations,
                "core_violation_details": sr.core_violation_details,
            }
        return {
            "total_eligible": self.total_eligible,
            "total_parsed": self.total_parsed,
            "total_skipped": self.total_skipped,
            "total_candidates": self.total_candidates,
            "total_core_violations": self.total_core_violations,
            "scopes": scopes_json,
            "parser_exemptions": self.parser_exemptions,
            "errors": self.errors,
        }


def _git_tracked_files(src_root: Path) -> set[str]:
    """Get Git-tracked files relative to src_root, plus untracked candidates."""
    try:
        # tracked files
        tracked = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", str(src_root)],
            capture_output=True, text=True, cwd=src_root.parent,
            timeout=30,
        )
        if tracked.returncode != 0:
            return set()
        result = set()
        for line in tracked.stdout.splitlines():
            line = line.strip()
            if line:
                # Make relative to src_root
                try:
                    p = Path(line)
                    if p.is_absolute():
                        p = p.relative_to(src_root)
                    result.add(str(p).replace("\\", "/"))
                except (ValueError, OSError):
                    pass
        return result
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()


def _matches_any_glob(rel_path: str, globs: tuple[str, ...]) -> bool:
    """Check if a relative path matches any of the given globs."""
    for g in globs:
        if fnmatch.fnmatch(rel_path, g):
            return True
        # Also check without src/ prefix for globs starting with src/
        if g.startswith("src/") and fnmatch.fnmatch(f"src/{rel_path}", g):
            return True
    return False


def _compute_scope(rel_path: str) -> str:
    """
    Compute scope for a file relative to src/.

    Scope = first directory under src/, or "src:root" for files directly in src/.
    """
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return "src:root"
    return parts[0]


def _glob_match(path: str, pattern: str) -> bool:
    """
    Match a path against a glob pattern with proper ** support.

    Handles `src/**/*.vue` matching both `src/App.vue` and
    `src/components/Test.vue` (** = zero or more path segments).
    """
    import re as _re

    # Replace ** with a unique placeholder before escaping
    _PH = "\x00GLOBSTAR\x00"
    tmp = pattern.replace("**", _PH)
    # Escape regex specials
    tmp = _re.escape(tmp)
    # Restore globstar: match zero or more path segments (including the trailing /)
    # Before globstar there's usually a /, and after it there's usually a /
    # Handle patterns like "src/**/*.vue" -> "src/" + ** + "/*.vue"
    # After escaping: "src/" + \x00GLOBSTAR\x00 + "/\*\.vue"
    # We need ** to eat the surrounding slashes: "src/(.*/)?" + "*\.vue"
    tmp = tmp.replace(f"/{_PH}/", "/(?:.+/)?")
    tmp = tmp.replace(f"/{_PH}", "(?:/.+)?")
    tmp = tmp.replace(f"{_PH}/", "(?:.+/)?")
    tmp = tmp.replace(_PH, ".*")
    # Convert remaining single \* to non-slash wildcard
    tmp = tmp.replace(r"\*", "[^/]*")
    regex = f"^{tmp}$"

    return bool(_re.match(regex, path))


def enumerate_eligible_files(
    frontend_src: Path,
    parser_exemptions: dict[str, str] | None = None,
) -> tuple[dict[str, list[Path]], dict[str, str], list[str]]:
    """
    Enumerate eligible files grouped by scope.

    Returns (scope_to_files, actual_exemptions_used, errors).
    """
    errors: list[str] = []
    parser_exemptions = parser_exemptions or {}

    # Walk the src directory
    scope_files: dict[str, list[Path]] = {}
    all_candidates: list[tuple[str, Path]] = []

    for p in frontend_src.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(frontend_src)).replace("\\", "/")
        full_rel = f"src/{rel}"

        # Check include – use PurePosixPath.match for recursive ** support
        included = False
        for g in INCLUDE_GLOBS:
            if _glob_match(full_rel, g):
                included = True
                break
        if not included:
            continue

        # Check exclude
        excluded = False
        for g in EXCLUDE_GLOBS:
            if _glob_match(full_rel, g) or _glob_match(rel, g):
                excluded = True
                break
        if excluded:
            continue

        scope = _compute_scope(rel)
        all_candidates.append((scope, p))

    for scope, p in all_candidates:
        if scope not in scope_files:
            scope_files[scope] = []
        scope_files[scope].append(p)

    return scope_files, parser_exemptions, errors


def run_scan(
    frontend_src: Path,
    parser_exemptions: dict[str, str] | None = None,
    core_files: frozenset[str] | None = None,
) -> ScanResult:
    """
    Run the full scan on the frontend src directory.

    Args:
        frontend_src: Path to the frontend `src/` directory.
        parser_exemptions: Dict of {relative_path: reason} for files
            that are allowed to skip parsing.
        core_files: Set of relative paths (from src/) that are in the
            core matrix. Unknown numerics in these files are violations.
    """
    result = ScanResult()
    result.parser_exemptions = parser_exemptions or {}
    core_files = core_files or frozenset()

    scope_files, _, errors = enumerate_eligible_files(
        frontend_src, parser_exemptions
    )
    result.errors.extend(errors)

    for scope, files in sorted(scope_files.items()):
        sr = ScopeResult(scope=scope)
        sr.eligible = len(files)

        for fpath in files:
            rel = str(fpath.relative_to(frontend_src)).replace("\\", "/")
            is_core = rel in core_files

            # Check parser exemption
            if rel in result.parser_exemptions:
                sr.exempted += 1
                sr.parsed += 1  # exempted counts as parsed for eligible = parsed + exempted
                continue

            pr = parse_file(fpath)
            if not pr.parsed:
                sr.skipped += 1
                sr.skipped_files.append(rel)
                if rel not in result.parser_exemptions:
                    result.errors.append(
                        f"{SCAN_SCOPE_DRIFT}: Unregistered parser skip: {rel} ({pr.error})"
                    )
                continue

            sr.parsed += 1

            for node in pr.display_nodes:
                if node.violation_code:
                    sr.core_violations += 1
                    sr.core_violation_details.append({
                        "file": rel,
                        "line": node.line,
                        "code": node.violation_code,
                        "tag": node.tag_or_expr,
                    })

                if node.is_unknown_numeric:
                    sr.candidates += 1
                    sr.candidate_details.append({
                        "file": rel,
                        "line": node.line,
                        "tag": node.tag_or_expr,
                        "signals": node.signals,
                        "core": is_core,
                    })

        # Validate scope invariant
        expected_parsed = sr.parsed  # parsed already includes exempted
        if sr.eligible != expected_parsed + sr.skipped:
            result.errors.append(
                f"{SCAN_SCOPE_DRIFT}: scope={scope} eligible={sr.eligible} "
                f"!= parsed({sr.parsed}) + skipped({sr.skipped})"
            )

        result.scopes[scope] = sr
        result.total_eligible += sr.eligible
        result.total_parsed += sr.parsed
        result.total_skipped += sr.skipped
        result.total_candidates += sr.candidates
        result.total_core_violations += sr.core_violations

    # Validate: no scope has eligible=0 (scope drift if include root shrinks)
    for scope, sr in result.scopes.items():
        if sr.eligible == 0:
            result.errors.append(
                f"{SCAN_SCOPE_DRIFT}: scope={scope} has 0 eligible files"
            )
        if sr.parsed == 0 and sr.eligible > 0:
            result.errors.append(
                f"{SCAN_SCOPE_DRIFT}: scope={scope} has 0 parsed files "
                f"out of {sr.eligible} eligible"
            )

    return result
