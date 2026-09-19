"""Property-based test for StalePropagationEngine format detection (P6).

Spec: .kiro/specs/acnr-consumer-wiring (design.md Correctness Property P6).

Subject under test: module-level pure function
``app.services.stale_propagation_engine._detect_and_normalize`` (task 3.5).

Property 6: Format Detection Correctness
  For any string, ``_detect_and_normalize()`` SHALL classify inputs with a
  ``WP:`` prefix and colons as legacy format (applying normalization to
  addr_id), and inputs with ``/`` separators and no ``WP:`` prefix as addr_id
  format (passing through unchanged). Non-WP domain URIs (REPORT:, TB:, NOTE:,
  ...) also pass through unchanged.
  **Validates: Requirements 4.1, 4.2, 4.3**
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.linkage_graph_builder import _normalize_wp_uri_to_addr_id
from app.services.stale_propagation_engine import _detect_and_normalize


# ─── Strategies ──────────────────────────────────────────────────────────────

# Legal wp_code: leading letter + digits + optional "-digit" + optional trailing
# letter. Contains no ":" and no "/", forming a clean single segment and never
# colliding with the literal "WP:" legacy prefix.
_wp_code = st.from_regex(r"\A[A-N]\d{1,2}(?:-\d)?[A-Z]?\Z")

# Sheet code recognizable by the builder's _SHEET_CODE_PATTERN.
_sheet_code = st.from_regex(r"\A[A-Z]\d{1,2}(?:-\d{1,2})?[A-Z]?\Z")

# Chinese sheet-display prefixes seen in prefill/cross-wp data. None contain any
# A–Z latin letter, so the sheet-code regex only matches the code we append.
_sheet_prefix = st.sampled_from(["明细表", "审定表", "分析表", "汇总表", ""])

# Cell reference: column letters + row number. No ":" / "/".
_cell = st.from_regex(r"\A[A-Z]{1,3}\d{1,4}\Z")

# Non-WP domains that must pass through unchanged.
_non_wp_domain = st.sampled_from(["REPORT", "TB", "NOTE", "ADJ", "MAPPING"])


@st.composite
def _legacy_wp_uri(draw: st.DrawFn) -> str:
    """A valid legacy WP URI ``WP:{wp_code}:{sheet_display}:{cell}`` that
    normalizes to a 3-segment addr_id."""
    wp_code = draw(_wp_code)
    sheet_display = f"{draw(_sheet_prefix)}{draw(_sheet_code)}"
    cell = draw(_cell)
    return f"WP:{wp_code}:{sheet_display}:{cell}"


@st.composite
def _addr_id(draw: st.DrawFn) -> str:
    """An addr_id ``{wp_code}/{sheet_code}/{cell}`` (no ``WP:`` prefix)."""
    return f"{draw(_wp_code)}/{draw(_sheet_code)}/{draw(_cell)}"


@st.composite
def _non_wp_uri(draw: st.DrawFn) -> str:
    """A non-WP domain URI, e.g. ``REPORT:...``, ``TB:...``, ``NOTE:...``."""
    domain = draw(_non_wp_domain)
    suffix = draw(st.text())
    return f"{domain}:{suffix}"


# Tagged mixed strategy: each example is (kind, uri) so a single property
# exercises all three input categories interleaved (the "mix" required by the
# task), while allowing category-specific assertions.
_mixed = st.one_of(
    st.tuples(st.just("legacy"), _legacy_wp_uri()),
    st.tuples(st.just("addr_id"), _addr_id()),
    st.tuples(st.just("non_wp"), _non_wp_uri()),
)


# ─── Property 6: Format Detection Correctness ────────────────────────────────

@settings(max_examples=200)
@given(tagged=_mixed)
def test_p6_format_detection_correctness(tagged: tuple[str, str]) -> None:
    """Property 6: legacy WP URIs → addr_id; addr_id / non-WP pass through.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """
    kind, uri = tagged
    result = _detect_and_normalize(uri)

    if kind == "legacy":
        # Legacy WP URI is normalized to addr_id: contains "/", no "WP:" prefix,
        # and matches the dedicated normalization function (Req 4.1).
        assert not result.startswith("WP:")
        assert "/" in result
        assert result == _normalize_wp_uri_to_addr_id(uri)
        # Exactly three "/"-separated segments (wp_code / sheet_code / cell).
        assert len(result.split("/")) == 3
    else:
        # addr_id-format (Req 4.2) and non-WP inputs (Req 4.3) pass through
        # unchanged.
        assert result == uri


@settings(max_examples=200)
@given(uri=_addr_id())
def test_p6_addr_id_passthrough_unchanged(uri: str) -> None:
    """Property 6: addr_id-format input is used directly (unchanged).

    **Validates: Requirements 4.2, 4.3**
    """
    assert not uri.startswith("WP:")
    assert _detect_and_normalize(uri) == uri


@settings(max_examples=200)
@given(uri=_non_wp_uri())
def test_p6_non_wp_domain_passthrough_unchanged(uri: str) -> None:
    """Property 6: non-WP domain URIs (REPORT:/TB:/NOTE:/...) pass through.

    **Validates: Requirements 4.3**
    """
    assert not uri.startswith("WP:")
    assert _detect_and_normalize(uri) == uri


@settings(max_examples=200)
@given(uri=_legacy_wp_uri())
def test_p6_legacy_wp_uri_normalized_to_addr_id(uri: str) -> None:
    """Property 6: legacy WP URI is normalized (contains "/", drops "WP:").

    **Validates: Requirements 4.1**
    """
    assert uri.startswith("WP:")
    result = _detect_and_normalize(uri)
    assert not result.startswith("WP:")
    assert "/" in result
    assert result == _normalize_wp_uri_to_addr_id(uri)


# ─── Concrete examples (unit) ────────────────────────────────────────────────

def test_example_legacy_wp_uri_normalized() -> None:
    """Design example: WP:D2:明细表D2-2:E100 → D2/D2-2/E100."""
    assert _detect_and_normalize("WP:D2:明细表D2-2:E100") == "D2/D2-2/E100"


def test_example_addr_id_passthrough() -> None:
    """An addr_id-format input is returned unchanged."""
    assert _detect_and_normalize("D2/D2-2/E100") == "D2/D2-2/E100"


def test_example_non_wp_domains_unchanged() -> None:
    """REPORT/TB/NOTE domain URIs pass through untouched."""
    for uri in [
        "REPORT:BS-009::",
        "TB:1122::期末余额",
        "NOTE:五、1:0:total",
    ]:
        assert _detect_and_normalize(uri) == uri
