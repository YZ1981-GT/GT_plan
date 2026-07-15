"""AI Entry Coverage Scanner — Task 6.2 (P18).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8.2
Property: P18 — AI_entry_scan_set ∩ gate_declared_set_complement = ∅

Scans backend Python files for AI entry point patterns (calls to LLM/generate/
chat_completion/etc.) and compares against the declared AI_ENTRY_REGISTRY.
If `discovered_set - declared_gated_set ≠ ∅` → exits non-zero (blocks CI merge).

Usage:
    python backend/scripts/check/check_ai_entry_coverage.py [--strict]

Exit codes:
    0 = coverage complete (P18 holds)
    1 = undeclared entry points found (blocks merge)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Ensure project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.evidence_governance.ai_evidence_gate import (  # noqa: E402
    AI_ENTRY_REGISTRY,
    compute_coverage_gap,
)

# ─────────────────────────────────────────────────────────────────────────────
# Scanner configuration
# ─────────────────────────────────────────────────────────────────────────────

#: Directories to scan (relative to backend/)
SCAN_DIRS: list[str] = [
    "app/routers",
    "app/services",
]

#: File patterns to scan
SCAN_PATTERN = "**/*.py"

#: Regex patterns that indicate AI entry points (function calls that invoke LLM)
AI_ENTRY_PATTERNS: list[re.Pattern[str]] = [
    # Direct chat_completion / generate calls
    re.compile(r"\bchat_completion\s*\("),
    re.compile(r"\bgenerate_text\s*\("),
    re.compile(r"\bgenerate_conclusion\s*\("),
    re.compile(r"\bgenerate_analysis\s*\("),
    re.compile(r"\brewrite_content\s*\("),
    re.compile(r"\bsummarize_content\s*\("),
    re.compile(r"\bcomplete_content\s*\("),
    re.compile(r"\bgenerate_audit_opinion\s*\("),
    re.compile(r"\bgenerate_disclosure_note\s*\("),
    re.compile(r"\bgenerate_review_response\s*\("),
    re.compile(r"\bai_assist_ocr_field\s*\("),
    re.compile(r"\bgenerate_derecognition_judge\s*\("),
    # Generic LLM invocation patterns
    re.compile(r"\bllm_client\.\w+\s*\("),
    re.compile(r"\bai_client\.generate\s*\("),
    re.compile(r"\bopenai_client\.\w+\.\w+\s*\("),
]

#: Files/directories to exclude from scanning (tests, migrations, etc.)
EXCLUDE_PATTERNS: list[str] = [
    "__pycache__",
    "test_",
    "tests/",
    "migrations/",
    "scripts/",
    "conftest",
    "ai_evidence_gate.py",  # The gate itself
    "ai_content_log_service.py",  # Existing lifecycle (not an entry point)
]

#: Known false-positive patterns (comments, imports, string literals)
FALSE_POSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*#"),  # Comment lines
    re.compile(r"^\s*from\s+"),  # Import lines
    re.compile(r"^\s*import\s+"),  # Import lines
    re.compile(r'["\'].*chat_completion.*["\']'),  # String literal references
]


# ─────────────────────────────────────────────────────────────────────────────
# Scanner functions
# ─────────────────────────────────────────────────────────────────────────────


def should_exclude(filepath: Path) -> bool:
    """Check if file should be excluded from scanning."""
    path_str = str(filepath)
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str:
            return True
    return False


def is_false_positive(line: str) -> bool:
    """Check if a matched line is a false positive."""
    for fp_pattern in FALSE_POSITIVE_PATTERNS:
        if fp_pattern.search(line):
            return True
    return False


def extract_entry_point_name(line: str) -> str | None:
    """Extract the entry point function name from a matched line."""
    for pattern in AI_ENTRY_PATTERNS:
        match = pattern.search(line)
        if match:
            # Extract the function name from the match
            matched_text = match.group(0)
            # Remove the opening paren
            func_name = matched_text.rstrip("(").strip()
            # Handle method calls (obj.method → method)
            if "." in func_name:
                func_name = func_name.split(".")[-1]
            return func_name
    return None


def scan_file(filepath: Path) -> set[str]:
    """Scan a single file for AI entry point patterns.

    Returns set of discovered entry point names.
    """
    discovered: set[str] = set()
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return discovered

    for line_no, line in enumerate(content.splitlines(), 1):
        if is_false_positive(line):
            continue
        for pattern in AI_ENTRY_PATTERNS:
            if pattern.search(line):
                name = extract_entry_point_name(line)
                if name:
                    discovered.add(name)
                break

    return discovered


def scan_directories(base_path: Path, dirs: list[str]) -> set[str]:
    """Scan specified directories for AI entry points.

    Returns the full set of discovered entry point names.
    """
    all_discovered: set[str] = set()

    for scan_dir in dirs:
        dir_path = base_path / scan_dir
        if not dir_path.exists():
            continue

        for filepath in dir_path.glob(SCAN_PATTERN):
            if should_exclude(filepath):
                continue
            file_entries = scan_file(filepath)
            all_discovered.update(file_entries)

    return all_discovered


def run_coverage_check(strict: bool = False) -> int:
    """Run the AI entry coverage check.

    Returns exit code: 0 = pass, 1 = fail.
    """
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    backend_root = PROJECT_ROOT
    print(f"[AI Entry Coverage] Scanning: {backend_root}")
    print(f"[AI Entry Coverage] Declared entries: {len(AI_ENTRY_REGISTRY)}")

    discovered = scan_directories(backend_root, SCAN_DIRS)
    print(f"[AI Entry Coverage] Discovered entries: {len(discovered)}")

    gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)

    if gap:
        print(f"\n[FAIL] P18 violation: {len(gap)} undeclared AI entry point(s):")
        for entry in sorted(gap):
            print(f"  - {entry}")
        print(
            "\nAction: Add these to AI_ENTRY_REGISTRY in "
            "app/services/evidence_governance/ai_evidence_gate.py"
        )
        return 1

    print("[OK] P18 holds: all discovered AI entry points are declared in gate registry")

    if strict:
        # In strict mode, also check for entries declared but never discovered
        # (potentially dead code in registry)
        unused = set(AI_ENTRY_REGISTRY) - discovered
        if unused:
            print(f"\n[INFO] {len(unused)} declared entries not found in scan:")
            for entry in sorted(unused):
                print(f"  - {entry} (declared but not discovered)")
            # Not a failure — entries may be in frontend or not yet implemented

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    strict_mode = "--strict" in sys.argv
    sys.exit(run_coverage_check(strict=strict_mode))
