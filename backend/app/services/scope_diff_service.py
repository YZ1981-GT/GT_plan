"""合并范围校对服务 — 合并企业树成员 vs consol_scope 表差异

group-tree-architecture 需求 9：

- compute_scope_diff: 计算树形成员 T 与合并范围成员 S 的集合差
    in_tree_not_scope = T \\ S（待纳入），in_scope_not_tree = S \\ T（待移除）
- sync_scope: **仅增量添加**树形子企业到 consol_scope 表，**不自动删除** scope 中多出条目
    （Req 9.4：移除交用户手动确认，避免误删手工配置的合并范围）

权威源：各项目三码 + 与上级关系推导出的合并企业树（consol-tree-three-code-autobuild 需求 11.3：
与合并计算同一棵树，``consol_tree_service.build_tree``），consol_scope 表作校对参考（Req 9.5）。
T = 树中的**子公司类企业**（含经中间企业间接持有、按最终控制方挂靠的）；母公司本身与各级分公司
不是合并范围成员（分公司并入所属企业汇总，不单独纳入合并范围）。差异提示不阻塞树形展示。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolScope
from app.models.core import Project
from app.services.project_audit_year import resolve_project_audit_year

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
    """合并项目的审计年度（平台统一解析，与企业树同一口径）。"""
    return resolve_project_audit_year(project)


async def _tree_members(db: AsyncSession, project_id: UUID) -> dict[str, str | None]:
    """本合并项目企业树中的子公司类企业 {企业代码: 企业名称}（合并计算同一棵树）。"""
    from app.services.consol_calc_basis import entity_kinds
    from app.services.consol_tree_service import build_tree, iter_nodes

    tree = await build_tree(db, project_id)
    if tree is None:
        return {}
    kinds = entity_kinds(tree)
    members: dict[str, str | None] = {}
    for node in iter_nodes(tree):
        code = (node.company_code or "").strip()
        if code and kinds.get(code) == "subsidiary" and code not in members:
            members[code] = node.company_name
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

    # --- 树形成员 T：本合并项目企业树中的子公司类企业（与合并计算同一棵树）---
    tree_members = await _tree_members(db, project_id)

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
        raise HTTPException(status_code=400, detail="无法确定合并项目的审计年度")

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

    # 企业树成员的名称（用于填充 company_name；不在树中的代码照常新增、名称留空）
    name_map = await _tree_members(db, project_id)

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
