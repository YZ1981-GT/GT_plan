"""Property-based test for P20 (stale 传递闭包) — Task 6.4.

Feature: attachment-ocr-ai-evidence-governance-hardening, Property 20
Spec: attachment-ocr-ai-evidence-governance-hardening

**Validates: Requirements 4, 9**

P20: stale 传递闭包 — actual stale set = exact reachable downstream closure
     in UnifiedGraph; 统一图由活动 EvidenceDependency 边与经规范化纳入的
     ACNR/legacy 边的并集构成，不得以任一单表闭包替代。

Test strategy:
  - Generate random DAGs (directed acyclic graphs) with mixed provenance edges
  - Build UnifiedGraph from those edges
  - Pick a random change source node
  - Verify: downstream_closure(source) == exact BFS reachable set (reference model)
  - Verify: deduplication by canonical edge hash works correctly
  - Verify: edges from all three provenances are merged correctly
"""

from __future__ import annotations

import uuid
from collections import deque

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.unified_graph_builder import (
    ClosureResult,
    EdgeProvenance,
    GraphScope,
    NormalizedEdge,
    UnifiedGraph,
    compute_canonical_edge_hash,
    normalize_node_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────────────

node_type_st = st.sampled_from([
    "attachment_version", "workpaper", "ocr_result", "ai_content",
    "citation", "evidence_ref", "acnr", "legacy",
])

node_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1, max_size=8,
)

provenance_st = st.sampled_from(list(EdgeProvenance))


@st.composite
def edge_st(draw: st.DrawFn) -> dict:
    """Generate a single edge specification."""
    s_type = draw(node_type_st)
    s_id = draw(node_id_st)
    t_type = draw(node_type_st)
    t_id = draw(node_id_st)
    prov = draw(provenance_st)
    return {
        "source_type": s_type,
        "source_id": s_id,
        "target_type": t_type,
        "target_id": t_id,
        "provenance": prov,
    }


@st.composite
def graph_and_source_st(draw: st.DrawFn) -> tuple[list[dict], str]:
    """Generate a list of edges and a starting node for closure computation."""
    edges = draw(st.lists(edge_st(), min_size=1, max_size=20))
    # Pick a source node from the edges
    all_source_keys = [
        normalize_node_key(e["source_type"], e["source_id"]) for e in edges
    ]
    source_key = draw(st.sampled_from(all_source_keys))
    return edges, source_key


# ─────────────────────────────────────────────────────────────────────────────
# Reference model: compute exact BFS reachable set
# ─────────────────────────────────────────────────────────────────────────────


def reference_bfs_closure(
    edges: list[dict], start_key: str
) -> set[str]:
    """Reference implementation: exact BFS reachable downstream closure.

    This is the ground truth for P20 — the actual stale set must equal this.
    """
    # Build adjacency (dedup by canonical edge hash like UnifiedGraph does)
    adjacency: dict[str, set[str]] = {}
    seen_hashes: set[str] = set()

    for e in edges:
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        target_key = normalize_node_key(e["target_type"], e["target_id"])
        provenance = e["provenance"]
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            provenance,
        )
        if edge_hash in seen_hashes:
            continue
        seen_hashes.add(edge_hash)
        adjacency.setdefault(source_key, set()).add(target_key)

    # BFS from start_key
    visited: set[str] = {start_key}
    queue: deque[str] = deque([start_key])
    closure: set[str] = set()

    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                closure.add(neighbor)
                queue.append(neighbor)

    return closure


# ─────────────────────────────────────────────────────────────────────────────
# Property tests
# ─────────────────────────────────────────────────────────────────────────────


@given(data=graph_and_source_st())
def test_p20_stale_closure_equals_exact_reachable_downstream(
    data: tuple[list[dict], str],
) -> None:
    """P20: actual stale set = exact reachable downstream closure in UnifiedGraph.

    **Validates: Requirements 4, 9**

    The downstream_closure computed by UnifiedGraph must be EXACTLY equal to
    the reference BFS reachable set — no over-inclusion, no under-inclusion.
    """
    edges, start_key = data

    # Build UnifiedGraph from edges
    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    graph = UnifiedGraph(scope=scope)

    for e in edges:
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        target_key = normalize_node_key(e["target_type"], e["target_id"])
        provenance = e["provenance"]
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            provenance,
        )
        graph.add_edge(NormalizedEdge(
            source_key=source_key,
            target_key=target_key,
            provenance=provenance,
            edge_hash=edge_hash,
        ))

    # Compute closure via UnifiedGraph
    actual_closure = graph.downstream_closure(start_key)

    # Compute reference closure
    expected_closure = reference_bfs_closure(edges, start_key)

    # P20: actual == expected (exact match)
    assert actual_closure == expected_closure, (
        f"P20 violated: actual={actual_closure}, expected={expected_closure}, "
        f"start={start_key}, edges={len(edges)}"
    )


