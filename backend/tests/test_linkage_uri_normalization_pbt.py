"""Property-based tests for WP URI → addr_id normalization (P4–P5).

Spec: .kiro/specs/acnr-consumer-wiring (design.md Correctness Properties P4–P5).

Subject under test: module-level pure function
``app.services.linkage_graph_builder._normalize_wp_uri_to_addr_id`` (task 3.1).

Property 4: WP URI Normalization Round-Trip Consistency
  For any valid WP-domain URI in format ``WP:{wp_code}:{sheet_display}:{cell}``
  where ``sheet_display`` contains a recognizable sheet code pattern
  (``[A-Z]\\d+(-\\d+)?[A-Z]?``), ``_normalize_wp_uri_to_addr_id(uri)`` produces an
  addr_id in format ``{wp_code}/{sheet_code}/{cell}`` that contains exactly three
  ``/``-separated segments and no ``WP:`` prefix.
  **Validates: Requirements 3.1, 3.10**

Property 5: Non-WP Domain URI Passthrough
  For any URI that does NOT start with ``WP:`` (including REPORT:, TB:, NOTE:,
  ADJ:, MAPPING:), ``_normalize_wp_uri_to_addr_id(uri)`` returns the input
  unchanged.
  **Validates: Requirements 3.5, 3.6, 3.8, 3.9**
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.linkage_graph_builder import _normalize_wp_uri_to_addr_id


# ─── Strategies ──────────────────────────────────────────────────────────────

# Legal wp_code: leading letter + digits + optional "-digit" + optional trailing
# letter. Contains no ":" and no "/", so it forms a clean single segment.
_wp_code = st.from_regex(r"\A[A-N]\d{1,2}(?:-\d)?[A-Z]?\Z")

# Sheet code recognizable by the builder's _SHEET_CODE_PATTERN
# (``[A-Z]\d+(?:-\d+)?[A-Z]?``). fullmatch keeps it self-contained.
_sheet_code = st.from_regex(r"\A[A-Z]\d{1,2}(?:-\d{1,2})?[A-Z]?\Z")

# Chinese sheet-display prefixes seen in prefill/cross-wp data. None contain any
# A–Z latin letter, so the sheet-code regex only ever matches the code we append.
_sheet_prefix = st.sampled_from(["明细表", "审定表", "分析表", "汇总表", ""])

# Cell reference: column letters + row number. No ":" / "/".
_cell = st.from_regex(r"\A[A-Z]{1,3}\d{1,4}\Z")

# Non-WP domains that must pass through unchanged.
_non_wp_domain = st.sampled_from(["REPORT", "TB", "NOTE", "ADJ", "MAPPING"])


# ─── Property 4: WP URI Normalization Round-Trip Consistency ─────────────────

@settings(max_examples=200)
@given(wp_code=_wp_code, prefix=_sheet_prefix, sheet_code=_sheet_code, cell=_cell)
def test_p4_wp_uri_normalizes_to_three_segment_addr_id(
    wp_code: str, prefix: str, sheet_code: str, cell: str
) -> None:
    """Property 4: WP-domain URI → ``{wp_code}/{sheet_code}/{cell}`` (3 segments).

    **Validates: Requirements 3.1, 3.10**
    """
    sheet_display = f"{prefix}{sheet_code}"
    uri = f"WP:{wp_code}:{sheet_display}:{cell}"

    result = _normalize_wp_uri_to_addr_id(uri)

    # No WP: prefix survives on the output.
    assert not result.startswith("WP:")

    # Exactly three "/"-separated segments (wp_code / sheet_code / cell).
    segments = result.split("/")
    assert len(segments) == 3, f"expected 3 segments, got {segments!r} from {uri!r}"

    # Round-trip: segments equal the components fed in.
    assert segments[0] == wp_code
    assert segments[1] == sheet_code
    assert segments[2] == cell
    assert result == f"{wp_code}/{sheet_code}/{cell}"


# ─── Property 5: Non-WP Domain URI Passthrough ───────────────────────────────

@settings(max_examples=200)
@given(domain=_non_wp_domain, suffix=st.text())
def test_p5_non_wp_domain_uri_passthrough(domain: str, suffix: str) -> None:
    """Property 5: non-WP-domain URI is returned unchanged (input == output).

    **Validates: Requirements 3.5, 3.6, 3.8, 3.9**
    """
    uri = f"{domain}:{suffix}"
    # By construction never starts with "WP:".
    assert not uri.startswith("WP:")

    assert _normalize_wp_uri_to_addr_id(uri) == uri


@settings(max_examples=200)
@given(text=st.text().filter(lambda s: not s.startswith("WP:")))
def test_p5_arbitrary_non_wp_string_passthrough(text: str) -> None:
    """Property 5 (generalized): any string not starting with ``WP:`` is unchanged.

    **Validates: Requirements 3.5, 3.6, 3.8, 3.9**
    """
    assert _normalize_wp_uri_to_addr_id(text) == text


# ─── Concrete examples (unit) ────────────────────────────────────────────────

def test_example_wp_uri_from_design_doc() -> None:
    """Design example: WP:D2:明细表D2-2:E100 → D2/D2-2/E100."""
    assert _normalize_wp_uri_to_addr_id("WP:D2:明细表D2-2:E100") == "D2/D2-2/E100"


def test_example_non_wp_domains_unchanged() -> None:
    """REPORT/TB/NOTE/MAPPING/ADJ domain URIs pass through untouched."""
    for uri in [
        "TB:1122::期末余额",
        "REPORT:BS-009::",
        "NOTE:五、1:0:total",
        "MAPPING:1001::1002",
        "ADJ:1122::aje",
    ]:
        assert _normalize_wp_uri_to_addr_id(uri) == uri


def test_example_unrecognizable_sheet_display_falls_back_to_raw() -> None:
    """When sheet_display has no sheet-code pattern, the raw display is kept."""
    # "现金" has no [A-Z]\d+... pattern → sheet_code falls back to raw display.
    assert _normalize_wp_uri_to_addr_id("WP:E1:现金:B5") == "E1/现金/B5"


# ─── docx / custom_flat WP URI (Req 3.7, 3.11, 12.2) ─────────────────────────

def test_example_docx_wp_uri_normalizes_to_custom_flat() -> None:
    """Real docx registry form WP:{wp}::docx:{text} → {wp}/{wp}/docx:{text}.

    **Validates: Requirements 3.7, 3.11**
    """
    result = _normalize_wp_uri_to_addr_id("WP:A10-1::docx:上市实体")
    assert result == "A10-1/A10-1/docx:上市实体"
    # Post-condition asserted by task: no WP: prefix, contains a "/".
    assert not result.startswith("WP:")
    assert "/" in result


def test_example_custom_flat_empty_sheet_suffix_normalizes() -> None:
    """Empty-sheet custom form WP:{wp}::{suffix} → {wp}/{wp}/{suffix}.

    **Validates: Requirements 3.7, 12.2**
    """
    assert _normalize_wp_uri_to_addr_id("WP:D2::某自定义字段") == "D2/D2/某自定义字段"


def test_example_degenerate_wp_uri_no_suffix_passthrough() -> None:
    """Degenerate WP:{wp}:: (empty sheet AND empty suffix) passes through unchanged.

    Guards the ``_from_docx_placeholders`` derived ``WP:{wp_code}::`` form from
    accidental rewrite (no meaningful addr_id).
    **Validates: Requirements 3.7 (edge case)**
    """
    assert _normalize_wp_uri_to_addr_id("WP:A10-1::") == "WP:A10-1::"


def test_example_wellformed_four_part_unaffected_by_custom_branch() -> None:
    """Well-formed 4-part WP URI still normalizes via the sheet-code path.

    **Validates: Requirements 3.1, 3.10**
    """
    assert _normalize_wp_uri_to_addr_id("WP:D2:明细表D2-2:E100") == "D2/D2-2/E100"
