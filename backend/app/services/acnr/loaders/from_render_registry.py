"""Loader: workpaper_render_registry → component_type + upstream/downstream 边。

读取 `workpaper_render_registry.json`，提取：
1. component_type（render_type + module 构成前端渲染标识）
2. upstream/downstream 边（L4 第 6 边源，端点 normalize 为 addr_id）

Requirements: 1.1, 22.4
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services import workpaper_render_registry_service as registry

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class RenderRegistryData:
    """render_registry loader 输出。"""

    # {wp_code → component_type (如 "html_procedure")}
    component_types: dict[str, str] = field(default_factory=dict)
    # {wp_code → render_type}
    render_types: dict[str, str] = field(default_factory=dict)
    # L4 边源：[(source_addr_id, target_addr_id, edge_type)]
    edges: list[tuple[str, str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _wp_code_to_addr_id(wp_code: str) -> str:
    """将 wp_code 转为 sheet 级 addr_id（{parent}/{sheet_code}）。

    例：D2-2 → D2/D2-2, A1 → A1/A1, A1-13 → A1/A1-13
    """
    parent = _extract_parent(wp_code)
    return f"{parent}/{wp_code}"


def _extract_parent(wp_code: str) -> str:
    """提取 parent_wp_code。"""
    m = re.match(r"^([A-S]\d+)", wp_code)
    if m:
        return m.group(1)
    return wp_code


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_render_registry_edges(
    *,
    entries: dict[str, Any] | None = None,
) -> RenderRegistryData:
    """从 workpaper_render_registry 加载 component_type 和依赖边。

    Parameters
    ----------
    entries
        可选：直接传入 registry entries dict（主要用于测试）。
        默认从 workpaper_render_registry_service 获取。

    Returns
    -------
    RenderRegistryData
        包含 component_types、render_types 和 L4 边列表。
    """
    if entries is None:
        entries = registry.get_all_entries()

    result = RenderRegistryData()

    for wp_code, entry in entries.items():
        render_type = entry.get("render_type", "")
        module = entry.get("module", "")

        # component_type = render_type（与前端 htmlRendererRegistry 对齐）
        result.component_types[wp_code] = render_type
        result.render_types[wp_code] = render_type

        # 提取 upstream/downstream 边
        source_addr_id = _wp_code_to_addr_id(wp_code)

        upstream: list[str] = entry.get("upstream", [])
        for up_code in upstream:
            target_addr_id = _wp_code_to_addr_id(up_code)
            # 边方向：source 依赖 target（上游）
            result.edges.append((source_addr_id, target_addr_id, "upstream"))

        downstream: list[str] = entry.get("downstream", [])
        for down_code in downstream:
            target_addr_id = _wp_code_to_addr_id(down_code)
            # 边方向：source → target（下游）
            result.edges.append((source_addr_id, target_addr_id, "downstream"))

    return result
