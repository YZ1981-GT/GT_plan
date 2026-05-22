"""Linkage Panorama Graph Aggregator.

聚合 cross_wp_references.json 为力导向图所需的节点+边结构，并叠加 DB 中的
prefill_stale 状态。本模块为纯计算逻辑，不依赖 FastAPI/SQLAlchemy。

Sprint 0 实测基线（cross_wp_references.json）：
- N_cwr_total = 400 条 references
- N_cwr_with_wp_target = 370 (标准 CWR，target 含 wp_code)
- N_cwr_cross_module = 31 (target 含 target_module 不含 wp_code)
- N_total_unique_nodes = 128 (110 真节点 + 18 模块虚拟节点)
- severity 5 级: blocking/warning/info/recommended/required

设计参考: .kiro/specs/linkage-panorama-graph/design.md v0.2 ADR-6 + ADR-7
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

# Cycle 推断结果合法集合
CYCLE_LITERALS = frozenset(
    {
        # 业务循环
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        # 辅助类
        "A",
        "B",
        "C",
        "S",
        # 特殊类
        "report",
        "note",
        "module",
        "other",
    }
)

# 报表节点前缀（cycle='report'）
_REPORT_PREFIXES = ("BS", "IS", "CFS", "EQ")
# 业务循环 + 辅助首字母（A/B/C/S 兜底接到推断逻辑）
_CYCLE_FIRST_LETTERS = "ABCDEFGHIJKLMNS"


def infer_cycle(wp_code: str) -> str:
    """Cycle 推断函数（前后端共享语义）。

    规则优先级（design v0.2）：
    1. ``__module__`` 前缀 → 'module'
    2. 'BS'/'IS'/'CFS'/'EQ' 前缀 → 'report'
    3. 中文 '附注' 前缀 或 'NOTE' 前缀 → 'note'
    4. 首字母 ∈ {A,B,C,D,E,F,G,H,I,J,K,L,M,N,S} 且首字母后非字母
       （避免 ``BS`` 被误命中为 B、``EQ`` 被误命中为 E）→ 该字母
    5. 其余 → 'other'
    """
    if not wp_code:
        return "other"
    if wp_code.startswith("__module__"):
        return "module"
    cu = wp_code.upper()
    if cu.startswith(_REPORT_PREFIXES):
        return "report"
    if wp_code.startswith("附注") or cu.startswith("NOTE"):
        return "note"
    first = cu[0]
    if first in _CYCLE_FIRST_LETTERS and (len(cu) == 1 or not cu[1].isalpha()):
        return first
    return "other"


def _module_node_id(module_name: str) -> str:
    """将 cross_module target 的 target_module 转换为虚拟节点 id。"""
    return f"__module__{module_name}"


def aggregate_graph_from_cwr(
    references: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """聚合 CWR references 为节点+边结构。

    输入: cross_wp_references.json 的 references 数组
    输出: (nodes, edges)

    节点字段: id, wp_code, cycle, label, is_stale=False (调 overlay_stale_status 后填充),
             degree, is_module (虚拟模块节点 True)
    边字段: id (ref_id), source, target, ref_id, severity, category, description,
           is_stale=False, label
    """
    refs = list(references)

    # 节点收集器：id -> {wp_code, cycle, label, degree, is_module}
    nodes_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    degree_counter: Counter[str] = Counter()

    def _ensure_node(node_id: str, *, label: str, is_module: bool = False) -> None:
        if node_id in nodes_map:
            return
        nodes_map[node_id] = {
            "id": node_id,
            "wp_code": node_id if not is_module else node_id.replace("__module__", ""),
            "cycle": infer_cycle(node_id),
            "label": label,
            "is_stale": False,
            "degree": 0,
            "is_module": is_module,
        }

    for ref in refs:
        source_wp = ref.get("source_wp")
        if not source_wp:
            continue
        _ensure_node(source_wp, label=source_wp, is_module=False)
        ref_id = ref.get("ref_id", "")
        severity = ref.get("severity", "info")
        category = ref.get("category", "")
        description = ref.get("description", "")

        targets = ref.get("targets") or []
        for idx, t in enumerate(targets):
            wp_code = t.get("wp_code")
            if wp_code:
                # 标准 CWR target
                _ensure_node(wp_code, label=wp_code, is_module=False)
                target_id = wp_code
                edge_label = t.get("sheet") or t.get("cell_label") or ""
            else:
                # cross_module 类 target（无 wp_code）
                target_module = t.get("target_module")
                if not target_module:
                    # 既无 wp_code 也无 target_module 的 target 跳过
                    continue
                target_id = _module_node_id(target_module)
                _ensure_node(target_id, label=target_module, is_module=True)
                edge_label = t.get("target_field", "")

            # 边 id 处理：同 ref 多 target 时附加序号防重复
            edge_id = ref_id if len(targets) <= 1 else f"{ref_id}#{idx}"
            edges.append(
                {
                    "id": edge_id,
                    "source": source_wp,
                    "target": target_id,
                    "ref_id": ref_id,
                    "severity": severity,
                    "category": category,
                    "description": description,
                    "is_stale": False,
                    "label": edge_label,
                }
            )
            degree_counter[source_wp] += 1
            degree_counter[target_id] += 1

    # 写入 degree
    for node_id, node in nodes_map.items():
        node["degree"] = degree_counter.get(node_id, 0)

    # 节点排序：按 cycle 字母再按 id，使返回稳定（便于测试）
    nodes = sorted(nodes_map.values(), key=lambda n: (n["cycle"], n["id"]))
    # 边按 id 排序
    edges.sort(key=lambda e: e["id"])

    return nodes, edges


def overlay_stale_status(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    stale_wp_codes: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """将 DB 中的 stale wp_codes 叠加到节点和边。

    规则:
    - 真节点 wp_code ∈ stale_wp_codes → node.is_stale = True
    - 虚拟模块节点（is_module=True）始终 is_stale=False
    - 边 is_stale = (source.is_stale OR target.is_stale)
    """
    stale_set = set(stale_wp_codes)
    node_stale_map: dict[str, bool] = {}
    for node in nodes:
        if node.get("is_module"):
            node["is_stale"] = False
        else:
            node["is_stale"] = node["id"] in stale_set
        node_stale_map[node["id"]] = node["is_stale"]

    for edge in edges:
        edge["is_stale"] = (
            node_stale_map.get(edge["source"], False)
            or node_stale_map.get(edge["target"], False)
        )

    return nodes, edges


def compute_statistics(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    """计算图统计信息。

    返回:
        node_count: 总节点数
        edge_count: 总边数
        stale_node_count: stale 节点数
        stale_edge_count: stale 边数
        blocking_edge_count: blocking 边数（向后兼容）
        severity_distribution: 5 级 severity 分布 dict
        cycle_distribution: cycle 分布 dict
    """
    sev_counter: Counter[str] = Counter()
    cycle_counter: Counter[str] = Counter()
    stale_node_count = 0
    stale_edge_count = 0
    blocking_edge_count = 0

    for node in nodes:
        cycle_counter[node.get("cycle", "other")] += 1
        if node.get("is_stale"):
            stale_node_count += 1

    for edge in edges:
        sev = edge.get("severity", "info")
        sev_counter[sev] += 1
        if sev == "blocking":
            blocking_edge_count += 1
        if edge.get("is_stale"):
            stale_edge_count += 1

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "stale_node_count": stale_node_count,
        "stale_edge_count": stale_edge_count,
        "blocking_edge_count": blocking_edge_count,
        "severity_distribution": dict(sev_counter),
        "cycle_distribution": dict(cycle_counter),
    }


def get_cycle_node_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    """便利函数：返回每个 cycle 的节点数（前端 CycleFilter 选项标注用）。"""
    counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        counts[node.get("cycle", "other")] += 1
    return dict(counts)
