"""Property-based tests for linkage_panorama_aggregator.

Feature: linkage-panorama-graph
Properties:
  P1 — node count invariant (Validates Requirements 9.3)
  P2 — edge endpoint validity (Validates Requirements 9.2, 2.1)
  P3 — stale subset invariant (Validates Requirements 8.1, 8.2, 8.5)

每个 property 至少 100 iterations。
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.services.linkage_panorama_aggregator import (
    aggregate_graph_from_cwr,
    overlay_stale_status,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# wp_code 生成策略：业务循环字母 + 1-2 位数字
_wp_code_letter = st.sampled_from(list("ABCDEFGHIJKLMN"))
_wp_code_strategy = st.builds(
    lambda l, n, sub: f"{l}{n}" + (f"-{sub}" if sub else ""),
    _wp_code_letter,
    st.integers(min_value=1, max_value=15),
    st.one_of(st.none(), st.integers(min_value=1, max_value=20)),
)

# severity 5 级
_severity_strategy = st.sampled_from(
    ["blocking", "warning", "info", "recommended", "required"],
)

# target_module 名集合
_module_name_strategy = st.sampled_from(
    [
        "trial_balance",
        "consolidation",
        "disclosure_notes",
        "adjustments",
        "audit_report",
    ],
)


def _standard_target_strategy():
    return st.fixed_dictionaries({
        "wp_code": _wp_code_strategy,
        "sheet": st.text(max_size=10),
    })


def _module_target_strategy():
    return st.fixed_dictionaries({
        "target_module": _module_name_strategy,
        "target_field": st.text(max_size=10),
    })


_target_strategy = st.one_of(_standard_target_strategy(), _module_target_strategy())


def _ref_strategy():
    return st.fixed_dictionaries({
        "ref_id": st.builds(lambda i: f"CW-{i:04d}", st.integers(min_value=1, max_value=9999)),
        "source_wp": _wp_code_strategy,
        "severity": _severity_strategy,
        "category": st.text(max_size=15),
        "description": st.text(max_size=20),
        "targets": st.lists(_target_strategy, min_size=0, max_size=5),
    })


# ---------------------------------------------------------------------------
# P1 — Node count invariant
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(refs=st.lists(_ref_strategy(), min_size=0, max_size=50))
def test_property_1_node_count_invariant(refs):
    """Feature: linkage-panorama-graph, Property 1: node count invariant.

    聚合后 nodes 数量 == 出现过的（source_wp ∪ standard target wp_code ∪ module 虚拟 id）数量；
    nodes 列表中无重复 id。
    """
    nodes, edges = aggregate_graph_from_cwr(refs)
    expected_ids: set[str] = set()
    for r in refs:
        if r.get("source_wp"):
            expected_ids.add(r["source_wp"])
        for t in r.get("targets", []):
            if t.get("wp_code"):
                expected_ids.add(t["wp_code"])
            elif t.get("target_module"):
                expected_ids.add(f"__module__{t['target_module']}")
    actual_ids = {n["id"] for n in nodes}
    assert actual_ids == expected_ids, (
        f"node id set mismatch: missing={expected_ids - actual_ids}, "
        f"extra={actual_ids - expected_ids}"
    )
    # 无重复
    assert len(actual_ids) == len(nodes)


# ---------------------------------------------------------------------------
# P2 — Edge endpoint validity
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(refs=st.lists(_ref_strategy(), min_size=0, max_size=50))
def test_property_2_edge_endpoint_validity(refs):
    """Feature: linkage-panorama-graph, Property 2: edge endpoint validity.

    每条 edge 的 source 和 target 必须存在于 nodes 集合中（无 dangling 引用）。
    """
    nodes, edges = aggregate_graph_from_cwr(refs)
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        assert edge["source"] in node_ids, f"dangling source: {edge['source']}"
        assert edge["target"] in node_ids, f"dangling target: {edge['target']}"


# ---------------------------------------------------------------------------
# P3 — Stale subset invariant
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    refs=st.lists(_ref_strategy(), min_size=1, max_size=30),
    stale_codes_strategy=st.lists(_wp_code_strategy, min_size=0, max_size=20),
)
def test_property_3_stale_subset_invariant(refs, stale_codes_strategy):
    """Feature: linkage-panorama-graph, Property 3: stale subset invariant.

    1. stale 节点 ⊆ 全部节点
    2. stale 边 ⊆ 全部边
    3. edge.is_stale ↔ (source.is_stale OR target.is_stale)
    4. 虚拟模块节点始终非 stale
    """
    nodes, edges = aggregate_graph_from_cwr(refs)
    overlay_stale_status(nodes, edges, stale_codes_strategy)

    node_by_id = {n["id"]: n for n in nodes}
    stale_nodes = [n for n in nodes if n["is_stale"]]
    stale_edges = [e for e in edges if e["is_stale"]]

    # 子集关系（自然成立，但用作骨架）
    assert all(n in nodes for n in stale_nodes)
    assert all(e in edges for e in stale_edges)

    # 模块虚拟节点始终非 stale
    for n in nodes:
        if n.get("is_module"):
            assert n["is_stale"] is False

    # 边 stale ↔ 至少一端 stale
    for edge in edges:
        src_stale = node_by_id[edge["source"]]["is_stale"]
        tgt_stale = node_by_id[edge["target"]]["is_stale"]
        expected = src_stale or tgt_stale
        assert edge["is_stale"] == expected, (
            f"edge {edge['id']} stale mismatch: edge={edge['is_stale']} "
            f"src={src_stale} tgt={tgt_stale}"
        )
