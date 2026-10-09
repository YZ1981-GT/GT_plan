"""formula_runtime.source_scope — 公式来源范围解析。

将 wp_formula.source_scope JSONB 解析为结构化的取数范围，
通过企业树服务解析 node_key 并收集子树的项目/公司列表。

结构化 source scope 格式（设计 §十二.4）：
{
    "project_id": "<uuid>",
    "year": <int>,
    "node_key": "<optional: 企业树节点键>",
    "include_descendants": true,
    "domains": ["report", "note", "workpaper", "consol_worksheet"]
}

spec: consol-node-key-isolation-and-shared-context 任务 8.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# 默认支持的取数域（设计 §十二.4 明确列举）
DEFAULT_SCOPE_DOMAINS = frozenset({"report", "note", "workpaper", "consol_worksheet"})


@dataclass(frozen=True)
class ResolvedSourceScope:
    """解析后的公式来源范围。"""

    project_id: UUID
    year: int
    node_key: str | None = None
    include_descendants: bool = True
    domains: frozenset[str] = field(default_factory=lambda: DEFAULT_SCOPE_DOMAINS)
    # 解析后的子树节点键列表（含自身），用于取数过滤
    resolved_node_keys: tuple[str, ...] = ()
    # 子树对应的项目 ID 列表（含自身项目），用于跨项目取数
    resolved_project_ids: tuple[UUID, ...] = ()


def parse_source_scope(raw: dict[str, Any] | None) -> ResolvedSourceScope | None:
    """将 JSONB 原始值解析为 ResolvedSourceScope。

    返回 None 表示 source_scope 为空/无效（公式使用默认的项目/年度级取数）。
    """
    if not raw or not isinstance(raw, dict):
        return None

    project_id_str = raw.get("project_id")
    year = raw.get("year")
    if not project_id_str or not year:
        return None

    try:
        project_id = UUID(str(project_id_str))
    except (ValueError, TypeError):
        logger.warning("source_scope 的 project_id 无效: %s", project_id_str)
        return None

    node_key = raw.get("node_key") or None
    include_descendants = bool(raw.get("include_descendants", True))

    domains_raw = raw.get("domains")
    if isinstance(domains_raw, list) and domains_raw:
        domains = frozenset(str(d) for d in domains_raw if d)
    else:
        domains = DEFAULT_SCOPE_DOMAINS

    return ResolvedSourceScope(
        project_id=project_id,
        year=int(year),
        node_key=node_key,
        include_descendants=include_descendants,
        domains=domains,
    )


async def resolve_scope_with_tree(
    db: Any,
    scope: ResolvedSourceScope,
) -> ResolvedSourceScope:
    """通过企业树服务解析 node_key，填充子树节点键和项目 ID 列表。

    如果 node_key 为空或企业树不可用，返回原始 scope 不含子树信息。
    """
    if not scope.node_key:
        return ResolvedSourceScope(
            project_id=scope.project_id,
            year=scope.year,
            node_key=scope.node_key,
            include_descendants=scope.include_descendants,
            domains=scope.domains,
            resolved_node_keys=(),
            resolved_project_ids=(scope.project_id,),
        )

    try:
        from app.services.consol_tree_service import (
            build_tree,
            find_node_by_key,
            get_descendants,
        )

        tree = await build_tree(db, scope.project_id)
        if tree is None:
            logger.warning(
                "source_scope 解析：项目 %s 无企业树", scope.project_id
            )
            return scope

        target_node = find_node_by_key(tree, scope.node_key)
        if target_node is None:
            logger.warning(
                "source_scope 解析：node_key %s 不在项目 %s 的企业树中",
                scope.node_key, scope.project_id,
            )
            return scope

        node_keys = [target_node.node_key]
        project_ids = set()
        if hasattr(target_node, "host_project_id") and target_node.host_project_id:
            project_ids.add(target_node.host_project_id)

        if scope.include_descendants:
            for desc in get_descendants(target_node):
                node_keys.append(desc.node_key)
                if hasattr(desc, "host_project_id") and desc.host_project_id:
                    project_ids.add(desc.host_project_id)

        # 确保主项目 ID 始终包含
        project_ids.add(scope.project_id)

        return ResolvedSourceScope(
            project_id=scope.project_id,
            year=scope.year,
            node_key=scope.node_key,
            include_descendants=scope.include_descendants,
            domains=scope.domains,
            resolved_node_keys=tuple(node_keys),
            resolved_project_ids=tuple(sorted(project_ids)),
        )

    except Exception:
        logger.exception(
            "source_scope 企业树解析失败：project=%s node_key=%s",
            scope.project_id, scope.node_key,
        )
        return scope
