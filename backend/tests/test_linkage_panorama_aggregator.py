"""Tests for linkage_panorama_aggregator (Requirements 9.2, 9.3, 9.8, 9.9).

覆盖：
- infer_cycle 全部分支（D~N / A/B/C/S / report / note / module / other）
- aggregate_graph_from_cwr 标准 ref / cross_module ref / 多 target
- overlay_stale_status 节点+边叠加 / 虚拟模块节点不 stale
- compute_statistics 5 级 severity 分布
- get_cycle_node_counts

测试断言全部基于运行时聚合结果（不硬编码 128/370 等字面量）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.linkage_panorama_aggregator import (
    aggregate_graph_from_cwr,
    compute_statistics,
    get_cycle_node_counts,
    infer_cycle,
    overlay_stale_status,
)

# ---------------------------------------------------------------------------
# infer_cycle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wp_code, expected",
    [
        # 业务循环
        ("D1", "D"),
        ("D2-1", "D"),
        ("E1", "E"),
        ("F2-1", "F"),
        ("G7", "G"),
        ("H1-13", "H"),
        ("I3-2", "I"),
        ("J1-2", "J"),
        ("K8-1", "K"),
        ("L5-3", "L"),
        ("M6-2", "M"),
        ("N5-1", "N"),
        # 辅助类
        ("A5", "A"),
        ("B15", "B"),
        ("C2-1", "C"),
        ("S5", "S"),
        # 报表（避免 BS/EQ 误命中 B/E）
        ("BS-1", "report"),
        ("BS", "report"),
        ("IS-3", "report"),
        ("CFS", "report"),
        ("EQ-2", "report"),
        # 附注
        ("附注-资产", "note"),
        ("NOTE3", "note"),
        # 模块
        ("__module__trial_balance", "module"),
        ("__module__consolidation", "module"),
        # 兜底
        ("PL", "other"),
        ("TB", "other"),
        ("REPORT", "other"),
        ("T1", "other"),
        ("disclosure", "other"),
        ("", "other"),
    ],
)
def test_infer_cycle_branches(wp_code, expected):
    """infer_cycle 各分支均按 design v0.2 规则正确归类。"""
    assert infer_cycle(wp_code) == expected


# ---------------------------------------------------------------------------
# aggregate_graph_from_cwr
# ---------------------------------------------------------------------------


def test_aggregate_empty_refs_returns_empty_graph():
    nodes, edges = aggregate_graph_from_cwr([])
    assert nodes == []
    assert edges == []


def test_aggregate_single_standard_ref_yields_two_nodes_one_edge():
    refs = [
        {
            "ref_id": "CW-001",
            "source_wp": "H1",
            "severity": "blocking",
            "category": "depreciation",
            "description": "折旧分摊",
            "targets": [{"wp_code": "K8", "sheet": "审定表K8-1"}],
        }
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    node_ids = {n["id"] for n in nodes}
    assert node_ids == {"H1", "K8"}
    assert len(edges) == 1
    edge = edges[0]
    assert edge["source"] == "H1"
    assert edge["target"] == "K8"
    assert edge["severity"] == "blocking"
    assert edge["ref_id"] == "CW-001"


def test_aggregate_cross_module_target_creates_virtual_node():
    """target 含 target_module 不含 wp_code → 生成 ``__module__{module}`` 虚拟节点。"""
    refs = [
        {
            "ref_id": "CW-059",
            "source_wp": "B15",
            "severity": "recommended",
            "category": "cross_module",
            "targets": [
                {
                    "target_module": "trial_balance",
                    "target_field": "materiality_level",
                }
            ],
        }
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    node_by_id = {n["id"]: n for n in nodes}
    assert "B15" in node_by_id
    assert "__module__trial_balance" in node_by_id
    module_node = node_by_id["__module__trial_balance"]
    assert module_node["is_module"] is True
    assert module_node["cycle"] == "module"
    assert module_node["label"] == "trial_balance"
    assert len(edges) == 1
    assert edges[0]["target"] == "__module__trial_balance"


def test_aggregate_skips_target_without_wp_code_and_module():
    refs = [
        {
            "ref_id": "CW-X",
            "source_wp": "H1",
            "severity": "info",
            "targets": [{"sheet": "孤立 sheet"}],
        }
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    # source 节点仍生成，但无边
    assert {n["id"] for n in nodes} == {"H1"}
    assert edges == []


def test_aggregate_multi_target_yields_unique_edge_ids():
    """同 ref_id 多 target 时，edge id 附加 ``#idx`` 避免重复。"""
    refs = [
        {
            "ref_id": "CW-100",
            "source_wp": "H1",
            "severity": "warning",
            "targets": [
                {"wp_code": "K8"},
                {"wp_code": "K9"},
                {"wp_code": "F2"},
            ],
        }
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    edge_ids = [e["id"] for e in edges]
    assert len(edge_ids) == 3
    assert len(set(edge_ids)) == 3, f"edge ids should be unique, got {edge_ids}"
    # 每条边的 ref_id 仍指向原始 CW-100
    assert all(e["ref_id"] == "CW-100" for e in edges)


def test_aggregate_degree_calculation():
    """节点 degree 应等于关联边数（出度+入度）。"""
    refs = [
        {"ref_id": "R1", "source_wp": "A", "severity": "info", "targets": [{"wp_code": "B"}]},
        {"ref_id": "R2", "source_wp": "A", "severity": "info", "targets": [{"wp_code": "C"}]},
        {"ref_id": "R3", "source_wp": "C", "severity": "info", "targets": [{"wp_code": "B"}]},
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    deg = {n["id"]: n["degree"] for n in nodes}
    assert deg["A"] == 2  # 2 出
    assert deg["B"] == 2  # 2 入
    assert deg["C"] == 2  # 1 入 + 1 出


# ---------------------------------------------------------------------------
# overlay_stale_status
# ---------------------------------------------------------------------------


def test_overlay_stale_marks_nodes_and_edges():
    refs = [
        {"ref_id": "R1", "source_wp": "H1", "severity": "blocking", "targets": [{"wp_code": "K8"}]},
        {"ref_id": "R2", "source_wp": "D2", "severity": "warning", "targets": [{"wp_code": "K9"}]},
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    overlay_stale_status(nodes, edges, ["H1"])
    node_by_id = {n["id"]: n for n in nodes}
    assert node_by_id["H1"]["is_stale"] is True
    assert node_by_id["K8"]["is_stale"] is False
    edge_h1_k8 = next(e for e in edges if e["source"] == "H1")
    edge_d2_k9 = next(e for e in edges if e["source"] == "D2")
    assert edge_h1_k8["is_stale"] is True  # source stale → 边 stale
    assert edge_d2_k9["is_stale"] is False


def test_overlay_stale_target_stale_marks_edge_stale():
    refs = [{"ref_id": "R1", "source_wp": "A", "severity": "info", "targets": [{"wp_code": "B"}]}]
    nodes, edges = aggregate_graph_from_cwr(refs)
    overlay_stale_status(nodes, edges, ["B"])
    assert edges[0]["is_stale"] is True


def test_overlay_stale_skips_module_nodes():
    """虚拟模块节点始终 is_stale=False，即使 stale_set 包含同名 module。"""
    refs = [
        {
            "ref_id": "R1",
            "source_wp": "B15",
            "severity": "recommended",
            "targets": [{"target_module": "trial_balance"}],
        }
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    overlay_stale_status(nodes, edges, ["__module__trial_balance", "trial_balance"])
    module_node = next(n for n in nodes if n["is_module"])
    assert module_node["is_stale"] is False


# ---------------------------------------------------------------------------
# compute_statistics
# ---------------------------------------------------------------------------


def test_compute_statistics_severity_5_levels():
    refs = [
        {"ref_id": "R1", "source_wp": "A", "severity": "blocking", "targets": [{"wp_code": "B"}]},
        {"ref_id": "R2", "source_wp": "A", "severity": "warning", "targets": [{"wp_code": "C"}]},
        {"ref_id": "R3", "source_wp": "A", "severity": "info", "targets": [{"wp_code": "D"}]},
        {"ref_id": "R4", "source_wp": "A", "severity": "recommended", "targets": [{"wp_code": "E"}]},
        {"ref_id": "R5", "source_wp": "A", "severity": "required", "targets": [{"wp_code": "F"}]},
    ]
    nodes, edges = aggregate_graph_from_cwr(refs)
    stats = compute_statistics(nodes, edges)
    assert stats["edge_count"] == 5
    assert stats["severity_distribution"] == {
        "blocking": 1,
        "warning": 1,
        "info": 1,
        "recommended": 1,
        "required": 1,
    }
    assert stats["blocking_edge_count"] == 1


# ---------------------------------------------------------------------------
# 全量 CWR 回归（baseline 校验，使用运行时表达式而非字面量）
# ---------------------------------------------------------------------------


_CWR_FILE = Path(__file__).resolve().parents[1] / "data" / "cross_wp_references.json"


def _load_full_cwr() -> list[dict]:
    with _CWR_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["references"]


def test_full_cwr_aggregation_uses_runtime_baseline():
    """全量 CWR 聚合后节点数/边数 == 数据计算值（运行时表达式，不硬编码）。"""
    refs = _load_full_cwr()

    # 运行时计算 expected 值（不硬编码）
    expected_unique_wp_codes: set[str] = set()
    expected_unique_modules: set[str] = set()
    expected_edges = 0
    for r in refs:
        if r.get("source_wp"):
            expected_unique_wp_codes.add(r["source_wp"])
        for t in r.get("targets", []):
            if t.get("wp_code"):
                expected_unique_wp_codes.add(t["wp_code"])
                expected_edges += 1
            elif t.get("target_module"):
                expected_unique_modules.add(t["target_module"])
                expected_edges += 1
    expected_total_nodes = len(expected_unique_wp_codes) + len(expected_unique_modules)

    nodes, edges = aggregate_graph_from_cwr(refs)
    stats = compute_statistics(nodes, edges)

    assert stats["node_count"] == expected_total_nodes
    assert stats["edge_count"] == expected_edges
    # severity 分布健康度：blocking 不应为 0
    assert stats["severity_distribution"].get("blocking", 0) > 0


def test_full_cwr_no_dangling_edges():
    """每条边的 source/target 必存在于节点集合（引用完整性）。"""
    refs = _load_full_cwr()
    nodes, edges = aggregate_graph_from_cwr(refs)
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        assert edge["source"] in node_ids, f"dangling source {edge['source']}"
        assert edge["target"] in node_ids, f"dangling target {edge['target']}"


def test_full_cwr_cycle_distribution_includes_aux_classes():
    """全量聚合后 cycle 分布应包含 A/B/C/S 辅助类（不被错误归到 other）。"""
    refs = _load_full_cwr()
    nodes, _ = aggregate_graph_from_cwr(refs)
    counts = get_cycle_node_counts(nodes)
    # 至少应有 A/B/C/S 各 ≥ 1 节点（real data 实测）
    for cycle in ("A", "B", "C", "S"):
        assert counts.get(cycle, 0) > 0, f"cycle {cycle} should have nodes, got {counts}"
    # module 类节点应来自 cross_module 类 target
    assert counts.get("module", 0) > 0
