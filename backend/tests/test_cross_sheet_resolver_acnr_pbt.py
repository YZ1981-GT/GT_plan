"""Property-based tests for CrossSheetResolver ACNR integration (P1–P3).

Spec: .kiro/specs/acnr-consumer-wiring (design.md Correctness Properties P1–P3).

Property 1: ACNR Resolve Fallback Preserves Response Contract
  For any input and any full_resolve outcome (found=true / found=false /
  exception), resolve() always returns a valid RefChainResponse with the same
  field schema.
  **Validates: Requirements 1.5, 1.6**

Property 2: addr_id Used on ACNR Hit
  When full_resolve returns found=true + non-empty addr_id, the RefChainNode.uri
  equals that addr_id and resolve_missed is False.
  **Validates: Requirements 1.2**

Property 3: Snapshot Fallback on ACNR Miss
  When full_resolve returns found=false or raises, the node uses snapshot
  fallback (sheet!cell) and resolve_missed=True.
  **Validates: Requirements 1.3, 1.6**

Testing note (per task 1.2): `_sync_resolve` returns None whenever a running
event loop is present, so ACNR-hit behavior cannot be exercised via a real
event loop. These tests monkeypatch `_sync_resolve` in the resolver module to
return controlled ResolveResult values (or raise), which is the canonical seam
for driving the three full_resolve outcomes deterministically.
"""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import given, settings
from hypothesis import strategies as st

import app.services.custom_query.cross_sheet_resolver as csr_mod
from app.services.custom_query.cross_sheet_resolver import (
    CrossSheetResolver,
    RefChainNode,
    RefChainResponse,
    _cell_ref_to_indices,
)
from app.services.acnr.resolver import ResolveResult


# ─── Strategies ──────────────────────────────────────────────────────────────

# Valid cell reference: 1-3 column letters + row number (matches ^[A-Z]+\d+$)
_col_st = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=3)
_row_st = st.integers(min_value=1, max_value=9999)
cell_ref_st = st.builds(lambda c, r: f"{c}{r}", _col_st, _row_st)

# Sheet names: letters, digits, dashes and Chinese; must be non-blank and free of '!'
_sheet_alphabet = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Lo"),
    whitelist_characters="-_",
)
sheet_name_st = (
    st.text(alphabet=_sheet_alphabet, min_size=1, max_size=16)
    .map(lambda s: s.strip())
    .filter(lambda s: s != "" and "!" not in s)
)

# Non-empty addr_id for hit cases (mimics "{wp_code}/{sheet_code}/{cell}")
addr_id_st = (
    st.text(min_size=1, max_size=24)
    .map(lambda s: s.strip())
    .filter(lambda s: s != "")
)


def _snapshot_with_formula(
    sheet_name: str, cell_ref: str, ref_sheet: str, ref_cell: str
) -> dict:
    """Build a parsed_data snapshot where sheet!cell contains a cross-sheet formula.

    Exercises BFS traversal (root node → one referenced node).
    """
    row_idx, col_idx = _cell_ref_to_indices(cell_ref)
    if row_idx is None or col_idx is None:
        return {}
    return {
        "univer_snapshot": {
            "sheets": [
                {
                    "name": sheet_name,
                    "cellData": {
                        str(row_idx): {
                            str(col_idx): {"f": f"={ref_sheet}!{ref_cell}"}
                        }
                    },
                }
            ]
        }
    }


# parsed_data variety: None, empty dict, empty snapshot, or a formula-bearing snapshot
parsed_data_st = st.one_of(
    st.none(),
    st.just({}),
    st.just({"univer_snapshot": {"sheets": []}}),
    st.builds(
        _snapshot_with_formula,
        sheet_name_st,
        cell_ref_st,
        sheet_name_st,
        cell_ref_st,
    ),
)


# ─── Fake _sync_resolve factories ────────────────────────────────────────────


def _make_hit(addr_id: str):
    def _fake(*, formula_ref=None, uri=None, project_id=None):
        return ResolveResult(found=True, addr_id=addr_id)

    return _fake


def _fake_miss(*, formula_ref=None, uri=None, project_id=None):
    return ResolveResult(found=False)


def _fake_none(*, formula_ref=None, uri=None, project_id=None):
    return None


def _fake_raise(*, formula_ref=None, uri=None, project_id=None):
    raise RuntimeError("simulated full_resolve failure")


# ─── Contract assertion helper ───────────────────────────────────────────────


