"""底稿批量 Tab 导入导出服务 — 基于 ACNR manifest

从 ACNR `manifest.list_import_export` 获取指定循环的 sheet 清单，
按 `depends_on_sheets` 拓扑排序后，使用每条 manifest entry 的
`api_prefix` + `item_id` 构造数据端点，`sheet_code` 作为 ZIP tab 名称。

核心铁律：
  - I/E 路由只认 manifest entry 的 api_prefix + item_id（源自 catalog）。
  - 未解析实例（wp_id=None）跳过并 log warning，不进 ZIP。
  - 拓扑排序保证 sheet 顺序满足 depends_on_sheets 依赖关系。
  - 导出与导入均应用拓扑排序：导出决定 ZIP 内 sheet 顺序，导入按依赖顺序路由
    数据，保证 ZIP 重新导入时依赖已就绪。

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def list_export_sheets(
    db: AsyncSession,
    project_id: str,
    cycle: str,
) -> list[dict[str, Any]]:
    """获取指定循环的可导出 sheet 列表（已拓扑排序）。

    从 manifest.list_import_export 获取清单，按 depends_on_sheets 拓扑排序，
    跳过 wp_id=None 的未解析实例。

    Args:
        db: Async database session（透传给 manifest.list_import_export）。
        project_id: 项目 UUID（透传，manifest 内部用于 resolve_instance）。
        cycle: 循环编码（如 "D"）。

    Returns:
        已拓扑排序的 manifest entry dict 列表，每条包含 sheet_code、api_prefix、
        item_id、depends_on_sheets、import_order、wp_id 等字段。wp_id=None 的
        条目已被过滤剔除。
    """
    from app.services.acnr.manifest import list_import_export

    entries = await list_import_export(db, project_id, cycle)

    # 过滤掉未解析实例（wp_id=None → resolve_instance miss）
    valid_entries: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("wp_id") is None:
            logger.warning(
                "Bulk export: skipping sheet_code=%s (wp_id=None, resolve_instance miss)",
                entry.get("sheet_code"),
            )
            continue
        valid_entries.append(entry)

    # 拓扑排序（按 depends_on_sheets，import_order 作 tiebreaker）
    # 导出也应用拓扑排序，确保 ZIP 中 sheet 顺序满足依赖，
    # 重新导入时依赖 sheet 先于依赖它的 sheet（Req 7.5）。
    sorted_entries = _topological_sort(valid_entries)
    return sorted_entries


async def list_import_sheets(
    db: AsyncSession,
    project_id: str,
    cycle: str,
) -> list[dict[str, Any]]:
    """获取指定循环的可导入 sheet 列表（已拓扑排序为导入顺序）。

    与 list_export_sheets 对称：从 manifest.list_import_export 获取清单，
    过滤 wp_id=None 的未解析实例（log warning + skip），按 depends_on_sheets
    拓扑排序，使被依赖的 sheet 排在依赖它的 sheet 之前，从而保证导入顺序满足
    依赖关系（Req 7.5）。

    调用方按返回顺序逐条导入时，使用每条 entry 的 `api_prefix` + `item_id`
    （必要时 `storage_field`）将导入数据路由到正确的存储端点（Req 6.6）。

    Args:
        db: Async database session（透传给 manifest.list_import_export）。
        project_id: 项目 UUID（透传，manifest 内部用于 resolve_instance）。
        cycle: 循环编码（如 "D"）。

    Returns:
        已拓扑排序（导入顺序）的 manifest entry dict 列表，每条包含 sheet_code、
        api_prefix、item_id、storage_field、depends_on_sheets、import_order、wp_id
        等字段。wp_id=None 的条目已被过滤剔除，不参与导入。
    """
    from app.services.acnr.manifest import list_import_export

    entries = await list_import_export(db, project_id, cycle)

    # 过滤掉未解析实例（wp_id=None → resolve_instance miss），跳过 + log warning
    valid_entries: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("wp_id") is None:
            logger.warning(
                "Bulk import: skipping sheet_code=%s (wp_id=None, resolve_instance miss)",
                entry.get("sheet_code"),
            )
            continue
        valid_entries.append(entry)

    # 拓扑排序：被依赖 sheet 先导入，import_order 作同级 tiebreaker（Req 7.1, 7.5）
    sorted_entries = _topological_sort(valid_entries)
    return sorted_entries


def _topological_sort(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 depends_on_sheets 拓扑排序（Kahn's algorithm）。

    - 无依赖的 entry 排前
    - 同级无依赖关系时以 import_order 为 tiebreaker
    - 循环依赖时（结果数 < 输入数）fallback 到 import_order 数值排序

    Args:
        entries: manifest entry dict 列表（已过滤 wp_id=None）。

    Returns:
        拓扑排序后的 entry 列表。检测到环时回退为 import_order 排序。
    """
    # 构建 sheet_code → entry 映射
    by_code: dict[str, dict] = {}
    for e in entries:
        by_code[e["sheet_code"]] = e

    # 构建邻接表（依赖 → 被依赖）+ 入度
    in_degree: dict[str, int] = {e["sheet_code"]: 0 for e in entries}
    graph: dict[str, list[str]] = {e["sheet_code"]: [] for e in entries}

    for e in entries:
        deps = e.get("depends_on_sheets") or []
        for dep in deps:
            if dep in graph:
                graph[dep].append(e["sheet_code"])
                in_degree[e["sheet_code"]] += 1

    # Kahn's algorithm：初始零入度队列，按 import_order 排序（tiebreaker）
    queue: deque[str] = deque(
        sorted(
            (code for code, deg in in_degree.items() if deg == 0),
            key=lambda c: by_code[c].get("import_order", 999),
        )
    )

    result: list[dict] = []
    while queue:
        current = queue.popleft()
        result.append(by_code[current])
        for neighbor in graph.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                # 插入时保持 import_order 排序（tiebreaker）
                inserted = False
                for i, q_item in enumerate(queue):
                    if by_code[neighbor].get("import_order", 999) < by_code[q_item].get(
                        "import_order", 999
                    ):
                        queue.insert(i, neighbor)
                        inserted = True
                        break
                if not inserted:
                    queue.append(neighbor)

    # 检测环（结果数 < 输入数 → 有环）
    if len(result) < len(entries):
        logger.error(
            "Circular dependency detected in depends_on_sheets, falling back to import_order sort"
        )
        return sorted(entries, key=lambda e: e.get("import_order", 999))

    return result
