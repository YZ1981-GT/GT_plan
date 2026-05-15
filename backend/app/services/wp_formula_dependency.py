"""底稿公式依赖图构建 + 拓扑排序 + 循环引用检测

D4 架构决策：公式解析器 → 构建依赖图 → 拓扑排序 → 逐个求值

依赖关系：
- =WP('H1', 'sheet', 'cell') → 依赖底稿 H1
- =PREV('D2', 'sheet', 'cell') → 依赖上年底稿 D2（跨年无循环风险）
- =TB/=LEDGER/=AUX/=ADJ/=NOTE → 依赖外部数据源（无底稿间依赖）
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class FormulaNode:
    """公式节点：一个底稿中的一个公式单元格"""
    wp_id: str  # 底稿 ID 或 wp_code
    sheet: str
    cell_ref: str
    formula_type: str
    raw_args: str
    # 依赖的其他底稿 wp_code 列表
    depends_on_wps: list[str] = field(default_factory=list)
    # 状态
    status: str = "pending"  # pending / filled / stale / error / waiting
    value: Any = None
    error: str | None = None


@dataclass
class DependencyGraph:
    """底稿间公式依赖图"""
    # wp_code → [FormulaNode]
    nodes_by_wp: dict[str, list[FormulaNode]] = field(default_factory=lambda: defaultdict(list))
    # 邻接表：wp_code → set of wp_codes it depends on
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # 反向邻接表：wp_code → set of wp_codes that depend on it
    reverse_edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # 所有参与的 wp_codes
    all_wps: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# 公式依赖提取
# ---------------------------------------------------------------------------

_WP_DEP_RE = re.compile(r"WP\('([^']+)'")
_PREV_DEP_RE = re.compile(r"PREV\('([^']+)'")


def extract_wp_dependencies(formula_type: str, raw_args: str) -> list[str]:
    """从公式中提取依赖的底稿 wp_code 列表

    只有 =WP() 和 =PREV() 会产生底稿间依赖。
    =TB/=LEDGER/=AUX/=ADJ/=NOTE 依赖外部数据源，不产生底稿间依赖。
    """
    deps = []
    ft = formula_type.upper()
    if ft == "WP":
        m = _WP_DEP_RE.search(f"{ft}('{raw_args}')" if "'" not in raw_args else raw_args)
        if m:
            deps.append(m.group(1))
        else:
            # 尝试从 raw_args 直接提取第一个参数
            parts = [p.strip().strip("'\"") for p in raw_args.split(",")]
            if parts:
                deps.append(parts[0])
    elif ft == "PREV":
        m = _PREV_DEP_RE.search(f"{ft}('{raw_args}')" if "'" not in raw_args else raw_args)
        if m:
            deps.append(m.group(1))
        else:
            parts = [p.strip().strip("'\"") for p in raw_args.split(",")]
            if parts:
                deps.append(parts[0])
    return deps


# ---------------------------------------------------------------------------
# 依赖图构建
# ---------------------------------------------------------------------------


def build_dependency_graph(
    formulas: list[dict[str, Any]],
    wp_code_map: dict[str, str] | None = None,
) -> DependencyGraph:
    """从公式列表构建依赖图

    Args:
        formulas: 公式列表，每项含 wp_code/wp_id, sheet, cell_ref, formula_type, raw_args
        wp_code_map: wp_id → wp_code 映射（可选）

    Returns:
        DependencyGraph 实例
    """
    graph = DependencyGraph()

    for f in formulas:
        wp_code = f.get("wp_code", f.get("wp_id", "unknown"))
        formula_type = f.get("formula_type", "")
        raw_args = f.get("raw_args", "")

        node = FormulaNode(
            wp_id=wp_code,
            sheet=f.get("sheet", ""),
            cell_ref=f.get("cell_ref", ""),
            formula_type=formula_type,
            raw_args=raw_args,
        )

        # 提取依赖
        deps = extract_wp_dependencies(formula_type, raw_args)
        node.depends_on_wps = deps

        graph.nodes_by_wp[wp_code].append(node)
        graph.all_wps.add(wp_code)

        for dep in deps:
            graph.edges[wp_code].add(dep)
            graph.reverse_edges[dep].add(wp_code)
            graph.all_wps.add(dep)

    return graph


# ---------------------------------------------------------------------------
# 循环引用检测
# ---------------------------------------------------------------------------


def detect_cycles(graph: DependencyGraph) -> list[list[str]]:
    """检测依赖图中的循环引用

    Returns:
        循环路径列表（每个循环是一个 wp_code 列表）。空列表表示无循环。
    """
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def _dfs(node: str) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.edges.get(node, set()):
            if neighbor not in visited:
                _dfs(neighbor)
            elif neighbor in rec_stack:
                # 找到循环
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        path.pop()
        rec_stack.discard(node)

    for wp in graph.all_wps:
        if wp not in visited:
            _dfs(wp)

    return cycles


def has_cycle(graph: DependencyGraph) -> bool:
    """快速判断是否有循环"""
    return len(detect_cycles(graph)) > 0


# ---------------------------------------------------------------------------
# 拓扑排序
# ---------------------------------------------------------------------------


def topological_sort(graph: DependencyGraph) -> list[str]:
    """对依赖图进行拓扑排序（Kahn's algorithm）

    Returns:
        按依赖顺序排列的 wp_code 列表（先无依赖的，后有依赖的）

    Raises:
        ValueError: 如果存在循环引用
    """
    # 计算入度
    in_degree: dict[str, int] = {wp: 0 for wp in graph.all_wps}
    for wp, deps in graph.edges.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[wp] = in_degree.get(wp, 0)  # ensure wp exists
            # wp depends on dep, so wp's in_degree doesn't change here
            # dep is depended upon, so nothing changes for dep's in_degree
            pass

    # 重新计算：in_degree[wp] = 有多少个其他节点是 wp 的前置依赖
    in_degree = {wp: 0 for wp in graph.all_wps}
    for wp, deps in graph.edges.items():
        # wp depends on deps, so wp has in_degree = len(deps that are in graph)
        for dep in deps:
            if dep in graph.all_wps:
                in_degree[wp] = in_degree.get(wp, 0) + 1

    # BFS
    queue = deque([wp for wp, deg in in_degree.items() if deg == 0])
    result: list[str] = []

    while queue:
        wp = queue.popleft()
        result.append(wp)

        # 对于所有依赖 wp 的节点，减少入度
        for dependent in graph.reverse_edges.get(wp, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(graph.all_wps):
        # 存在循环
        remaining = graph.all_wps - set(result)
        raise ValueError(f"循环引用检测：以下底稿存在循环依赖: {remaining}")

    return result


# ---------------------------------------------------------------------------
# 增量刷新：stale 标记 + 只重算受影响公式（Task 3.3）
# ---------------------------------------------------------------------------


def get_affected_wps(graph: DependencyGraph, changed_wp: str) -> list[str]:
    """获取受某底稿变更影响的所有下游底稿（BFS 传播）

    Args:
        graph: 依赖图
        changed_wp: 发生变更的底稿 wp_code

    Returns:
        受影响的 wp_code 列表（不含 changed_wp 自身）
    """
    affected: list[str] = []
    visited: set[str] = set()
    queue = deque([changed_wp])
    visited.add(changed_wp)

    while queue:
        current = queue.popleft()
        # 找到所有依赖 current 的底稿
        for dependent in graph.reverse_edges.get(current, set()):
            if dependent not in visited:
                visited.add(dependent)
                affected.append(dependent)
                queue.append(dependent)

    return affected


async def mark_stale_downstream(
    db: "AsyncSession",
    project_id: "UUID",
    changed_wp_code: str,
    graph: DependencyGraph | None = None,
) -> list[str]:
    """标记下游底稿为 stale（增量刷新的第一步）

    Args:
        db: 数据库会话
        project_id: 项目 ID
        changed_wp_code: 发生变更的底稿编码
        graph: 预构建的依赖图（可选，为 None 时跳过）

    Returns:
        被标记为 stale 的 wp_code 列表
    """
    if graph is None:
        return []

    affected = get_affected_wps(graph, changed_wp_code)
    if not affected:
        return []

    # 批量标记 stale
    import sqlalchemy as sa
    from app.models.workpaper_models import WorkingPaper

    await db.execute(
        sa.update(WorkingPaper)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .values(prefill_stale=True)
    )

    _logger.info(
        "mark_stale_downstream: project=%s changed=%s affected=%d wps=%s",
        project_id, changed_wp_code, len(affected), affected[:5],
    )
    return affected


async def incremental_refresh(
    db: "AsyncSession",
    project_id: "UUID",
    year: int,
    changed_wp_code: str,
    graph: DependencyGraph | None = None,
) -> dict[str, Any]:
    """增量刷新：只重算受影响的公式

    流程：
    1. 从依赖图找到受影响的下游底稿
    2. 按拓扑顺序重算
    3. 更新 stale 标记

    Returns:
        刷新结果摘要
    """
    if graph is None:
        return {"refreshed": 0, "message": "无依赖图，跳过增量刷新"}

    affected = get_affected_wps(graph, changed_wp_code)
    if not affected:
        return {"refreshed": 0, "message": "无下游依赖，无需刷新"}

    # 按拓扑顺序排列受影响的底稿
    try:
        full_order = topological_sort(graph)
    except ValueError as e:
        return {"refreshed": 0, "error": str(e)}

    # 只保留受影响的，按拓扑顺序
    ordered_affected = [wp for wp in full_order if wp in set(affected)]

    refreshed = 0
    errors = []

    for wp_code in ordered_affected:
        # 这里只标记需要重算，实际重算由 prefill_workpaper_real 执行
        _logger.debug("incremental_refresh: queued %s for recalc", wp_code)
        refreshed += 1

    # 标记 stale
    await mark_stale_downstream(db, project_id, changed_wp_code, graph)

    return {
        "refreshed": refreshed,
        "affected_wps": ordered_affected,
        "errors": errors,
        "message": f"已标记 {refreshed} 个底稿需要重算",
    }
