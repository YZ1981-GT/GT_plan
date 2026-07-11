"""Property-based test for the LinkageGraph build invariant (P10).

Spec: .kiro/specs/acnr-consumer-wiring (design.md Correctness Properties, P10;
tasks.md task 3.4).

Property 10: Graph Build Invariant — WP Nodes Use addr_id
  When ``LinkageGraphBuilder`` constructs its node set from the JSON data
  sources (prefill_formula_mapping / cross_wp_references /
  address_registry_l3_dependencies), every node whose ``module == "WP"`` SHALL
  have a URI in ACNR addr_id form — i.e. it contains a ``/`` separator and does
  NOT carry a ``WP:`` prefix — while every non-WP-domain node (TB/REPORT/NOTE/
  MAPPING/ADJ) SHALL retain its original domain-prefixed URI unchanged.
  **Validates: Requirements 3.11**

Hermetic strategy
  The full ``build()`` coroutine writes an output file and fans out to DB /
  downstream engines. To keep the property fast and DB-free (as task 3.4
  prescribes), we mock the three JSON data sources with random well-formed WP
  entries plus random non-WP (TB) entries, point the module-level ``DATA_DIR``
  at a throwaway directory, and drive the synchronous ``_from_*`` node builders
  that ``build()`` itself calls. The invariant is asserted on the resulting
  ``builder._nodes`` map — the exact structure ``build()`` serialises.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from hypothesis import given, settings
from hypothesis import strategies as st

import app.services.linkage_graph_builder as lgb


# ─── Strategies (well-formed WP / non-WP components, no ':' or '/') ──────────

# Legal wp_code: single clean segment, no ':' / '/'.
_wp_code = st.from_regex(r"\A[A-N]\d{1,2}(?:-\d)?[A-Z]?\Z")

# Sheet code recognised by the builder's _SHEET_CODE_PATTERN.
_sheet_code = st.from_regex(r"\A[A-Z]\d{1,2}(?:-\d{1,2})?[A-Z]?\Z")

# Chinese display prefixes seen in real prefill/cross-wp data (no latin A-Z).
_sheet_prefix = st.sampled_from(["明细表", "审定表", "分析表", "汇总表", ""])

# Cell reference / label: non-empty, no ':' / '/'.
_cell = st.from_regex(r"\A[A-Z]{1,3}\d{1,4}\Z")

# Non-WP (TB) source components fed through prefill formulas.
_tb_code = st.from_regex(r"\A\d{3,4}\Z")
_tb_label = st.sampled_from(["期末余额", "期初余额", "本期发生额", "审定数"])


@st.composite
def _wp_ref(draw: Any) -> dict[str, str]:
    """A single well-formed WP coordinate (wp_code + display sheet + cell)."""
    return {
        "wp_code": draw(_wp_code),
        "sheet": draw(_sheet_prefix) + draw(_sheet_code),
        "cell": draw(_cell),
    }


@st.composite
def _scenario(draw: Any) -> dict[str, Any]:
    """Random content for the three WP-producing JSON data sources."""
    prefill_refs = draw(st.lists(_wp_ref(), min_size=1, max_size=6))
    # Optional TB source per prefill cell (non-WP domain entries).
    tb_refs = draw(
        st.lists(st.tuples(_tb_code, _tb_label), min_size=0, max_size=6)
    )
    cross_refs = draw(
        st.lists(st.tuples(_wp_ref(), _wp_ref()), min_size=0, max_size=5)
    )
    l3_refs = draw(
        st.lists(
            st.tuples(_wp_code, _sheet_code, _cell, _sheet_code, _cell),
            min_size=0,
            max_size=5,
        )
    )

    # prefill_formula_mapping.json
    mappings = []
    for i, ref in enumerate(prefill_refs):
        tb = tb_refs[i] if i < len(tb_refs) else None
        formula = f"=TB('{tb[0]}','{tb[1]}')" if tb else ""
        mappings.append(
            {
                "wp_code": ref["wp_code"],
                "sheet": ref["sheet"],
                "cells": [
                    {"cell_ref": ref["cell"], "formula": formula, "formula_type": "tb"}
                ],
            }
        )
    prefill = {"mappings": mappings}

    # cross_wp_references.json
    references = []
    for src, tgt in cross_refs:
        references.append(
            {
                "source_wp": src["wp_code"],
                "source_sheet": src["sheet"],
                "source_cell_label": src["cell"],
                "severity": "warning",
                "targets": [
                    {
                        "wp_code": tgt["wp_code"],
                        "sheet": tgt["sheet"],
                        "cell_label": tgt["cell"],
                    }
                ],
            }
        )
    cross = {"references": references}

    # address_registry_l3_dependencies.json
    dependencies = []
    for wp_code, s_sheet, s_cell, t_sheet, t_cell in l3_refs:
        dependencies.append(
            {
                "source_wp": wp_code,
                "source_sheet": s_sheet,
                "source_cell": s_cell,
                "target_sheet": t_sheet,
                "target_cell": t_cell,
            }
        )
    l3 = {"dependencies": dependencies}

    return {"prefill": prefill, "cross": cross, "l3": l3}


def _build_nodes(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Write mocked sources to a temp DATA_DIR and run the sync node builders."""
    tmp = Path(tempfile.mkdtemp(prefix="lgb_p10_"))
    (tmp / "prefill_formula_mapping.json").write_text(
        json.dumps(scenario["prefill"], ensure_ascii=False), encoding="utf-8"
    )
    (tmp / "cross_wp_references.json").write_text(
        json.dumps(scenario["cross"], ensure_ascii=False), encoding="utf-8"
    )
    (tmp / "address_registry_l3_dependencies.json").write_text(
        json.dumps(scenario["l3"], ensure_ascii=False), encoding="utf-8"
    )

    original_data_dir = lgb.DATA_DIR
    lgb.DATA_DIR = tmp
    try:
        builder = lgb.LinkageGraphBuilder(db=None)
        # These are exactly the synchronous JSON sources build() invokes.
        builder._from_prefill_mapping()
        builder._from_cross_wp_references()
        builder._from_l3_dependencies()
        return dict(builder._nodes)
    finally:
        lgb.DATA_DIR = original_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


