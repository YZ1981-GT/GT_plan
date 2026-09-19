"""合并范围校对服务 — 树形(projects 三代码) vs consol_scope 表差异

group-tree-architecture 需求 9：

- compute_scope_diff: 计算树形成员 T 与合并范围成员 S 的集合差
    in_tree_not_scope = T \\ S（待纳入），in_scope_not_tree = S \\ T（待移除）
- sync_scope: **仅增量添加**树形子企业到 consol_scope 表，**不自动删除** scope 中多出条目
    （Req 9.4：移除交用户手动确认，避免误删手工配置的合并范围）

权威源：projects 表三代码（company_code / parent_company_code / ultimate_company_code），
consol_scope 表作校对参考（Req 9.5）。差异提示不阻塞树形展示。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolScope
from app.models.core import Project
from app.services.consol_tree_service import build_group_trees_from_projects

logger = logging.getLogger(__name__)


async def _load_consol_project(db: AsyncSession, project_id: UUID) -> Project:
    """加载合并母项目，校验存在且 report_scope='consolidated'。"""
    result = await db.execute(
        sa.select(Project).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.report_scope != "consolidated":
        raise HTTPException(status_code=400, detail="该项目不是合并项目，无合并范围校对")
    return project


def _resolve_year(project: Project) -> int | None:
    """从合并项目推导年度：优先 audit_period_end 年份，回退 audit_year。"""
    ape = getattr(project, "audit_period_end", None)
    if ape is not None:
        return ape.year
    return getattr(project, "audit_year", None)


def _collect_tree_members(tree: dict, root_code: str) -> dict[str, str | None]:
    """遍历单棵集团树，收集除根节点外所有节点的 {company_code: company_name}。

    根节点（company_code == root_code，即 ultimate 最终控制方）是合并母公司本身，
    不计入"子企业"成员集合。
    """
    members: dict[str, str | None] = {}

    def _walk(node: dict) -> None:
        code = (node.get("companyCode") or "").strip()
        if code and code != root_code:
            members[code] = node.get("companyName")
        for child in node.get("children", []):
            _walk(child)

    for child in tree.get("children", []):
        _walk(child)
    return members


async def compute_scope_diff(db: AsyncSession, project_id: UUID) -> dict:
    """计算树形成员 T 与合并范围成员 S 的集合差（Property 10）。

    Returns:
        {
            "in_tree_not_scope": [{"company_code", "company_name"}, ...],  # T \\ S
            "in_scope_not_tree": [{"company_code", "company_name"}, ...],  # S \\ T
        }
    """
    project = await _load_consol_project(db, project_id)
    year = _resolve_year(project)
    root_code = (project.company_code or "").strip()

    # --- 树形成员 T：本合并项目所属集团树的所有子节点 company_code ---
    # 取同一 ultimate（= 本合并项目的 company_code，作为最终控制方根）的项目构建树。
    tree_members: dict[str, str | None] = {}
    if root_code:
        stmt = sa.select(Project).where(
            Project.is_deleted == sa.false(),
            Project.ultimate_company_code == root_code,
        )
        proj_result = await db.execute(stmt)
        group_projects = list(proj_result.scalars().all())
        forest = build_group_trees_from_projects(group_projects, year=year)
        for tree in forest["trees"]:
            if (tree.get("ultimateCode") or "").strip() == root_code:
                tree_members = _collect_tree_members(tree, root_code)
                break

    # --- 合并范围成员 S：consol_scope 表 is_included=true 的 company_code ---
    scope_stmt = sa.select(ConsolScope).where(
        ConsolScope.project_id == project_id,
        ConsolScope.is_included == sa.true(),
        ConsolScope.is_deleted.is_(False),
    )
    if year is not None:
        scope_stmt = scope_stmt.where(ConsolScope.year == year)
    scope_result = await db.execute(scope_stmt)
    scope_members: dict[str, str | None] = {}
    for row in scope_result.scalars().all():
        code = (row.company_code or "").strip()
        if code:
            scope_members[code] = row.company_name

    tree_codes = set(tree_members.keys())
    scope_codes = set(scope_members.keys())

    in_tree_not_scope = [
        {"company_code": code, "company_name": tree_members.get(code)}
        for code in sorted(tree_codes - scope_codes)
    ]
    in_scope_not_tree = [
        {"company_code": code, "company_name": scope_members.get(code)}
        for code in sorted(scope_codes - tree_codes)
    ]

    return {
        "in_tree_not_scope": in_tree_not_scope,
        "in_scope_not_tree": in_scope_not_tree,
    }


async def sync_scope(db: AsyncSession, project_id: UUID, company_codes: list[str]) -> int:
    """将指定子企业代码**仅增量添加**到 consol_scope 表（Req 9.4）。

    - 对每个不在 consol_scope（同项目+同年度）中的 company_code，新增一行
      ConsolScope（is_included=true，company_name 取同集团项目名）。
    - **绝不删除**已存在的 scope 行（即使其不在 company_codes 中）。
    - 已存在的 company_code 跳过，不重复插入。

    本函数只 flush，由路由统一 commit（保持与跨 service 编排一致）。

    Returns:
        实际新增的条数。
    """
    project = await _load_consol_project(db, project_id)
    year = _resolve_year(project)
    if year is None:
        raise HTTPException(status_code=400, detail="合并项目缺少审计期末日期，无法确定年度")

    # 去重 + 过滤空白
    wanted = [c.strip() for c in company_codes if c and c.strip()]
    wanted = list(dict.fromkeys(wanted))
    if not wanted:
        return 0

    # 已存在的 scope 代码（同项目+同年度，含已软删？只看未删行，避免与软删唯一约束冲突）
    existing_result = await db.execute(
        sa.select(ConsolScope.company_code).where(
            ConsolScope.project_id == project_id,
            ConsolScope.year == year,
            ConsolScope.is_deleted.is_(False),
        )
    )
    existing_codes = {(c or "").strip() for c in existing_result.scalars().all()}

    # 同集团项目 company_code → client_name（用于填充 company_name）
    root_code = (project.company_code or "").strip()
    name_map: dict[str, str] = {}
    if root_code:
        name_result = await db.execute(
            sa.select(Project.company_code, Project.client_name).where(
                Project.is_deleted == sa.false(),
                Project.ultimate_company_code == root_code,
            )
        )
        for code, client_name in name_result.all():
            if code:
                name_map[code.strip()] = client_name

    added = 0
    for code in wanted:
        if code in existing_codes:
            continue
        db.add(ConsolScope(
            project_id=project_id,
            year=year,
            company_code=code,
            company_name=name_map.get(code),
            is_included=True,
        ))
        existing_codes.add(code)
        added += 1

    if added:
        await db.flush()
    return added
