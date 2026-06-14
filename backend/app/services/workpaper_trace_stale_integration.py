"""底稿溯源链 stale 集成

从 workpaper_render_registry.json 的 upstream/downstream 关系提取依赖边，
注入 unified_dependency_graph 中，由 StalePropagationEngine.on_change 自动传播。

用法：
  - 启动时调用 inject_registry_edges() 将注册表关系补入图中
  - 当 A 循环底稿数据变更时，调用 propagate_wp_stale(wp_code, project_id, year)
    触发下游标记

URI 格式：WP:{wp_code}::data（与现有 WP:D0 系列一致）
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.services import workpaper_render_registry_service as registry

logger = logging.getLogger(__name__)


def build_registry_edges() -> list[dict[str, str]]:
    """从注册表 upstream/downstream 生成图边列表。

    每条 downstream 关系转化为 source→target 边：
      A1.downstream 含 A2 → edge: WP:A1::data → WP:A2::data
    """
    entries = registry.get_all_entries()
    edges: list[dict[str, str]] = []
    for code, entry in entries.items():
        for ds in entry.get("downstream", []):
            if ds in entries:
                edges.append({
                    "source": f"WP:{code}::data",
                    "target": f"WP:{ds}::data",
                })
    return edges


def inject_registry_edges() -> int:
    """将注册表边注入 StalePropagationEngine 内存图。

    返回注入的边数。调用时机：应用启动后/注册表更新后。
    """
    from app.services.stale_propagation_engine import stale_engine

    edges = build_registry_edges()
    injected = 0
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        # 避免重复
        existing = stale_engine._graph.get(source, [])
        if target not in existing:
            stale_engine._graph.setdefault(source, []).append(target)
            stale_engine._reverse_graph.setdefault(target, []).append(source)
            injected += 1

    if injected:
        logger.info(
            "workpaper_trace_stale_integration: injected %d registry edges into stale graph",
            injected,
        )
    return injected


async def propagate_wp_stale(
    wp_code: str,
    project_id: UUID | str,
    year: int,
) -> list[str]:
    """当某底稿数据变更时，触发下游 stale 标记。

    返回被标记 stale 的下游 URI 列表。
    """
    from app.services.stale_propagation_engine import stale_engine

    source_uri = f"WP:{wp_code}::data"
    result = await stale_engine.on_change(
        source_uri=source_uri,
        project_id=project_id,
        year=year,
    )
    affected = result.get("affected_uris", []) if isinstance(result, dict) else []
    return affected