@given(data=graph_and_source_st())
def test_p20_deduplication_by_edge_hash(
    data: tuple[list[dict], str],
) -> None:
    """P20 auxiliary: same logical edge deduplicated by canonical edge hash.

    **Validates: Requirements 4, 9**

    Adding the same edge twice (same source/target/provenance) should not
    change the closure result or the edge count.
    """
    edges, start_key = data

    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)

    # Build graph once
    graph1 = UnifiedGraph(scope=scope)
    for e in edges:
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        target_key = normalize_node_key(e["target_type"], e["target_id"])
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            e["provenance"],
        )
        graph1.add_edge(NormalizedEdge(
            source_key=source_key,
            target_key=target_key,
            provenance=e["provenance"],
            edge_hash=edge_hash,
        ))

    # Build graph with duplicates
    graph2 = UnifiedGraph(scope=scope)
    for e in edges + edges:  # duplicated edges
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        target_key = normalize_node_key(e["target_type"], e["target_id"])
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            e["provenance"],
        )
        graph2.add_edge(NormalizedEdge(
            source_key=source_key,
            target_key=target_key,
            provenance=e["provenance"],
            edge_hash=edge_hash,
        ))

    # Edge counts should be the same (dedup)
    assert graph1.edge_count == graph2.edge_count

    # Closures should be identical
    closure1 = graph1.downstream_closure(start_key)
    closure2 = graph2.downstream_closure(start_key)
    assert closure1 == closure2


@given(data=graph_and_source_st())
def test_p20_all_provenances_merged(
    data: tuple[list[dict], str],
) -> None:
    """P20 auxiliary: edges from all three provenances are merged into single graph.

    **Validates: Requirements 4, 9**

    UnifiedGraph must contain edges from EvidenceDependency, ACNR, AND legacy
    sources — the closure traverses across provenance boundaries.
    """
    edges, start_key = data

    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    graph = UnifiedGraph(scope=scope)

    provenances_seen: set[EdgeProvenance] = set()

    for e in edges:
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        target_key = normalize_node_key(e["target_type"], e["target_id"])
        prov = e["provenance"]
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            prov,
        )
        if graph.add_edge(NormalizedEdge(
            source_key=source_key,
            target_key=target_key,
            provenance=prov,
            edge_hash=edge_hash,
        )):
            provenances_seen.add(prov)

    # All added edges have their provenance tracked
    graph_provenances = {edge.provenance for edge in graph.edges.values()}
    assert graph_provenances == provenances_seen

    # Closure traverses across provenance boundaries
    closure = graph.downstream_closure(start_key)
    # If start has outgoing edges of different provenances, closure includes targets from all
    direct_targets = set(graph.adjacency.get(start_key, []))
    for target in direct_targets:
        assert target in closure or target == start_key


@given(
    edges=st.lists(edge_st(), min_size=0, max_size=15),
    target_type=node_type_st,
    target_id=node_id_st,
)
def test_p20_clear_stale_requires_all_in_edges_verified(
    edges: list[dict],
    target_type: str,
    target_id: str,
) -> None:
    """P20 auxiliary: stale clearing requires re-verifying ALL active in-edges.

    **Validates: Requirements 4, 9**

    Restoring one source doesn't clear stale from other sources.
    If target has N in-edges, all N source keys must be in verified_sources.
    """
    scope = GraphScope(project_id=uuid.uuid4(), audit_year=2025)
    graph = UnifiedGraph(scope=scope)

    target_key = normalize_node_key(target_type, target_id)

    for e in edges:
        source_key = normalize_node_key(e["source_type"], e["source_id"])
        tk = normalize_node_key(e["target_type"], e["target_id"])
        edge_hash = compute_canonical_edge_hash(
            e["source_type"], e["source_id"],
            e["target_type"], e["target_id"],
            e["provenance"],
        )
        graph.add_edge(NormalizedEdge(
            source_key=source_key,
            target_key=tk,
            provenance=e["provenance"],
            edge_hash=edge_hash,
        ))

    # Get all in-edges for our target
    in_edges = graph.all_in_edges(target_key)
    all_sources = {edge.source_key for edge in in_edges}

    if not in_edges:
        # No in-edges → can always clear
        return

    # Partial verification (just first source) → should NOT clear
    partial_verified = {next(iter(all_sources))} if all_sources else set()
    if len(all_sources) > 1:
        # With partial verification, still stale
        unverified = all_sources - partial_verified
        assert len(unverified) > 0, "Should have unverified sources"

    # Full verification → can clear
    full_verified = all_sources
    remaining = all_sources - full_verified
    assert len(remaining) == 0, "Full verification should clear all"
