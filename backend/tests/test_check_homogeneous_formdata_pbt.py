# Feature: workpaper-maintainability-convergence-followup, Property 7: CI guard strict mode blocks new violations
"""
Property-Based Test for check_homogeneous_formdata.py CI guard.

Property 7: CI guard strict mode blocks new violations
  - For any new file matching the homogeneous FormData pattern that contains
    self-built checklist-responses network calls and does NOT use
    createChecklistFormData or useChecklistPersistence,
    `check_homogeneous_formdata.py --strict` SHALL exit 1.

Counter-property:
  - For any file that uses createChecklistFormData( → scan_file produces
    NO violations.

Uses importlib to load scan functions from backend/scripts/check/check_homogeneous_formdata.py.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ─── 动态导入 check_homogeneous_formdata.py ──────────────────────────────────

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'check' / 'check_homogeneous_formdata.py'

_spec = importlib.util.spec_from_file_location('check_homogeneous_formdata', _SCRIPT_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules['check_homogeneous_formdata'] = _module
_spec.loader.exec_module(_module)

scan_file = _module.scan_file
Report = _module.Report
FORMDATA_FILE_RE = _module.FORMDATA_FILE_RE
MIGRATED_ALLOWLIST = _module.MIGRATED_ALLOWLIST
uses_factory_or_adapter = _module.uses_factory_or_adapter
FRONTEND_ROOT = _module.FRONTEND_ROOT


# ─── Strategies ──────────────────────────────────────────────────────────────

# Generate a valid useXFormData filename NOT in allowlist
_ALPHA_UPPER = st.sampled_from(list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
_DIGITS = st.text(alphabet='0123456789', min_size=1, max_size=3)
_SUFFIX = st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=0, max_size=8)


@st.composite
def formdata_filename(draw: st.DrawFn) -> str:
    """Generate a filename matching useXFormData pattern NOT in MIGRATED_ALLOWLIST."""
    letter = draw(_ALPHA_UPPER)
    digits = draw(_DIGITS)
    suffix = draw(_SUFFIX)
    # Capitalize suffix first letter if present to make valid camelCase
    if suffix:
        suffix = suffix[0].upper() + suffix[1:]
    name = f'use{letter}{digits}{suffix}FormData.ts'
    assume(FORMDATA_FILE_RE.match(name))
    assume(name not in MIGRATED_ALLOWLIST)
    return name


# Self-built network call patterns (must trigger violation detection)
_NETWORK_PATTERNS = st.sampled_from([
    'api.put(`/api/workpapers/${wpId}/checklist-responses`, data)',
    "api.put('/api/workpapers/' + wpId + '/checklist-responses', payload)",
    'api.get(`/api/workpapers/${wpId}/checklist-responses`)',
    "api.get('/api/workpapers/${id}/checklist-responses')",
    "fetch(`/api/workpapers/${wpId}/checklist-responses`)",
])

# Surrounding code that doesn't use factory
_FILLER_LINES = st.lists(
    st.sampled_from([
        'import { ref } from "vue"',
        'const wpId = ref("")',
        'const data = ref({})',
        'export function useNewFormData(wpId, projectId) {',
        '  const saving = ref(false)',
        '  return { saving }',
        '}',
        '// some comment',
        '',
    ]),
    min_size=2,
    max_size=10,
)


@st.composite
def violating_file_content(draw: st.DrawFn) -> str:
    """Generate file content with self-built network calls and NO factory usage."""
    prefix_lines = draw(_FILLER_LINES)
    network_call = draw(_NETWORK_PATTERNS)
    suffix_lines = draw(_FILLER_LINES)
    content = '\n'.join(prefix_lines + [network_call] + suffix_lines)
    # Ensure no factory pattern present
    assume(not uses_factory_or_adapter(content))
    return content


@st.composite
def compliant_file_content(draw: st.DrawFn) -> str:
    """Generate file content that uses createChecklistFormData factory."""
    factory_line = "const result = createChecklistFormData({"
    config_lines = [
        '  wpId,',
        '  projectId,',
        "  itemPrefix: 'X1-',",
        "  label: 'X1',",
        '})',
    ]
    extra_lines = draw(_FILLER_LINES)
    content = '\n'.join(
        ["import { createChecklistFormData } from '../factories/createChecklistFormData'"]
        + extra_lines
        + [factory_line]
        + config_lines
    )
    return content


# ─── Property Tests ──────────────────────────────────────────────────────────


@settings(max_examples=100)
@given(filename=formdata_filename(), content=violating_file_content())
def test_property7_self_built_network_produces_violations(filename: str, content: str):
    """
    Property 7: For any new FormData file with self-built network calls
    and no factory usage, scan_file SHALL produce violations.
    """
    # Create a temp file with the appropriate name in a directory structure
    # that mimics FRONTEND_ROOT to make filepath.relative_to work
    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a mock directory structure: audit-platform/frontend/src/components/workpaper/composables/
        composables_dir = Path(tmpdir) / 'audit-platform' / 'frontend' / 'src' / 'components' / 'workpaper' / 'composables'
        composables_dir.mkdir(parents=True, exist_ok=True)
        filepath = composables_dir / filename
        filepath.write_text(content, encoding='utf-8')

        # Monkey-patch FRONTEND_ROOT for this test
        original_frontend_root = _module.FRONTEND_ROOT
        _module.FRONTEND_ROOT = Path(tmpdir) / 'audit-platform' / 'frontend' / 'src'

        try:
            report = Report()
            scan_file(filepath, report)
            assert report.violations, (
                f'Expected violations for file {filename} with self-built network, '
                f'but got none. Content snippet: {content[:200]}'
            )
            assert report.homogeneous_new > 0
        finally:
            _module.FRONTEND_ROOT = original_frontend_root


@settings(max_examples=100)
@given(filename=formdata_filename(), content=compliant_file_content())
def test_property7_counter_factory_usage_no_violations(filename: str, content: str):
    """
    Counter-property: For any FormData file that uses createChecklistFormData(,
    scan_file SHALL produce NO violations.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        composables_dir = Path(tmpdir) / 'audit-platform' / 'frontend' / 'src' / 'components' / 'workpaper' / 'composables'
        composables_dir.mkdir(parents=True, exist_ok=True)
        filepath = composables_dir / filename
        filepath.write_text(content, encoding='utf-8')

        original_frontend_root = _module.FRONTEND_ROOT
        _module.FRONTEND_ROOT = Path(tmpdir) / 'audit-platform' / 'frontend' / 'src'

        try:
            report = Report()
            scan_file(filepath, report)
            assert not report.violations, (
                f'Expected no violations for file {filename} using factory, '
                f'but got {len(report.violations)}. Content: {content[:200]}'
            )
            assert report.homogeneous_new == 0
        finally:
            _module.FRONTEND_ROOT = original_frontend_root
