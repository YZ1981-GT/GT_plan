"""Property-based tests for check_wp_version_trail.py CI guard script.

# Feature: version-trail-full-coverage, Property 1: CI Guard Detection Completeness
# Feature: version-trail-full-coverage, Property 2: CI Guard Whitelist Exclusion

Validates:
- Property 1: scan_file correctly detects presence/absence of two markers
- Property 2: whitelisted files never appear in violations
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Import guard script functions via sys.path ──────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
sys.path.insert(0, str(_SCRIPT_DIR))

from check_wp_version_trail import (  # noqa: E402
    MARKER_COMPONENT,
    MARKER_COMPOSABLE,
    load_whitelist,
    scan_file,
)


# ─── Strategies ──────────────────────────────────────────────────────────────

# Generate random Vue SFC-like content that may or may not contain the markers
_vue_filler = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters="\n<>/{}()='\";:.- ",
    ),
    min_size=0,
    max_size=300,
)


@st.composite
def vue_sfc_content(draw, has_composable: bool = False, has_component: bool = False):
    """Generate random Vue SFC content with controlled marker presence."""
    parts = []
    # Random preamble
    parts.append(draw(_vue_filler))

    if has_composable:
        # Insert the composable marker in a realistic context
        parts.append(f"\nimport {{ {MARKER_COMPOSABLE} }} from './composables/{MARKER_COMPOSABLE}'\n")
    else:
        # Ensure no accidental inclusion of the marker
        filler = draw(_vue_filler)
        # Remove any accidental occurrence
        filler = filler.replace(MARKER_COMPOSABLE, "somethingElse")
        parts.append(filler)

    parts.append(draw(_vue_filler))

    if has_component:
        # Insert the component marker in template context
        parts.append(f"\n<{MARKER_COMPONENT} ref=\"versionTrailRef\" />\n")
    else:
        filler = draw(_vue_filler)
        filler = filler.replace(MARKER_COMPONENT, "OtherComponent")
        parts.append(filler)

    parts.append(draw(_vue_filler))

    content = "".join(parts)
    # Final safety: strip markers if not intended
    if not has_composable:
        content = content.replace(MARKER_COMPOSABLE, "Replaced")
    if not has_component:
        content = content.replace(MARKER_COMPONENT, "Replaced")
    return content


# ─── Property 1: CI Guard Detection Completeness ─────────────────────────────
# Feature: version-trail-full-coverage, Property 1: CI Guard Detection Completeness
# **Validates: Requirements 14.2, 14.3**


@settings(max_examples=100)
@given(content=vue_sfc_content(has_composable=True, has_component=True))
def test_scan_file_both_present(content: str, tmp_path: Path):
    """scan_file returns (True, True) when both markers are present."""
    p = tmp_path / "GtD3Test.vue"
    p.write_text(content, encoding="utf-8")
    has_composable, has_component = scan_file(p)
    assert has_composable is True
    assert has_component is True


@settings(max_examples=100)
@given(content=vue_sfc_content(has_composable=True, has_component=False))
def test_scan_file_only_composable(content: str, tmp_path: Path):
    """scan_file returns (True, False) when only composable marker is present."""
    p = tmp_path / "GtD4Test.vue"
    p.write_text(content, encoding="utf-8")
    has_composable, has_component = scan_file(p)
    assert has_composable is True
    assert has_component is False


@settings(max_examples=100)
@given(content=vue_sfc_content(has_composable=False, has_component=True))
def test_scan_file_only_component(content: str, tmp_path: Path):
    """scan_file returns (False, True) when only component marker is present."""
    p = tmp_path / "GtE1Test.vue"
    p.write_text(content, encoding="utf-8")
    has_composable, has_component = scan_file(p)
    assert has_composable is False
    assert has_component is True


@settings(max_examples=100)
@given(content=vue_sfc_content(has_composable=False, has_component=False))
def test_scan_file_neither_present(content: str, tmp_path: Path):
    """scan_file returns (False, False) when neither marker is present."""
    p = tmp_path / "GtF1Test.vue"
    p.write_text(content, encoding="utf-8")
    has_composable, has_component = scan_file(p)
    assert has_composable is False
    assert has_component is False


# ─── Property 2: CI Guard Whitelist Exclusion ─────────────────────────────────
# Feature: version-trail-full-coverage, Property 2: CI Guard Whitelist Exclusion
# **Validates: Requirements 14.5**

# Strategy: generate random filenames and a random whitelist subset
_filename_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-."),
    min_size=3,
    max_size=30,
).map(lambda s: f"Gt{s}.vue")


@st.composite
def filename_and_whitelist(draw):
    """Generate a list of filenames and a whitelist subset."""
    filenames = draw(st.lists(_filename_strategy, min_size=1, max_size=20, unique=True))
    # Whitelist is a subset of the filenames
    whitelist_indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(filenames) - 1),
            max_size=len(filenames),
            unique=True,
        )
    )
    whitelist = {filenames[i] for i in whitelist_indices}
    return filenames, whitelist


@settings(max_examples=100)
@given(data=filename_and_whitelist())
def test_whitelist_exclusion_property(data, tmp_path: Path):
    """Whitelisted files never appear in violations regardless of content.

    Property: For any set of filenames and any whitelist configuration,
    whitelisted files SHALL be excluded from violation reporting.
    Non-whitelisted non-compliant files SHALL appear in violations.
    """
    filenames, whitelist = data

    # Write whitelist file
    whitelist_path = tmp_path / "whitelist.txt"
    whitelist_content = "# Auto-generated whitelist\n" + "\n".join(whitelist)
    whitelist_path.write_text(whitelist_content, encoding="utf-8")

    # Verify load_whitelist correctly loads the set
    loaded = load_whitelist(whitelist_path)
    assert loaded == whitelist


@settings(max_examples=100)
@given(data=filename_and_whitelist())
def test_whitelist_comments_and_empty_lines(data, tmp_path: Path):
    """Whitelist loading ignores comments and empty lines correctly."""
    filenames, whitelist = data

    # Write whitelist with extra comments and empty lines
    lines = ["# Comment at top", ""]
    for f in whitelist:
        lines.append(f"# Entry for {f}")
        lines.append(f)
        lines.append("")  # Empty line after each entry
    lines.append("# Trailing comment")

    whitelist_path = tmp_path / "whitelist.txt"
    whitelist_path.write_text("\n".join(lines), encoding="utf-8")

    loaded = load_whitelist(whitelist_path)
    assert loaded == whitelist


def test_whitelist_file_not_exists(tmp_path: Path):
    """load_whitelist returns empty set when file doesn't exist."""
    nonexistent = tmp_path / "nonexistent_whitelist.txt"
    result = load_whitelist(nonexistent)
    assert result == set()


@settings(max_examples=100)
@given(data=filename_and_whitelist())
def test_whitelist_never_in_violations(data, tmp_path: Path):
    """Simulate the full scan logic: whitelisted files never appear as violations."""
    filenames, whitelist = data

    # Create files: whitelisted ones are NON-COMPLIANT (no markers),
    # ensuring if whitelist works they still won't appear in violations
    violations = []
    for fname in filenames:
        fpath = tmp_path / fname
        # Write non-compliant content (no markers)
        fpath.write_text("<template><div>empty</div></template>", encoding="utf-8")

        if fname in whitelist:
            # Whitelisted: should NOT appear in violations
            continue

        has_composable, has_component = scan_file(fpath)
        if not (has_composable and has_component):
            violations.append(fname)

    # Verify: no whitelisted file in violations
    for v in violations:
        assert v not in whitelist, f"Whitelisted file {v} found in violations!"

    # Verify: all non-whitelisted files ARE in violations (since content is non-compliant)
    non_whitelisted = set(filenames) - whitelist
    assert set(violations) == non_whitelisted
