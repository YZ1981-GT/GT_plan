#!/usr/bin/env python3
"""
generate_coverage_ledger.py — 扫描底稿主入口，正向检出各全局能力接线状态，
写入 coverage-ledger.json。

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python generate_coverage_ledger.py                      # 生成并写入 coverage-ledger.json
    python generate_coverage_ledger.py --check              # 仅打印报告，不写文件
    python generate_coverage_ledger.py --output path.json   # 指定输出路径

Feature: platform-global-hardening, Task 3.4
Requirements: 2.3
"""
import sys
import os
import re
import json
import pathlib
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/

WP_CODE_OVERRIDES_PATH = PROJECT_ROOT / 'backend' / 'app' / 'data' / 'wp_code_overrides.json'
WORKPAPER_DIR = PROJECT_ROOT / 'audit-platform' / 'frontend' / 'src' / 'components' / 'workpaper'
OUTPUT_PATH = WORKPAPER_DIR / 'coverage-ledger.json'

# ─── Capability detection patterns ───────────────────────────────────────────

CAPABILITIES = [
    'displayPrefs',
    'agingConfig',
    'version',
    'review',
    'ai',
    'importExport',
    'acnr',
]

# Regex patterns for each capability detection
# Each maps to a list of regex patterns; if ANY matches → detected=true
DETECTION_PATTERNS = {
    'displayPrefs': [
        re.compile(r'DisplayPrefs_Key', re.IGNORECASE),
        re.compile(r'useDisplayPrefsStore'),
    ],
    'agingConfig': [
        re.compile(r'useAgingConfig'),
    ],
    'version': [
        re.compile(r'useWorkpaperVersionToolbar'),
    ],
    'review': [
        re.compile(r'useWorkpaperReviewProvide'),
        re.compile(r"provide\s*\(\s*['\"]openReviewDialog['\"]"),
    ],
    'ai': [
        re.compile(r'useD\d+AiGenerate|useE\d+AiGenerate|useF\d+AiGenerate|useG\d+AiGenerate|useH\d+AiGenerate|useI\d+AiGenerate|useJ\d+AiGenerate|useK\d+AiGenerate|useL\d+AiGenerate|useM\d+AiGenerate|useN\d+AiGenerate|useS\d+AiGenerate'),
        re.compile(r"provide\s*\(\s*['\"]generateAiText['\"]"),
        re.compile(r'ai/generate-text'),
    ],
    'importExport': [
        re.compile(r'useD\d+ImportExport|useE\d+ImportExport|useF\d+ImportExport|useG\d+ImportExport|useH\d+ImportExport|useI\d+ImportExport|useJ\d+ImportExport|useK\d+ImportExport|useL\d+ImportExport|useM\d+ImportExport|useN\d+ImportExport|useS\d+ImportExport|useWorkpaperImportExport|useXImportExport'),
    ],
    'acnr': [
        re.compile(r'useAcnr'),
        re.compile(r'address_registry|addressRegistry', re.IGNORECASE),
        re.compile(r'GtIndexChip'),
    ],
}

# shellWrapped detection
SHELL_WRAPPED_PATTERNS = [
    re.compile(r'useWorkpaperScaffold'),
    re.compile(r'GtWorkpaperShell'),
]

# ─── Main entry file resolution ───────────────────────────────────────────────

# Main entry pattern: Gt{CycleCode}*.vue at workpaper root
# e.g., GtD2AccountsReceivable.vue, GtE1MonetaryFund.vue
MAIN_ENTRY_RE = re.compile(r'^Gt([A-Z]\d+(?:-\d+)?)\w*\.vue$')

# wp_code root extraction: D2-1 → D2, G4-5 → G4
WP_ROOT_RE = re.compile(r'^([A-Z]\d+)')


def load_wp_code_overrides() -> dict:
    """Load wp_code_overrides.json as authoritative wp_code list."""
    try:
        with open(WP_CODE_OVERRIDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f'[WARN] 无法读取 wp_code_overrides.json: {e}', file=sys.stderr)
        return {}


