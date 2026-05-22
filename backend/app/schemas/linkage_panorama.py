"""联动全景图 API schema (Requirements 9.x)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """图节点。

    - is_module=True 表示 cross_module 类虚拟节点（id 以 ``__module__`` 开头）
    """

    id: str
    wp_code: str
    cycle: str
    label: str
    is_stale: bool = False
    degree: int = 0
    is_module: bool = False


class GraphEdge(BaseModel):
    """图边。"""

    id: str
    source: str
    target: str
    ref_id: str
    severity: str
    category: str = ""
    description: str = ""
    is_stale: bool = False
    label: str = ""


class GraphStatistics(BaseModel):
    """图统计信息。"""

    node_count: int
    edge_count: int
    stale_node_count: int
    stale_edge_count: int
    blocking_edge_count: int
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    cycle_distribution: dict[str, int] = Field(default_factory=dict)


class GraphDataResponse(BaseModel):
    """联动全景图数据响应。"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    statistics: GraphStatistics