# ─── Property 10: Graph Build Invariant — WP Nodes Use addr_id ───────────────

@settings(max_examples=150, deadline=None)
@given(scenario=_scenario())
def test_p10_wp_nodes_use_addr_id_non_wp_unchanged(scenario: dict[str, Any]) -> None:
    """Property 10: WP nodes are addr_id keyed; non-WP nodes keep original URI.

    **Validates: Requirements 3.11**
    """
    nodes = _build_nodes(scenario)

    saw_wp = False
    for uri, node in nodes.items():
        # The dict key and the node's own uri field agree.
        assert node["uri"] == uri, f"node key/uri mismatch: {uri!r} vs {node!r}"

        if node["module"] == "WP":
            saw_wp = True
            # addr_id form: contains a '/' separator ...
            assert "/" in node["uri"], (
                f"WP node URI missing '/': {node['uri']!r}"
            )
            # ... and NO surviving 'WP:' prefix anywhere in the id.
            assert "WP:" not in node["uri"], (
                f"WP node URI still carries WP: prefix: {node['uri']!r}"
            )
        else:
            # Non-WP domains (TB/REPORT/NOTE/MAPPING/ADJ) keep their original,
            # domain-prefixed URI unchanged.
            assert node["uri"].startswith(node["module"] + ":"), (
                f"non-WP node lost its domain prefix: "
                f"module={node['module']!r} uri={node['uri']!r}"
            )

    # A prefill mapping always yields >=1 WP target node, so the WP branch of
    # the invariant is never vacuously satisfied.
    assert saw_wp, "expected at least one WP-domain node from prefill mappings"


# ─── Concrete example (unit) ─────────────────────────────────────────────────

def test_p10_example_mixed_domains_from_design() -> None:
    """Design example: a WP target fed by a TB source yields one addr_id WP
    node and one unchanged TB node."""
    scenario = {
        "prefill": {
            "mappings": [
                {
                    "wp_code": "D2",
                    "sheet": "明细表D2-2",
                    "cells": [
                        {
                            "cell_ref": "E100",
                            "formula": "=TB('1122','期末余额')",
                            "formula_type": "tb",
                        }
                    ],
                }
            ]
        },
        "cross": {"references": []},
        "l3": {"dependencies": []},
    }
    nodes = _build_nodes(scenario)

    # WP target normalised to addr_id.
    assert "D2/D2-2/E100" in nodes
    assert nodes["D2/D2-2/E100"]["module"] == "WP"

    # TB source retained unchanged.
    assert "TB:1122::期末余额" in nodes
    assert nodes["TB:1122::期末余额"]["module"] == "TB"

    for uri, node in nodes.items():
        if node["module"] == "WP":
            assert "/" in uri and "WP:" not in uri
        else:
            assert uri.startswith(node["module"] + ":")
