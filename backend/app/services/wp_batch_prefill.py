"""批量预填充编排服务

按依赖顺序处理多底稿的预填充。
复用 prefill_engine.batch_prefill_ordered 核心逻辑，
提供更高层的编排能力（跨项目、进度回调、结果汇总）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper
from app.services.prefill_engine import batch_prefill_ordered
from app.services.wp_formula_dependency import (
    DependencyGraph,
    build_dependency_graph,
    detect_cycles,
    topological_sort,
)

_logger = logging.getLogger(__name__)


@dataclass
class BatchPrefillResult:
    """批量预填充结果"""
    total: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    execution_order: list[str] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    cycle_detected: bool = False
    cycle_path: list[str] | None = None


async def collect_formulas_for_project(
    db: AsyncSession,
    project_id: UUID,
    wp_ids: list[UUID] | None = None,
) -> tuple[list[dict], dict[str, WorkingPaper]]:
    """收集项目底稿的公式信息，用于构建依赖图

    Args:
        db: 数据库会话
        project_id: 项目 ID
        wp_ids: 指定底稿 ID 列表（None 表示全部）

    Returns:
        (公式列表, wp_code→WorkingPaper 映射)
    """
    q = sa.select(WorkingPaper).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    if wp_ids:
        q = q.where(WorkingPaper.id.in_(wp_ids))

    result = await db.execute(q)
    workpapers = result.scalars().all()

    wp_map: dict[str, WorkingPaper] = {}
    all_formulas: list[dict] = []

    for wp in workpapers:
        wp_code = (wp.parsed_data or {}).get("wp_code", str(wp.id))
        wp_map[wp_code] = wp

        # 从 cell_provenance 提取公式信息
        provenance = (wp.parsed_data or {}).get("cell_provenance", {})
        for cell_ref, prov in provenance.items():
            sheet = cell_ref.split("!")[0] if "!" in cell_ref else ""
            ref = cell_ref.split("!")[-1] if "!" in cell_ref else cell_ref
            all_formulas.append({
                "wp_code": wp_code,
                "sheet": sheet,
                "cell_ref": ref,
                "formula_type": prov.get("formula_type", ""),
                "raw_args": prov.get("raw_args", ""),
            })

    return all_formulas, wp_map


async def batch_prefill(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_ids: list[UUID],
) -> BatchPrefillResult:
    """按依赖顺序批量预填充多底稿

    流程：
    1. 收集所有底稿的公式
    2. 构建跨底稿依赖图
    3. 检测循环引用
    4. 拓扑排序确定执行顺序
    5. 按顺序逐个执行预填充
    6. 返回结果汇总

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 审计年度
        wp_ids: 要预填充的底稿 ID 列表

    Returns:
        BatchPrefillResult 结果对象
    """
    result = BatchPrefillResult(total=len(wp_ids))

    # 委托给 prefill_engine 的核心实现
    raw = await batch_prefill_ordered(db, project_id, year, wp_ids)

    result.success_count = raw.get("success_count", 0)
    result.error_count = raw.get("error_count", 0)
    result.results = raw.get("results", {})
    result.errors = raw.get("errors", {})
    result.execution_order = raw.get("execution_order", [])

    # 检查是否有循环引用错误
    if "circular_reference" in raw.get("errors", {}):
        result.cycle_detected = True
        result.cycle_path = []

    return result


async def batch_prefill_project(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    stale_only: bool = True,
) -> BatchPrefillResult:
    """项目级批量预填充（只处理 stale 或全部）

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 审计年度
        stale_only: True=只处理 prefill_stale=True 的底稿

    Returns:
        BatchPrefillResult
    """
    q = sa.select(WorkingPaper.id).where(
        WorkingPaper.project_id == project_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    if stale_only:
        q = q.where(WorkingPaper.prefill_stale == True)  # noqa: E712

    result = await db.execute(q)
    wp_ids = [row[0] for row in result.all()]

    if not wp_ids:
        return BatchPrefillResult(
            total=0, success_count=0, error_count=0,
            execution_order=[], results={}, errors={},
        )

    return await batch_prefill(db, project_id, year, wp_ids)


async def get_dependency_summary(
    db: AsyncSession,
    project_id: UUID,
    wp_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """获取依赖图摘要（用于前端展示）

    Returns:
        {
            "nodes": [...],  # 底稿节点列表
            "edges": [...],  # 依赖边列表
            "has_cycle": bool,
            "execution_order": [...],
            "stale_wps": [...],
        }
    """
    formulas, wp_map = await collect_formulas_for_project(db, project_id, wp_ids)
    graph = build_dependency_graph(formulas)

    cycles = detect_cycles(graph)
    has_cycle = len(cycles) > 0

    order: list[str] = []
    if not has_cycle:
        try:
            order = topological_sort(graph)
        except ValueError:
            has_cycle = True

    # 构建节点和边
    nodes = []
    for wp_code in graph.all_wps:
        wp = wp_map.get(wp_code)
        nodes.append({
            "id": wp_code,
            "label": wp_code,
            "wp_id": str(wp.id) if wp else None,
            "formula_count": len(graph.nodes_by_wp.get(wp_code, [])),
            "is_stale": wp.prefill_stale if wp else False,
        })

    edges = []
    for wp_code, deps in graph.edges.items():
        for dep in deps:
            edges.append({"from": dep, "to": wp_code})

    return {
        "nodes": nodes,
        "edges": edges,
        "has_cycle": has_cycle,
        "cycles": cycles[:3] if cycles else [],
        "execution_order": order,
        "total_formulas": sum(len(v) for v in graph.nodes_by_wp.values()),
    }
