"""批量建项工作簿的场景与集团来源约束。

携带 ``root_project_id`` 的工作簿只能维护它导出的那棵合并树；不能把合法模板改造成
跨集团更新入口。来源项目权限在普通项目库存扫描之前校验。
"""
from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.batch_project_types import project_year, role_value


async def validate_template_origin(
    db: AsyncSession,
    *,
    loaded: Any,
    mode: str,
    current_user: Any | None,
    rows: Iterable[Any],
) -> tuple[Project | None, set[UUID]]:
    """校验模板场景和可选集团根，返回来源根与当下成员项目 ID。"""
    template_mode = getattr(loaded, "mode", None)
    if template_mode is not None and template_mode != mode:
        raise HTTPException(status_code=400, detail="模板场景与当前导入场景不一致，请重新下载模板")
    root_id = getattr(loaded, "root_project_id", None)
    if root_id is None:
        return None, set()
    if mode != "consolidation" or template_mode != "consolidation":
        raise HTTPException(status_code=400, detail="只有合并模块导出的模板可以携带集团来源")

    # 非 admin 必须先证明能编辑来源根，再构建企业树；避免把 root_id 变成存在性 oracle。
    if current_user is not None and role_value(current_user) != "admin":
        from app.deps import assert_project_permission

        await assert_project_permission(db, current_user, root_id, "edit")
    root = await db.get(Project, root_id)
    if root is None or root.is_deleted or (root.report_scope or "standalone") != "consolidated":
        raise HTTPException(status_code=400, detail="模板来源合并项目不存在或已失效，请重新导出")

    from app.services.consol_tree_service import build_tree, iter_nodes

    tree = await build_tree(db, root_id)
    if tree is None:
        raise HTTPException(status_code=400, detail="模板来源集团树不存在，请重新导出")
    member_ids: set[UUID] = set()
    for node in iter_nodes(tree):
        if node.project_id is not None:
            member_ids.add(node.project_id)
        if node.host_project_id is not None:
            member_ids.add(node.host_project_id)
    member_ids.add(root.id)

    root_code = str(root.company_code or "").strip()
    root_year = project_year(root)
    update_ids: set[UUID] = set()
    for row in rows:
        if str(getattr(row, "action", "create")) == "skip":
            continue
        row_year = getattr(row, "audit_year", None)
        ultimate = str(getattr(row, "ultimate_company_code", "") or "").strip()
        action = str(getattr(row, "action", "create"))
        row_project_id = getattr(row, "project_id", None)
        # 携带来源根的工作簿只能维护该最终控制方、该年度。空 ultimate 也必须拒绝：
        # 若把空值放过，后续 `_prepare_create_group_fields` 未必能补齐（例如同时没有 parent），
        # 合法集团模板就会被改造成创建独立企业的跨集团入口。加固前内联实现也是严格相等。
        if row_year != root_year or ultimate != root_code:
            raise HTTPException(status_code=400, detail="导入行不属于模板来源集团或审计年度")
        if action == "update" and row_project_id is not None:
            if row_project_id not in member_ids:
                raise HTTPException(status_code=400, detail="更新项目不属于模板来源集团")
            update_ids.add(row_project_id)

    if current_user is not None and role_value(current_user) != "admin":
        from app.deps import assert_project_permission

        for project_id in sorted(update_ids, key=str):
            await assert_project_permission(db, current_user, project_id, "edit")
    return root, member_ids


__all__ = ["validate_template_origin"]