def _assert_valid_response(resp: object) -> None:
    """Assert resp conforms to the RefChainResponse schema (field types intact)."""
    assert isinstance(resp, RefChainResponse)
    assert isinstance(resp.chain, list)
    assert isinstance(resp.has_cycle, bool)
    assert resp.truncated_at_depth is None or isinstance(resp.truncated_at_depth, int)
    for node in resp.chain:
        assert isinstance(node, RefChainNode)
        assert isinstance(node.depth, int)
        assert isinstance(node.uri, str) and node.uri != ""
        assert isinstance(node.truncated, bool)
        assert isinstance(node.cycle, bool)
        assert isinstance(node.missing, bool)
        assert isinstance(node.resolve_missed, bool)


# ─── Property 1: ACNR Resolve Fallback Preserves Response Contract ───────────
# Validates: Requirements 1.5, 1.6


@settings(max_examples=200, deadline=None)
@given(
    parsed_data=parsed_data_st,
    sheet_name=sheet_name_st,
    cell_ref=cell_ref_st,
    addr_id=addr_id_st,
    outcome=st.sampled_from(["hit", "miss", "none", "raise"]),
    project_id=st.one_of(st.none(), st.text(min_size=1, max_size=8)),
)
def test_p1_resolve_preserves_response_contract(
    parsed_data, sheet_name, cell_ref, addr_id, outcome, project_id
):
    """For any input and any full_resolve outcome, resolve() returns a valid
    RefChainResponse with the same field schema (no exceptions bubble up)."""
    fakes = {
        "hit": _make_hit(addr_id),
        "miss": _fake_miss,
        "none": _fake_none,
        "raise": _fake_raise,
    }
    resolver = CrossSheetResolver(project_id=project_id)
    with patch.object(csr_mod, "_sync_resolve", fakes[outcome]):
        resp = resolver.resolve(parsed_data, sheet_name, cell_ref)

    _assert_valid_response(resp)


# ─── Property 2: addr_id Used on ACNR Hit ────────────────────────────────────
# Validates: Requirements 1.2


@settings(max_examples=200, deadline=None)
@given(
    sheet_name=sheet_name_st,
    cell_ref=cell_ref_st,
    addr_id=addr_id_st,
    project_id=st.one_of(st.none(), st.text(min_size=1, max_size=8)),
)
def test_p2_addr_id_used_on_acnr_hit(sheet_name, cell_ref, addr_id, project_id):
    """When full_resolve returns found=true with a non-empty addr_id, the root
    RefChainNode.uri equals that addr_id and resolve_missed is False."""
    # parsed_data=None → single root node (no cross-sheet formula to traverse),
    # so the chain has exactly one node whose uri reflects the ACNR hit.
    resolver = CrossSheetResolver(project_id=project_id)
    with patch.object(csr_mod, "_sync_resolve", _make_hit(addr_id)):
        resp = resolver.resolve(None, sheet_name, cell_ref)

    _assert_valid_response(resp)
    assert len(resp.chain) == 1
    node = resp.chain[0]
    assert node.uri == addr_id
    assert node.resolve_missed is False


# ─── Property 3: Snapshot Fallback on ACNR Miss ──────────────────────────────
# Validates: Requirements 1.3, 1.6


@settings(max_examples=200, deadline=None)
@given(
    sheet_name=sheet_name_st,
    cell_ref=cell_ref_st,
    outcome=st.sampled_from(["miss", "none", "raise"]),
    project_id=st.one_of(st.none(), st.text(min_size=1, max_size=8)),
)
def test_p3_snapshot_fallback_on_acnr_miss(
    sheet_name, cell_ref, outcome, project_id
):
    """When full_resolve returns found=false or raises, the node uses snapshot
    fallback (sheet!cell) with resolve_missed=True; BFS continues uninterrupted."""
    fakes = {"miss": _fake_miss, "none": _fake_none, "raise": _fake_raise}
    resolver = CrossSheetResolver(project_id=project_id)
    with patch.object(csr_mod, "_sync_resolve", fakes[outcome]):
        resp = resolver.resolve(None, sheet_name, cell_ref)

    _assert_valid_response(resp)
    assert len(resp.chain) == 1
    node = resp.chain[0]
    # resolve() upper-cases cell_ref before building the fallback uri
    assert node.uri == f"{sheet_name}!{cell_ref.upper()}"
    assert node.resolve_missed is True
