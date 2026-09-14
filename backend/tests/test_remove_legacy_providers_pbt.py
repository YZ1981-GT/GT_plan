# Feature: workpaper-maintainability-convergence-followup, Property 4: Legacy Provider removal preserves Runtime Boundary
"""
Property 4: Legacy Provider removal preserves Runtime Boundary

For any main entry file content that contains `inject(WorkpaperRuntimeContextKey`
AND some legacy provider code (useWorkpaperVersionToolbar/useWorkpaperReviewProvide
imports and calls), after running `identify_lines_to_delete` + filtering +
`compress_blank_lines`, the resulting content STILL contains
`inject(WorkpaperRuntimeContextKey`.

Validates: Requirements 3.3
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Set

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Import the script under test ────────────────────────────────────────────

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migration"
    / "remove_legacy_providers.py"
)
_spec = importlib.util.spec_from_file_location("remove_legacy_providers", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

identify_lines_to_delete = _mod.identify_lines_to_delete
compress_blank_lines = _mod.compress_blank_lines

# ─── Strategies ──────────────────────────────────────────────────────────────

# The critical Runtime Boundary line that MUST be preserved
RUNTIME_BOUNDARY_LINE = "const runtime = inject(WorkpaperRuntimeContextKey, null)"

# Legacy provider import lines (0-2)
LEGACY_IMPORTS = [
    "import { useWorkpaperVersionToolbar } from '@/composables/useWorkpaperVersionToolbar'",
    "import { useWorkpaperReviewProvide } from '@/composables/useWorkpaperReviewProvide'",
]

# Legacy provider call lines (0-2)
LEGACY_CALLS = [
    "const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = useWorkpaperVersionToolbar(wpId, projectId)",
    "useWorkpaperReviewProvide({ wpId, projectId })",
]

# Random Vue script lines that are neither legacy nor runtime boundary
NEUTRAL_LINES = [
    "import { ref, computed, onMounted } from 'vue'",
    "import { useRoute } from 'vue-router'",
    "const props = defineProps<{ wpId: string; projectId: string }>()",
    "const route = useRoute()",
    "const isLoading = ref(false)",
    "const allResponses = ref(new Map())",
    "onMounted(async () => { await loadData() })",
    "const emit = defineEmits(['navigate-sheet'])",
    "function handleSave(data: any) { /* save logic */ }",
    "const currentSheet = computed(() => props.sheetName || '')",
    "watch(() => props.year, (v) => { if (v) fetchTbData() })",
    "provide('saveResponse', saveImmediate)",
    "",  # blank line
]


@st.composite
def vue_script_with_runtime_boundary_and_legacy(draw: st.DrawFn) -> str:
    """Generate a synthetic Vue <script setup> content that:
    - Always contains the inject(WorkpaperRuntimeContextKey line
    - Contains 0-2 legacy provider import lines
    - Contains 0-2 legacy provider call lines
    - Contains random neutral lines interspersed
    """
    lines: List[str] = []

    # Add <script setup lang="ts"> header
    lines.append('<script setup lang="ts">')

    # Draw 0-5 neutral lines before imports
    num_pre = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_pre):
        lines.append(draw(st.sampled_from(NEUTRAL_LINES)))

    # Draw 0-2 legacy import lines
    num_legacy_imports = draw(st.integers(min_value=0, max_value=2))
    legacy_import_indices = draw(
        st.lists(
            st.sampled_from(range(len(LEGACY_IMPORTS))),
            min_size=num_legacy_imports,
            max_size=num_legacy_imports,
            unique=True,
        )
    )
    for idx in legacy_import_indices:
        lines.append(LEGACY_IMPORTS[idx])

    # Draw 1-4 neutral lines between imports and runtime boundary
    num_mid = draw(st.integers(min_value=1, max_value=4))
    for _ in range(num_mid):
        lines.append(draw(st.sampled_from(NEUTRAL_LINES)))

    # Always include the Runtime Boundary inject line
    lines.append(RUNTIME_BOUNDARY_LINE)

    # Draw 1-4 more neutral lines
    num_post_inject = draw(st.integers(min_value=1, max_value=4))
    for _ in range(num_post_inject):
        lines.append(draw(st.sampled_from(NEUTRAL_LINES)))

    # Draw 0-2 legacy call lines
    num_legacy_calls = draw(st.integers(min_value=0, max_value=2))
    legacy_call_indices = draw(
        st.lists(
            st.sampled_from(range(len(LEGACY_CALLS))),
            min_size=num_legacy_calls,
            max_size=num_legacy_calls,
            unique=True,
        )
    )
    for idx in legacy_call_indices:
        lines.append(LEGACY_CALLS[idx])

    # Draw 0-5 neutral lines at the end
    num_tail = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_tail):
        lines.append(draw(st.sampled_from(NEUTRAL_LINES)))

    # Close script tag
    lines.append("</script>")

    return "\n".join(lines)


# ─── Property Test ───────────────────────────────────────────────────────────


@settings(max_examples=100)
@given(content=vue_script_with_runtime_boundary_and_legacy())
def test_property_4_legacy_removal_preserves_runtime_boundary(content: str) -> None:
    """Property 4: Legacy Provider removal preserves Runtime Boundary.

    For any file content that contains `inject(WorkpaperRuntimeContextKey`
    AND some legacy provider code, after running identify_lines_to_delete +
    filtering + compress_blank_lines, the resulting content STILL contains
    `inject(WorkpaperRuntimeContextKey`.

    Validates: Requirements 3.3
    """
    # Precondition: content must contain the Runtime Boundary pattern
    assert "inject(WorkpaperRuntimeContextKey" in content

    # Apply the deletion pipeline (same as process_file logic)
    lines = content.split("\n")
    to_delete: Set[int] = identify_lines_to_delete(lines)

    # Build new content by excluding deleted lines
    new_lines = [line for i, line in enumerate(lines) if i not in to_delete]

    # Compress consecutive blank lines
    new_lines = compress_blank_lines(new_lines)

    result = "\n".join(new_lines)

    # Property: Runtime Boundary code MUST still be present
    assert "inject(WorkpaperRuntimeContextKey" in result, (
        f"Runtime Boundary inject line was incorrectly removed!\n"
        f"Deleted line indices: {sorted(to_delete)}\n"
        f"Original lines count: {len(lines)}\n"
        f"Result lines count: {len(new_lines)}"
    )


@settings(max_examples=100)
@given(content=vue_script_with_runtime_boundary_and_legacy())
def test_property_4_legacy_lines_are_removed(content: str) -> None:
    """Property 4 supplementary: Legacy provider lines ARE actually deleted.

    Ensures the deletion logic is not a no-op — when legacy lines exist,
    they should be removed from the output.

    Validates: Requirements 3.1, 3.2
    """
    lines = content.split("\n")
    to_delete: Set[int] = identify_lines_to_delete(lines)

    # Build new content
    new_lines = [line for i, line in enumerate(lines) if i not in to_delete]
    new_lines = compress_blank_lines(new_lines)
    result = "\n".join(new_lines)

    # If original had legacy imports, they should be gone
    has_version_toolbar_import = any(
        "useWorkpaperVersionToolbar" in l and "import" in l for l in lines
    )
    has_review_provide_import = any(
        "useWorkpaperReviewProvide" in l and "import" in l for l in lines
    )

    if has_version_toolbar_import:
        # The import line itself should not appear in result
        assert not any(
            "import" in l and "useWorkpaperVersionToolbar" in l
            for l in new_lines
        ), "useWorkpaperVersionToolbar import should have been removed"

    if has_review_provide_import:
        assert not any(
            "import" in l and "useWorkpaperReviewProvide" in l
            for l in new_lines
        ), "useWorkpaperReviewProvide import should have been removed"
