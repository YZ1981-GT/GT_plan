"""合并报表树形服务 — 三码体系构建企业树

build_tree: 从 projects 表构建树（parent_project_id 关系）
find_node: 按 company_code 查找节点
get_descendants: 获取所有后代节点
to_dict: 树→JSON
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project


@dataclass
class TreeNode:
    """企业树节点"""
    project_id: UUID
    company_code: str
    company_name: str
    parent_company_code: str | None
    ultimate_company_code: str | None
    consol_level: int
    children: list[TreeNode] = field(default_factory=list)


async def build_tree(db: AsyncSession, root_project_id: UUID) -> TreeNode | None:
    """从 projects 表构建企业树。

    root_project_id 是合并项目（最顶层），其子项目通过 parent_project_id 关联。
    """
    # 加载根项目
    result = await db.execute(
        sa.select(Project).where(
            Project.id == root_project_id,
            Project.is_deleted == sa.false(),
        )
    )
    root = result.scalar_one_or_none()
    if not root:
        return None

    # 加载所有子项目（递归查找所有 parent_project_id 链）
    all_projects = await _load_all_descendants(db, root_project_id)
    all_projects.insert(0, root)

    # 构建节点映射
    node_map: dict[UUID, TreeNode] = {}
    for p in all_projects:
        node_map[p.id] = TreeNode(
            project_id=p.id,
            company_code=p.company_code or str(p.id)[:8],
            company_name=p.client_name,
            parent_company_code=p.parent_company_code,
            ultimate_company_code=p.ultimate_company_code,
            consol_level=p.consol_level or 1,
        )

    # 建立父子关系
    for p in all_projects:
        if p.parent_project_id and p.parent_project_id in node_map:
            parent_node = node_map[p.parent_project_id]
            parent_node.children.append(node_map[p.id])

    return node_map.get(root_project_id)


async def _load_all_descendants(db: AsyncSession, root_id: UUID) -> list[Project]:
    """BFS 加载所有后代项目"""
    descendants: list[Project] = []
    queue = [root_id]
    visited: set[UUID] = {root_id}

    while queue:
        parent_ids = queue[:]
        queue.clear()
        result = await db.execute(
            sa.select(Project).where(
                Project.parent_project_id.in_(parent_ids),
                Project.is_deleted == sa.false(),
            )
        )
        children = result.scalars().all()
        for child in children:
            if child.id not in visited:
                visited.add(child.id)
                descendants.append(child)
                queue.append(child.id)

    return descendants


def find_node(root: TreeNode, company_code: str) -> TreeNode | None:
    """在树中按 company_code 查找节点（DFS）"""
    if root.company_code == company_code:
        return root
    for child in root.children:
        found = find_node(child, company_code)
        if found:
            return found
    return None


def get_descendants(node: TreeNode) -> list[TreeNode]:
    """获取节点的所有后代（不含自身）"""
    result: list[TreeNode] = []
    for child in node.children:
        result.append(child)
        result.extend(get_descendants(child))
    return result


def to_dict(node: TreeNode) -> dict:
    """树节点→JSON 字典"""
    return {
        "project_id": str(node.project_id),
        "company_code": node.company_code,
        "company_name": node.company_name,
        "parent_company_code": node.parent_company_code,
        "ultimate_company_code": node.ultimate_company_code,
        "consol_level": node.consol_level,
        "children": [to_dict(c) for c in node.children],
    }
