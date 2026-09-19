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
import re
import json
import pathlib
from collections import Counter
from datetime import datetime, timezone

from capability_ledger import (
    CAPABILITIES,
    RUNTIME_CAPABILITIES,
    SCHEMA_VERSION,
    capability_record,
)

try:
    from .workpaper_component_manifest import (
        MANIFEST_OUTPUT_PATH,
        generate_component_manifest,
        print_component_manifest_summary,
        write_component_manifest,
    )
except ImportError:  # direct script execution
    from workpaper_component_manifest import (
        MANIFEST_OUTPUT_PATH,
        generate_component_manifest,
        print_component_manifest_summary,
        write_component_manifest,
    )

sys.stdout.reconfigure(encoding='utf-8')

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/

WP_CODE_OVERRIDES_PATH = PROJECT_ROOT / 'backend' / 'app' / 'data' / 'wp_code_overrides.json'
WORKPAPER_DIR = PROJECT_ROOT / 'audit-platform' / 'frontend' / 'src' / 'components' / 'workpaper'
OUTPUT_PATH = WORKPAPER_DIR / 'coverage-ledger.json'

# ─── Capability detection patterns ───────────────────────────────────────────

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
    'persistence': [
        re.compile(r'useChecklistPersistence'),
        re.compile(r'checklist-responses'),
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


def _entry_ref(file_path: pathlib.Path) -> str:
    return file_path.relative_to(PROJECT_ROOT).as_posix()


def detect_capabilities(file_path: pathlib.Path) -> dict[str, list[str]]:
    """Return reproducible source evidence for every detected capability."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return {capability: [] for capability in CAPABILITIES}

    source = _entry_ref(file_path)
    return {
        capability: [
            f'{source}:{pattern.pattern}'
            for pattern in DETECTION_PATTERNS[capability]
            if pattern.search(content)
        ]
        for capability in CAPABILITIES
    }


def detect_shell_evidence(file_path: pathlib.Path) -> list[str]:
    """Return source evidence for legacy Shell/Scaffold runtime wiring."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []
    source = _entry_ref(file_path)
    return [
        f'{source}:{pattern.pattern}'
        for pattern in SHELL_WRAPPED_PATTERNS
        if pattern.search(content)
    ]


def get_distinct_root_codes(overrides: dict) -> set[str]:
    """Extract dedicated root wp_codes from the override source."""
    skip_types = {'skip', 'onlyoffice-sheet', 'word-template', 'redirect-materiality'}
    return {
        match.group(1)
        for code, component_type in overrides.items()
        if component_type not in skip_types and (match := WP_ROOT_RE.match(code))
    }


def component_type_for(root_code: str, overrides: dict) -> str | None:
    """Resolve one representative dedicated componentType for a root code."""
    skip_types = {'skip', 'onlyoffice-sheet', 'word-template', 'redirect-materiality'}
    exact = overrides.get(root_code)
    if exact is not None and exact not in skip_types:
        return exact
    candidates = [
        component_type
        for code, component_type in overrides.items()
        if component_type not in skip_types
        and (match := WP_ROOT_RE.match(code))
        and match.group(1) == root_code
    ]
    return Counter(candidates).most_common(1)[0][0] if candidates else None


def generate_ledger(check_only: bool = False) -> dict:
    """Generate a complete capability-level v2 ledger."""
    overrides = load_wp_code_overrides()
    root_codes = get_distinct_root_codes(overrides)
    entry_files = find_main_entry_files()
    entries = {}

    for root_code in sorted(root_codes):
        entry_file = entry_files.get(root_code)
        if entry_file is None:
            continue
        detected = detect_capabilities(entry_file)
        shell_evidence = detect_shell_evidence(entry_file)
        records = {}
        for capability in CAPABILITIES:
            evidence = list(detected[capability])
            if shell_evidence and capability in RUNTIME_CAPABILITIES:
                evidence.extend(shell_evidence)
            records[capability] = capability_record(
                'covered' if evidence else 'unknown', evidence
            )
        entries[root_code] = {
            'componentType': component_type_for(root_code, overrides),
            'entryFile': _entry_ref(entry_file),
            'capabilities': records,
        }

    return {
        'schemaVersion': SCHEMA_VERSION,
        'generatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'capabilities': list(CAPABILITIES),
        'entries': entries,
    }


def main() -> int:
    check_only = '--check' in sys.argv
    component_manifest_mode = '--component-manifest' in sys.argv
    output_path = MANIFEST_OUTPUT_PATH if component_manifest_mode else OUTPUT_PATH

    # Parse --output flag
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_path = pathlib.Path(sys.argv[idx + 1])

    if component_manifest_mode:
        manifest = generate_component_manifest()
        print_component_manifest_summary(manifest)
        if not check_only:
            write_component_manifest(manifest, output_path)
            print(f'\n[OK] 已写入: {output_path}')
        else:
            print('\n[CHECK] 预演模式，未写入文件。')
        if '--strict' in sys.argv and not manifest['isComplete']:
            print('[FAIL] component manifest 存在注册漂移。')
            return 1
        return 0

    ledger = generate_ledger(check_only=check_only)

    # Print summary
    total = len(ledger['entries'])
    covered_any = sum(
        any(record['status'] == 'covered' for record in entry['capabilities'].values())
        for entry in ledger['entries'].values()
    )

    print(f'[Coverage Ledger v2] 扫描完成: {total} 个底稿根入口')
    print(f'  至少一项能力有证据: {covered_any}')
    print(f'  能力清单: {", ".join(CAPABILITIES)}')
    print()

    # Print per-entry summary
    for code, entry in ledger['entries'].items():
        covered = [
            capability
            for capability, record in entry['capabilities'].items()
            if record['status'] == 'covered'
        ]
        print(f"  {code:6s} → {', '.join(covered) if covered else '(无证据)'}")

    if check_only:
        print('\n[CHECK] 预演模式，未写入文件。')
        return 0

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'\n[OK] 已写入: {output_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
