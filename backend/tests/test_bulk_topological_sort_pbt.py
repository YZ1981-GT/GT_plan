"""Property-based tests for bulk export/import topological sort (P7–P9).

Spec: .kiro/specs/acnr-consumer-wiring (design.md Correctness Properties P7–P9).

Subject under test: module-level pure function
``app.services.wp_bulk_tab_export._topological_sort`` (task 5.2).

It operates on ``list[dict]`` entries with keys:
  - ``sheet_code``          (str, unique per entry)
  - ``depends_on_sheets``   (list[str], references other sheet_codes)
  - ``import_order``        (int, tiebreaker / fallback sort key)

Property 7: Topological Sort Respects Dependencies
  For any list of entries forming a valid DAG of ``depends_on_sheets``,
  ``_topological_sort()`` produces an ordering where every entry appears AFTER
  all entries it depends on.
  **Validates: Requirements 7.1, 7.2**

Property 8: Topological Sort Stability via import_order
  Scoped (per task 5.2 audit) to flat no-dependency sets: when every entry has
  an empty ``depends_on_sheets``, the output is fully ordered ascending by
  ``import_order`` (the lower import_order appears first). This is the globally
  satisfiable form of "unrelated entries ordered by import_order"; we do NOT
  assert it across dependency chains, where a chain can legitimately force an
  unrelated lower-order node later.
  **Validates: Requirements 7.4**

Property 9: Circular Dependency Fallback
  For any list of entries containing a circular dependency in
  ``depends_on_sheets``, ``_topological_sort()`` returns entries sorted by
  ``import_order`` (numeric fallback) and fires ``logger.error``.
  **Validates: Requirements 7.3**
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st

import app.services.wp_bulk_tab_export as wp_mod
from app.services.wp_bulk_tab_export import _topological_sort


# ─── Strategies ──────────────────────────────────────────────────────────────


@st.composite
def _dag_entries(draw: st.DrawFn) -> list[dict]:
    """Random DAG: node i may only depend on lower-index nodes.

    Assigning each node a topological rank (its index) and only allowing edges
    to lower ranks guarantees the graph is acyclic. Input order is shuffled so
    the topo sort cannot be trivially satisfied by the incoming order.
    """
    n = draw(st.integers(min_value=1, max_value=8))
    codes = [f"S{i}" for i in range(n)]
    # Distinct import_order values (a permutation) — exercises the tiebreaker.
    import_orders = draw(st.permutations(list(range(n))))

    entries: list[dict] = []
    for i in range(n):
        lower = codes[:i]
        if lower:
            deps = draw(
                st.lists(
                    st.sampled_from(lower), unique=True, max_size=len(lower)
                )
            )
        else:
            deps = []
        entries.append(
            {
                "sheet_code": codes[i],
                "depends_on_sheets": deps,
                "import_order": import_orders[i],
            }
        )

    return list(draw(st.permutations(entries)))


@st.composite
def _flat_entries(draw: st.DrawFn) -> list[dict]:
    """Flat set: every entry has NO dependencies, distinct import_order."""
    n = draw(st.integers(min_value=1, max_value=10))
    codes = [f"S{i}" for i in range(n)]
    import_orders = draw(st.permutations(list(range(n))))
    entries = [
        {
            "sheet_code": codes[i],
            "depends_on_sheets": [],
            "import_order": import_orders[i],
        }
        for i in range(n)
    ]
    return list(draw(st.permutations(entries)))


@st.composite
def _cyclic_entries(draw: st.DrawFn) -> list[dict]:
    """Contains a 2-cycle (S0 → S1 → S0) guaranteeing an unresolvable cycle."""
    n = draw(st.integers(min_value=2, max_value=8))
    codes = [f"S{i}" for i in range(n)]
    import_orders = draw(st.permutations(list(range(n))))
    entries = [
        {
            "sheet_code": codes[i],
            "depends_on_sheets": [],
            "import_order": import_orders[i],
        }
        for i in range(n)
    ]
    # Introduce a back edge to form a cycle: S0 depends on S1 and S1 on S0.
    entries[0]["depends_on_sheets"] = ["S1"]
    entries[1]["depends_on_sheets"] = ["S0"]
    return list(draw(st.permutations(entries)))


# ─── Property 7: Topological Sort Respects Dependencies ──────────────────────


@settings(max_examples=150)
@given(entries=_dag_entries())
def test_p7_topological_sort_respects_dependencies(entries: list[dict]) -> None:
    """Every entry appears AFTER all sheets in its depends_on_sheets.

    **Validates: Requirements 7.1, 7.2**
    """
    result = _topological_sort(entries)

    # A valid DAG never triggers the cycle fallback: all entries preserved.
    assert len(result) == len(entries)
    assert {e["sheet_code"] for e in result} == {e["sheet_code"] for e in entries}

    position = {e["sheet_code"]: idx for idx, e in enumerate(result)}
    for e in entries:
        for dep in e["depends_on_sheets"]:
            assert position[dep] < position[e["sheet_code"]], (
                f"{e['sheet_code']} must appear after its dependency {dep}"
            )


# ─── Property 8: Topological Sort Stability via import_order (flat scope) ─────


@settings(max_examples=150)
@given(entries=_flat_entries())
def test_p8_flat_set_ordered_by_import_order(entries: list[dict]) -> None:
    """With no dependencies, output is fully sorted ascending by import_order.

    **Validates: Requirements 7.4**
    """
    result = _topological_sort(entries)

    orders = [e["import_order"] for e in result]
    assert orders == sorted(orders)

    expected_codes = [
        e["sheet_code"] for e in sorted(entries, key=lambda x: x["import_order"])
    ]
    assert [e["sheet_code"] for e in result] == expected_codes


# ─── Property 9: Circular Dependency Fallback ────────────────────────────────


@settings(max_examples=150)
@given(entries=_cyclic_entries())
def test_p9_circular_dependency_fallback(entries: list[dict]) -> None:
    """Cyclic input falls back to import_order numeric sort + logger.error.

    **Validates: Requirements 7.3**
    """
    with mock.patch.object(wp_mod.logger, "error") as mock_error:
        result = _topological_sort(entries)

    expected = sorted(entries, key=lambda e: e.get("import_order", 999))
    assert result == expected
    assert mock_error.called, "logger.error must fire on circular dependency"


# ─── Explicit examples (documentation / regression anchors) ──────────────────


def test_example_linear_chain_orders_dependencies_first() -> None:
    """A → B → C chain: dependency-free A first, dependent C last."""
    entries = [
        {"sheet_code": "C", "depends_on_sheets": ["B"], "import_order": 1},
        {"sheet_code": "A", "depends_on_sheets": [], "import_order": 3},
        {"sheet_code": "B", "depends_on_sheets": ["A"], "import_order": 2},
    ]
    result = _topological_sort(entries)
    assert [e["sheet_code"] for e in result] == ["A", "B", "C"]


def test_example_flat_set_sorted_by_import_order() -> None:
    entries = [
        {"sheet_code": "X", "depends_on_sheets": [], "import_order": 30},
        {"sheet_code": "Y", "depends_on_sheets": [], "import_order": 10},
        {"sheet_code": "Z", "depends_on_sheets": [], "import_order": 20},
    ]
    result = _topological_sort(entries)
    assert [e["sheet_code"] for e in result] == ["Y", "Z", "X"]


def test_example_cycle_falls_back_to_import_order() -> None:
    entries = [
        {"sheet_code": "A", "depends_on_sheets": ["B"], "import_order": 2},
        {"sheet_code": "B", "depends_on_sheets": ["A"], "import_order": 1},
    ]
    with mock.patch.object(wp_mod.logger, "error") as mock_error:
        result = _topological_sort(entries)
    assert [e["sheet_code"] for e in result] == ["B", "A"]
    assert mock_error.called