def find_main_entry_files() -> dict:
    """
    Find main entry Vue files for each cycle root wp_code.
    Returns dict: wp_code_root → file_path
    """
    entries = {}
    if not WORKPAPER_DIR.exists():
        return entries

    for f in WORKPAPER_DIR.iterdir():
        if not f.is_file():
            continue
        m = MAIN_ENTRY_RE.match(f.name)
        if m:
            code = m.group(1)
            # Normalize: take root code (D2, E1, etc.)
            root_m = WP_ROOT_RE.match(code)
            root_code = root_m.group(1) if root_m else code
            # Keep first match per root code (most specific)
            if root_code not in entries:
                entries[root_code] = f
    return entries


def detect_capabilities(file_path: pathlib.Path) -> dict:
    """
    Read a main entry .vue file and detect capability wiring via regex.
    Returns dict: capability → bool
    """
    detected = {}
    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        # fail-open: cannot read → all unknown
        return {cap: False for cap in CAPABILITIES}

    for cap in CAPABILITIES:
        patterns = DETECTION_PATTERNS.get(cap, [])
        found = any(p.search(content) for p in patterns)
        detected[cap] = found

    return detected


def detect_shell_wrapped(file_path: pathlib.Path) -> bool:
    """Check if a main entry uses GtWorkpaperShell or useWorkpaperScaffold."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return False

    return any(p.search(content) for p in SHELL_WRAPPED_PATTERNS)


def get_distinct_root_codes(overrides: dict) -> set:
    """
    Extract distinct root wp_codes from overrides that represent D~N/S cycle entries.
    Only include codes that have a dedicated componentType (not skip/generic).
    """
    skip_types = {'skip', 'onlyoffice-sheet', 'word-template', 'redirect-materiality'}
    root_codes = set()

    for code, comp_type in overrides.items():
        if comp_type in skip_types:
            continue
        # Extract root: D2-1 → D2, G4 → G4
        m = WP_ROOT_RE.match(code)
        if m:
            root_codes.add(m.group(1))

    return root_codes


def generate_ledger(check_only: bool = False) -> dict:
    """Generate the coverage ledger data."""
    overrides = load_wp_code_overrides()
    root_codes = get_distinct_root_codes(overrides)
    entry_files = find_main_entry_files()

    entries = {}

    for root_code in sorted(root_codes):
        entry_file = entry_files.get(root_code)
        if entry_file is None:
            # No main entry found for this root — skip silently
            continue

        shell_wrapped = detect_shell_wrapped(entry_file)
        detected = detect_capabilities(entry_file)

        # Only include detected capabilities that are True (keep object compact)
        detected_compact = {k: v for k, v in detected.items() if v}

        entry = {
            'shellWrapped': shell_wrapped,
            'detected': detected_compact,
        }
        entries[root_code] = entry

    ledger = {
        'generatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'capabilities': CAPABILITIES,
        'entries': entries,
    }

    return ledger


def main():
    check_only = '--check' in sys.argv
    output_path = OUTPUT_PATH

    # Parse --output flag
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_path = pathlib.Path(sys.argv[idx + 1])

    ledger = generate_ledger(check_only=check_only)

    # Print summary
    total = len(ledger['entries'])
    shell_count = sum(1 for e in ledger['entries'].values() if e['shellWrapped'])
    detected_any = sum(
        1 for e in ledger['entries'].values()
        if any(e['detected'].values()) if e['detected']
    )

    print(f'[Coverage Ledger] 扫描完成: {total} 个底稿根入口')
    print(f'  shellWrapped: {shell_count}')
    print(f'  至少一项能力检出: {detected_any}')
    print(f'  能力清单: {", ".join(CAPABILITIES)}')
    print()

    # Print per-entry summary
    for code, entry in ledger['entries'].items():
        caps = ', '.join(entry['detected'].keys()) if entry['detected'] else '(无)'
        shell = '🛡️' if entry['shellWrapped'] else '  '
        print(f'  {shell} {code:6s} → {caps}')

    if check_only:
        print(f'\n[CHECK] 预演模式，未写入文件。')
        return

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'\n[OK] 已写入: {output_path}')


if __name__ == '__main__':
    main()
