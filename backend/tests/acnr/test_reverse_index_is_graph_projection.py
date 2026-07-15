"""Property 10: 反向索引 == graph 反向投影 (PBT)

验证 FormulaReverseIndex.build_from_graph(graph_builder) 产出的
dependents(target) == graph_builder.predecessors(target)。

即：反向索引的 query 结果与 LinkageGraphBuilder.predecessors 方法的输出
完全等价——两者来自同一份边数据的不同视角。

**Validates: Requirements 1.2**

Testing framework: hypothesis
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Ensure backend is importable
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.formula_reverse_index import FormulaReverseIndex  # noqa: E402
from app.services.linkage_graph_builder import LinkageGraphBuilder  # noqa: E402


# ─── Strategies ──────────────────────────────────────────────────────────────

# addr_id 格式：{parent}/{sheet}/{coordinate}（wp 域）
_wp_code = st.sampled_from(["D1", "D2", "D3", "F1", "G1", "H1", "K1", "K2", "L1"])
_sheet_code = st.builds(
    lambda wp, n: f"{wp}-{n}",
    _wp_code,
    st.integers(min_value=1, max_value=9),
)
_cell_ref = st.builds(
    lambda c, r: f"{c}{r}",
    st.sampled_from(["A", "B", "C", "D", "E", "F"]),
    st.integers(min_value=1, max_value=200),
)

# 生成 canonical addr_id (wp 域)
_addr_id = st.builds(
    lambda wp, sh, cell: f"{wp}/{sh}/{cell}",
    _wp_code,
    _sheet_code,
    _cell_ref,
)

# 非 wp 域 URI
_tb_uri = st.builds(
    lambda code, label: f"TB:{code}::{label}",
    st.sampled_from(["1001", "1002", "1122", "2211", "6001"]),
    st.sampled_from(["期末余额", "期初余额", "借方发生额"]),
)
_report_uri = st.builds(
    lambda code: f"REPORT:{code}::",
    st.sampled_from(["BS-001", "BS-009", "IS-003", "IS-010"]),
)

_any_uri = st.one_of(_addr_id, _tb_uri, _report_uri)

# Edge type and severity
_edge_type = st.sampled_from(["data_flow", "reverse_ref", "intra_wp", "mapping"])
_severity = st.sampled_from(["blocking", "warning", "info"])

# An edge dict
_edge = st.builds(
    lambda src, tgt, et, sev: {
        "source": src,
        "target": tgt,
        "type": et,
        "severity": sev,
    },
    _any_uri,
    _any_uri,
    _edge_type,
    _severity,
).filter(lambda e: e["source"] != e["target"])  # no self-loops

# A list of edges (small graph)
_edges_list = st.lists(_edge, min_size=1, max_size=20)


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestReverseIndexIsGraphProjection:
    """Property 10: 反向索引 == graph 反向投影 — PBT dependents == predecessors"""

    @given(edges=_edges_list)
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_build_from_graph_matches_predecessors(
        self, edges: list[dict[str, str]]
    ):
        """build_from_graph 产出的反向索引 == predecessors 对每个 target 的输出。

        **Validates: Requirements 1.2**

        Property: 对于图中的每个 target 节点 t，
        FormulaReverseIndex.build_from_graph(builder) 产出的 index[t]（去重排序后）
        == builder.predecessors(t)（去重排序后）。
        """
        # Build a graph manually
        builder = LinkageGraphBuilder(db=None)
        builder._edges = list(edges)

        # Also register nodes
        for e in edges:
            builder._ensure_node(
                e["source"], *builder._parse_uri_parts(e["source"])
            )
            builder._ensure_node(
                e["target"], *builder._parse_uri_parts(e["target"])
            )

        # Build reverse index from the graph
        rev_index = FormulaReverseIndex(db=None)
        index_dict = rev_index.build_from_graph(builder)

        # Collect all unique targets from the graph edges
        all_targets: set[str] = set()
        for e in edges:
            all_targets.add(e["target"])

        # Verify equivalence: for each target, index[target] == predecessors(target)
        for target in all_targets:
            from_index = sorted(set(index_dict.get(target, [])))
            from_predecessors = sorted(builder.predecessors(target))
            assert from_index == from_predecessors, (
                f"Mismatch for target={target!r}: "
                f"index={from_index} vs predecessors={from_predecessors}"
            )

    @given(edges=_edges_list, query_target=_any_uri)
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_predecessors_absent_target_returns_empty(
        self, edges: list[dict[str, str]], query_target: str
    ):
        """predecessors() 对不在图中作为 target 的节点返回空列表。

        **Validates: Requirements 1.2**

        注意：FormulaReverseIndex.query() 有前缀匹配功能（设计如此），
        所以这里只验证 predecessors() 方法的精确匹配行为。
        """
        builder = LinkageGraphBuilder(db=None)
        builder._edges = list(edges)
        for e in edges:
            builder._ensure_node(
                e["source"], *builder._parse_uri_parts(e["source"])
            )
            builder._ensure_node(
                e["target"], *builder._parse_uri_parts(e["target"])
            )

        # If query_target is not a target in the graph, predecessors should return empty
        targets_in_graph = {e["target"] for e in edges}
        if query_target not in targets_in_graph:
            from_predecessors = builder.predecessors(query_target)
            assert from_predecessors == [], (
                f"Expected empty predecessors for absent target {query_target!r}, "
                f"got {from_predecessors}"
            )

    @given(edges=_edges_list)
    @settings(
        max_examples=5,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_get_edges_for_returns_outgoing_edges(
        self, edges: list[dict[str, str]]
    ):
        """get_edges_for(source) 返回从 source 出发的所有边。

        **Validates: Requirements 1.2**
        """
        builder = LinkageGraphBuilder(db=None)
        builder._edges = list(edges)
        for e in edges:
            builder._ensure_node(
                e["source"], *builder._parse_uri_parts(e["source"])
            )
            builder._ensure_node(
                e["target"], *builder._parse_uri_parts(e["target"])
            )

        # Pick all unique sources
        all_sources: set[str] = {e["source"] for e in edges}

        for source in all_sources:
            result = builder.get_edges_for(source)
            expected = [e for e in edges if e["source"] == source]
            assert len(result) == len(expected), (
                f"get_edges_for({source!r}): got {len(result)} edges, "
                f"expected {len(expected)}"
            )
            # Each returned edge should have the correct source
            for e in result:
                assert e["source"] == source
