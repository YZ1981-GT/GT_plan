"""当前集团树导出模板的来源、权限和范围校验。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_types import project_year as _project_year


async def validate_template_origin(
    db: AsyncSession,
    *,
    loaded: workbook_io.LoadedWorkbook,
    mode: str,
    current_user: Any | None,
    rows: list[workbook_io.ParsedRow],
) -> tuple[Project | None, set[UUID]]:
    """约束当前集团树导出模板只能回导到同一集团与年度，且不暴露隐藏成员归属。"""
    if loaded.mode is not None and loaded.mode != mode:
        raise HTTPException(status_code=400, detail="模板场景与当前导入入口不匹配，请下载对应模板")
    root_project_id = loaded.root_project_id
    if root_project_id is None:
        return None, set()
    if mode != "consolidation":
        raise HTTPException(status_code=400, detail="只有合并模块可以使用当前集团树导出模板")
    origin_error = "当前集团树模板不可用，请重新从当前集团树导出"
    write_rows = [row for row in rows if row.action in ("create", "update")]
    # 授权先于构树与成员归属比较：对根或任一更新目标无权，均不透露它是否仍在树内。
    if current_user is not None:
        from app.deps import assert_project_permission
        try:
            await assert_project_permission(db, current_user, root_project_id, "readonly")
            if write_rows:
                await assert_project_permission(db, current_user, root_project_id, "edit")
            for row in write_rows:
                if row.action == "update" and row.project_id is not None:
                    await assert_project_permission(db, current_user, row.project_id, "edit")
        except HTTPException as exc:
            raise HTTPException(status_code=400, detail=origin_error) from exc
        # assert_project_permission 会修改 RLS 上下文；构树仍按已授权的来源根读取，不能继承末个目标项目。
        from app.core.database import set_rls_context
        await set_rls_context(db, root_project_id)
    root = await db.get(Project, root_project_id)
    if root is None or root.is_deleted or (root.report_scope or "standalone") != "consolidated":
        raise HTTPException(status_code=400, detail=origin_error)
    from app.services.consol_tree_service import build_tree, iter_nodes
    tree = await build_tree(db, root_project_id)
    if tree is None:
        raise HTTPException(status_code=400, detail=origin_error)
    member_ids = {node.project_id for node in iter_nodes(tree) if node.project_id is not None}
    root_year = _project_year(root)
    root_code = (root.company_code or "").strip()
    for row in rows:
        if row.action == "skip":
            continue
        if row.action == "update" and row.project_id not in member_ids:
            raise HTTPException(status_code=400, detail=origin_error)
        if row.audit_year != root_year or row.ultimate_company_code != root_code:
            raise HTTPException(
                status_code=400,
                detail="当前集团树模板只能维护同一最终控制方和审计年度；新建其他集团请下载空白模板",
            )
    return root, member_ids


__all__ = ["validate_template_origin"]
