"""
Coverage Ledger Generator correctness properties (Property 1, 2, 3).

# Feature: workpaper-maintainability-convergence-followup, Property 1: Ledger completeness — all dedicated roots present
# Feature: workpaper-maintainability-convergence-followup, Property 2: Runtime Boundary auto-marking consistency
# Feature: workpaper-maintainability-convergence-followup, Property 3: Runtime Boundary absence preserves unknown

Testing framework: Hypothesis (Python PBT), configured with @settings(max_examples=100)
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ─── Import the generator module from script location ─────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts" / "check"

# Need to add the script dir to sys.path for the relative imports in the module
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location(
    "generate_coverage_ledger", _SCRIPT_DIR / "generate_coverage_ledger.py"
)
assert _spec and _spec.loader
gen_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_module)

# Also import capability_ledger for constants
from capability_ledger import (  # noqa: E402
    CAPABILITIES,
    RUNTIME_CAPABILITIES,
)

# ─── Strategies ───────────────────────────────────────────────────────────────

# Generate valid wp_code root codes like A1, B2, C3, D4, ..., N5, K14, K15 etc.
_LETTERS = "ABCDEFGHIJKLMN"
_wp_root_code = st.builds(
    lambda letter, num: f"{letter}{num}",
    st.sampled_from(list(_LETTERS)),
    st.integers(min_value=1, max_value=18),
)

# Non-skip componentTypes
_NON_SKIP_TYPES = [
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "audit-sheet",
    "a-program-console",
    "confirmation-positive",
    "d-form-review",
    "d-form-confirmation",
    "j1-employee-compensation",
    "k1-other-receivables",
]

# Skip types that should be excluded
_SKIP_TYPES = ["skip", "onlyoffice-sheet", "word-template", "redirect-materiality"]

_non_skip_component_type = st.sampled_from(_NON_SKIP_TYPES)
_skip_component_type = st.sampled_from(_SKIP_TYPES)

# Generate a set of overrides: root_code → componentType (non-skip)
_overrides_entry = st.tuples(_wp_root_code, _non_skip_component_type)


# Generate random file content with inject(WorkpaperRuntimeContextKey)
_RUNTIME_INJECT_SNIPPET = "const runtime = inject(WorkpaperRuntimeContextKey, null)"

_vue_boilerplate = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=0,
    max_size=200,
)


@st.composite
def _file_content_with_runtime_boundary(draw):
    """Generate file content that contains inject(WorkpaperRuntimeContextKey)."""
    prefix = draw(_vue_boilerplate)
    suffix = draw(_vue_boilerplate)
    # Use various forms of the inject pattern
    inject_form = draw(st.sampled_from([
        "inject(WorkpaperRuntimeContextKey",
        "inject( WorkpaperRuntimeContextKey",
        "inject(  WorkpaperRuntimeContextKey",
        "const runtime = inject(WorkpaperRuntimeContextKey, null)",
        "const ctx = inject(WorkpaperRuntimeContextKey)",
    ]))
    return f"{prefix}\n{inject_form}\n{suffix}"


@st.composite
def _file_content_without_runtime_boundary(draw):
    """Generate file content that does NOT contain inject(WorkpaperRuntimeContextKey)
    and has no other matching detection patterns for any capability."""
    # Generate innocuous text that won't match any DETECTION_PATTERNS or RUNTIME_BOUNDARY_PATTERN
    safe_words = draw(st.lists(
        st.sampled_from([
            "const", "function", "return", "export", "import",
            "template", "script", "setup", "defineComponent",
            "computed", "ref", "reactive", "onMounted",
            "watchEffect", "provide", "emit", "props",
            "ElTable", "ElButton", "ElCard", "ElForm",
            "useState", "handleClick", "loadData",
            "const data = ref([])",
            "function handleSave() {}",
            "export default defineComponent({})",
        ]),
        min_size=3,
        max_size=15,
    ))
    content = "\n".join(safe_words)
    # Verify it doesn't accidentally match any patterns
    assert not gen_module.RUNTIME_BOUNDARY_PATTERN.search(content)
    for cap_patterns in gen_module.DETECTION_PATTERNS.values():
        for pattern in cap_patterns:
            assert not pattern.search(content)
    return content


# ─── Property 1: Ledger completeness — all dedicated roots present ────────────


@settings(max_examples=100, deadline=None, suppress_health_check=[
    HealthCheck.too_slow, HealthCheck.function_scoped_fixture,
])
@given(
    overrides_data=st.lists(
        st.tuples(_wp_root_code, _non_skip_component_type),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0],
    ),
    run_id=st.integers(min_value=0, max_value=2**31),
)
def test_property_1_ledger_completeness_all_dedicated_roots_present(
    overrides_data: list[tuple[str, str]], run_id: int, tmp_path: Path
) -> None:
    """Property 1: Ledger completeness — all dedicated roots present.

    For any wp_code root that has a dedicated main entry file and a non-skip
    componentType in wp_code_overrides.json, the generated Coverage Ledger
    SHALL contain a capability record for that root.

    **Validates: Requirements 1.2**
    """
    import tempfile

    # Use a unique temp dir per hypothesis example to avoid reuse
    work_dir = Path(tempfile.mkdtemp())

    # Build overrides dict from generated data
    overrides = {code: comp_type for code, comp_type in overrides_data}

    # Create corresponding main entry files in a temp dir
    workpaper_dir = work_dir / "workpaper"
    workpaper_dir.mkdir(parents=True)

    expected_roots = set()
    for code, comp_type in overrides_data:
        # Create a main entry file like GtD2SomeComponent.vue
        filename = f"Gt{code}TestComponent.vue"
        entry_file = workpaper_dir / filename
        entry_file.write_text(
            "<script setup>\n// placeholder\n</script>\n",
            encoding="utf-8",
        )
        expected_roots.add(code)

    # Compute root codes using the module function
    root_codes = gen_module.get_distinct_root_codes(overrides)

    # Verify all expected roots are extracted
    assert expected_roots == root_codes, (
        f"Expected roots {expected_roots} but got {root_codes}"
    )

    # Now test the full flow with patched paths
    with patch.object(gen_module, "WORKPAPER_DIR", workpaper_dir), \
         patch.object(gen_module, "PROJECT_ROOT", work_dir):

        entry_files = gen_module.find_main_entry_files()

        # All roots in overrides with entry files should be found
        for root in expected_roots:
            assert root in entry_files, (
                f"Root {root} has entry file but was not found by find_main_entry_files()"
            )

        # Generate the ledger with patched functions
        with patch.object(gen_module, "load_wp_code_overrides", return_value=overrides):
            ledger = gen_module.generate_ledger()

        # Verify all non-skip roots with entry files appear in ledger
        for root in expected_roots:
            assert root in ledger["entries"], (
                f"Root {root} (non-skip, has entry file) missing from ledger entries"
            )
            # Verify it has capability records for all capabilities
            entry = ledger["entries"][root]
            assert "capabilities" in entry
            for cap in CAPABILITIES:
                assert cap in entry["capabilities"], (
                    f"Root {root} missing capability record for {cap}"
                )


# ─── Property 2: Runtime Boundary auto-marking consistency ────────────────────


@settings(max_examples=100, deadline=None, suppress_health_check=[
    HealthCheck.too_slow, HealthCheck.function_scoped_fixture,
])
@given(content=_file_content_with_runtime_boundary())
def test_property_2_runtime_boundary_automark_consistency(
    content: str, tmp_path: Path
) -> None:
    """Property 2: Runtime Boundary auto-marking consistency.

    For any main entry file containing `inject(WorkpaperRuntimeContextKey`,
    the Ledger Generator SHALL mark all 5 Runtime Boundary capabilities
    (displayPrefs, agingConfig, version, review, ai) as covered with
    non-empty evidence.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp())

    # Write generated file content to a temp file
    entry_file = work_dir / "GtD1TestComponent.vue"
    entry_file.write_text(content, encoding="utf-8")

    # Run detect_capabilities on the file
    with patch.object(gen_module, "PROJECT_ROOT", work_dir):
        capabilities = gen_module.detect_capabilities(entry_file)

    # All 5 Runtime Boundary capabilities must be covered (non-empty evidence)
    for cap in RUNTIME_CAPABILITIES:
        assert len(capabilities[cap]) > 0, (
            f"Capability '{cap}' has empty evidence despite file containing "
            f"inject(WorkpaperRuntimeContextKey). Content snippet: {content[:100]}"
        )
        # Evidence must contain the runtime boundary marker
        evidence_str = " ".join(capabilities[cap])
        assert "WorkpaperRuntimeContextKey" in evidence_str, (
            f"Capability '{cap}' evidence does not reference WorkpaperRuntimeContextKey: "
            f"{capabilities[cap]}"
        )


