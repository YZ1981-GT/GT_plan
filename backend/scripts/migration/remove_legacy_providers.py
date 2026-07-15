#!/usr/bin/env python
"""
remove_legacy_providers.py — 批量删除已被 Runtime Boundary 覆盖的 Legacy Provider 接线代码。

目标文件：workpaper/Gt*.vue 主入口（顶层 + 一级子目录）
前置条件：文件必须包含 inject(WorkpaperRuntimeContextKey 才处理
删除目标：
  - import { useWorkpaperVersionToolbar } from ... 行
  - useWorkpaperVersionToolbar(...) 调用行及其返回值解构
  - import { useWorkpaperReviewProvide } from ... 行
  - useWorkpaperReviewProvide(...) 调用行
安全约束：不触碰 inject(WorkpaperRuntimeContextKey 等 Runtime Boundary 消费代码

Usage:
  python backend/scripts/migration/remove_legacy_providers.py           # dry-run (prints unified diff)
  python backend/scripts/migration/remove_legacy_providers.py --apply   # writes changes
  python backend/scripts/migration/remove_legacy_providers.py --cycle D,E,F  # only D/E/F cycles

Requirements: 3.1, 3.2, 3.3, 3.6
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import List, Set, Tuple

# ─── Configuration ───────────────────────────────────────────────────────────

# Base directory for workpaper Vue components (relative to project root)
WORKPAPER_DIR = Path("audit-platform/frontend/src/components/workpaper")

# Pattern to identify eligible files (must inject WorkpaperRuntimeContextKey)
ELIGIBILITY_PATTERN = re.compile(r"inject\s*\(\s*WorkpaperRuntimeContextKey")

# Main entry file pattern: GtX1*.vue at top-level or one-level subdirectory
# Matches: GtD2AccountsReceivable.vue, GtK14-1Other.vue, etc.
MAIN_ENTRY_RE = re.compile(r"^Gt([A-Z]\d+(?:-\d+)?)\w*\.vue$")

# Cycle letter extraction: GtD2AccountsReceivable.vue -> "D"
CYCLE_LETTER_RE = re.compile(r"^Gt([A-Z])")

# ─── Legacy Provider Patterns ────────────────────────────────────────────────

# Import line patterns
RE_IMPORT_VERSION_TOOLBAR = re.compile(
    r"^\s*import\s+\{[^}]*useWorkpaperVersionToolbar[^}]*\}\s+from\s+['\"].*['\"];?\s*$"
)
RE_IMPORT_REVIEW_PROVIDE = re.compile(
    r"^\s*import\s+\{[^}]*useWorkpaperReviewProvide[^}]*\}\s+from\s+['\"].*['\"];?\s*$"
)

# Call/destructure patterns for useWorkpaperVersionToolbar
# Matches: const { versionTrailRef, ... } = useWorkpaperVersionToolbar(...)
# Matches: const result = useWorkpaperVersionToolbar(...)
# Matches: useWorkpaperVersionToolbar(...)
RE_CALL_VERSION_TOOLBAR = re.compile(
    r"^\s*(?:(?:const|let|var)\s+(?:\{[^}]*\}|\w+)\s*=\s*)?useWorkpaperVersionToolbar\s*\([^)]*\)\s*;?\s*$"
)

# Call patterns for useWorkpaperReviewProvide
# Matches: useWorkpaperReviewProvide(...)
# Matches: useWorkpaperReviewProvide({ wpId: ..., projectId: ... })
RE_CALL_REVIEW_PROVIDE = re.compile(
    r"^\s*(?:(?:const|let|var)\s+(?:\{[^}]*\}|\w+)\s*=\s*)?useWorkpaperReviewProvide\s*\([^)]*\)\s*;?\s*$"
)

# Multi-line call detection: starts with call but doesn't end with closing paren
RE_CALL_VERSION_TOOLBAR_START = re.compile(
    r"^\s*(?:(?:const|let|var)\s+(?:\{[^}]*\}|\w+)\s*=\s*)?useWorkpaperVersionToolbar\s*\("
)
RE_CALL_REVIEW_PROVIDE_START = re.compile(
    r"^\s*(?:(?:const|let|var)\s+(?:\{[^}]*\}|\w+)\s*=\s*)?useWorkpaperReviewProvide\s*\("
)

# Line that completes a multi-line call (ends with closing paren + optional semicolon)
RE_CALL_END = re.compile(r".*\)\s*;?\s*$")


# ─── Core Logic ──────────────────────────────────────────────────────────────


def find_main_entry_files(project_root: Path, cycle_filter: Set[str] | None) -> List[Path]:
    """Scan workpaper directory for Gt*.vue main entry files.

    Scans top-level and one-level subdirectories (d1/, k3/, etc.).
    Optionally filters by cycle letter prefix.
    """
    workpaper_path = project_root / WORKPAPER_DIR
    if not workpaper_path.is_dir():
        print(f"ERROR: Workpaper directory not found: {workpaper_path}", file=sys.stderr)
        sys.exit(1)

    results: List[Path] = []

    # Top-level Gt*.vue files
    for f in sorted(workpaper_path.iterdir()):
        if f.is_file() and MAIN_ENTRY_RE.match(f.name):
            if _matches_cycle_filter(f.name, cycle_filter):
                results.append(f)

    # One-level subdirectory Gt*.vue files
    for subdir in sorted(workpaper_path.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith(("__", ".")):
            for f in sorted(subdir.iterdir()):
                if f.is_file() and MAIN_ENTRY_RE.match(f.name):
                    if _matches_cycle_filter(f.name, cycle_filter):
                        results.append(f)

    return results


def _matches_cycle_filter(filename: str, cycle_filter: Set[str] | None) -> bool:
    """Check if filename matches the cycle filter (e.g., D, E, F)."""
    if cycle_filter is None:
        return True
    m = CYCLE_LETTER_RE.match(filename)
    if not m:
        return True  # Non-standard names pass through
    return m.group(1).upper() in cycle_filter


def is_eligible(content: str) -> bool:
    """Check if file contains inject(WorkpaperRuntimeContextKey — prerequisite for processing."""
    return bool(ELIGIBILITY_PATTERN.search(content))


def identify_lines_to_delete(lines: List[str]) -> Set[int]:
    """Identify line indices to delete (0-based).

    Targets:
    - import { useWorkpaperVersionToolbar } from '...' lines
    - useWorkpaperVersionToolbar(...) call lines (including multi-line destructure)
    - import { useWorkpaperReviewProvide } from '...' lines
    - useWorkpaperReviewProvide(...) call lines (including multi-line)
    """
    to_delete: Set[int] = set()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Check import lines
        if RE_IMPORT_VERSION_TOOLBAR.match(line):
            to_delete.add(i)
            i += 1
            continue

        if RE_IMPORT_REVIEW_PROVIDE.match(line):
            to_delete.add(i)
            i += 1
            continue

        # Check single-line calls
        if RE_CALL_VERSION_TOOLBAR.match(line):
            to_delete.add(i)
            i += 1
            continue

        if RE_CALL_REVIEW_PROVIDE.match(line):
            to_delete.add(i)
            i += 1
            continue

        # Check multi-line calls (start detected but no closing paren on same line)
        if RE_CALL_VERSION_TOOLBAR_START.match(line) and not RE_CALL_END.match(line):
            # Mark this line and all continuation lines until closing paren
            to_delete.add(i)
            i += 1
            while i < n and not RE_CALL_END.match(lines[i]):
                to_delete.add(i)
                i += 1
            if i < n:
                to_delete.add(i)  # Mark the closing line too
            i += 1
            continue

        if RE_CALL_REVIEW_PROVIDE_START.match(line) and not RE_CALL_END.match(line):
            to_delete.add(i)
            i += 1
            while i < n and not RE_CALL_END.match(lines[i]):
                to_delete.add(i)
                i += 1
            if i < n:
                to_delete.add(i)
            i += 1
            continue

        i += 1

    return to_delete


def compress_blank_lines(lines: List[str]) -> List[str]:
    """Compress consecutive blank lines: >2 consecutive blanks → 1 blank line."""
    result: List[str] = []
    consecutive_blanks = 0

    for line in lines:
        if line.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks <= 1:
                result.append(line)
            # Skip if >1 consecutive blank
        else:
            consecutive_blanks = 0
            result.append(line)

    return result


def process_file(filepath: Path) -> Tuple[str, str, bool]:
    """Process a single file. Returns (original_content, new_content, was_modified)."""
    content = filepath.read_text(encoding="utf-8")
    original_lines = content.splitlines(keepends=True)

    # Identify lines to delete
    lines_no_newline = [l.rstrip("\n").rstrip("\r") for l in original_lines]
    to_delete = identify_lines_to_delete(lines_no_newline)

    if not to_delete:
        return content, content, False

    # Build new content by excluding deleted lines
    new_lines = [line for i, line in enumerate(original_lines) if i not in to_delete]

    # Compress consecutive blank lines
    new_lines = compress_blank_lines(new_lines)

    new_content = "".join(new_lines)
    return content, new_content, True


def generate_diff(filepath: Path, original: str, modified: str, project_root: Path) -> str:
    """Generate a unified diff for the file."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    try:
        rel_path = str(filepath.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        rel_path = str(filepath)
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        lineterm="",
    )
    return "".join(diff)


# ─── Main Entry Point ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Remove legacy provider code from workpaper main entries that use Runtime Boundary."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to files (default is dry-run showing unified diff)",
    )
    parser.add_argument(
        "--cycle",
        type=str,
        default=None,
        help="Comma-separated cycle letters to process (e.g., D,E,F). Default: all cycles.",
    )
    args = parser.parse_args()

    # Determine project root (script is at backend/scripts/migration/)
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent  # backend/scripts/migration/ -> project root

    # Parse cycle filter
    cycle_filter: Set[str] | None = None
    if args.cycle:
        cycle_filter = {c.strip().upper() for c in args.cycle.split(",")}

    # Find target files
    entry_files = find_main_entry_files(project_root, cycle_filter)
    print(f"Found {len(entry_files)} main entry file(s) to scan.")

    # Statistics
    processed = 0
    modified = 0
    skipped_not_eligible = 0
    skipped_no_changes = 0

    for filepath in entry_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  WARN: Cannot read {filepath.name}: {e}", file=sys.stderr)
            continue

        # Eligibility check: must contain inject(WorkpaperRuntimeContextKey
        if not is_eligible(content):
            skipped_not_eligible += 1
            continue

        processed += 1

        # Process the file
        original, new_content, was_modified = process_file(filepath)

        if not was_modified:
            skipped_no_changes += 1
            continue

        modified += 1

        # Generate and show diff
        diff_text = generate_diff(filepath, original, new_content, project_root)
        if diff_text:
            try:
                rel = filepath.relative_to(project_root)
            except ValueError:
                rel = filepath
            print(f"\n{'─' * 72}")
            print(f"  {rel}")
            print(f"{'─' * 72}")
            print(diff_text)

        # Apply changes if --apply flag
        if args.apply:
            filepath.write_text(new_content, encoding="utf-8")
            print(f"  [APPLIED] {filepath.name}")

    # Summary
    print(f"\n{'═' * 72}")
    print("Summary:")
    print(f"  Total scanned:      {len(entry_files)}")
    print(f"  Not eligible:       {skipped_not_eligible} (no inject(WorkpaperRuntimeContextKey))")
    print(f"  Eligible processed: {processed}")
    print(f"  Modified:           {modified}")
    print(f"  No changes needed:  {skipped_no_changes}")
    if args.apply:
        print(f"  Mode:               APPLY (files written)")
    else:
        print(f"  Mode:               DRY-RUN (no files changed)")
    print(f"{'═' * 72}")


if __name__ == "__main__":
    main()