# ─── Property 3: Runtime Boundary absence preserves unknown ───────────────────


@settings(max_examples=100, deadline=None, suppress_health_check=[
    HealthCheck.too_slow, HealthCheck.function_scoped_fixture,
])
@given(content=_file_content_without_runtime_boundary())
def test_property_3_runtime_boundary_absence_preserves_unknown(
    content: str, tmp_path: Path
) -> None:
    """Property 3: Runtime Boundary absence preserves unknown.

    For any main entry file that does NOT contain `inject(WorkpaperRuntimeContextKey`
    and has no other matching detection patterns for a given capability,
    that capability SHALL remain as unknown status (empty evidence).

    **Validates: Requirements 2.6**
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp())

    # Write generated file content to a temp file
    entry_file = work_dir / "GtA1TestComponent.vue"
    entry_file.write_text(content, encoding="utf-8")

    # Run detect_capabilities on the file
    with patch.object(gen_module, "PROJECT_ROOT", work_dir):
        capabilities = gen_module.detect_capabilities(entry_file)

    # ALL capabilities must have empty evidence (no patterns matched)
    for cap in CAPABILITIES:
        assert capabilities[cap] == [], (
            f"Capability '{cap}' has non-empty evidence [{capabilities[cap]}] "
            f"despite file containing no matching patterns. Content: {content[:200]}"
        )
