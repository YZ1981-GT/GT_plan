"""公式作用域过滤查询 API（formula-management-library Req 24 / Task 20.2）。

独立 router 模块（避免与并行任务在既有 router 同文件同行冲突）。仅查询、只读：
- GET /api/formula-scope/{project_id}/formulas?scope=note
      → 返回该项目指定作用域的公式列表（Req 24.1：弹窗按域加载）。
- GET /api/formula-scope/{project_id}/formulas
      → 返回该项目全部公式按 7 类作用域分组的并集（Req 24.3：全局公式页）。

作用域隔离（Req 24.5）：作用域分类为确定性单值划分，某作用域的编辑仅改该作用域
列表，其余作用域列表逐一不变。取数只读，遵循 service 只 flush / router commit 铁律
（本端点无写入，故不 commit）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.formula_management.formula_scope_query import (
    FORMULA_SCOPES,
    SCOPE_LABEL_MAP,
    formula_scope_query_service,
    formula_to_dict,
)

router = APIRouter(prefix="/api/formula-scope", tags=["formula-scope"])


@router.get("/{project_id}/formulas")
async def list_formulas_by_scope(
    project_id: UUID,
    scope: str | None = Query(
        None,
        description=(
            "目标 Formula_Scope（7 类：note/consol_note/consol_worksheet/"
            "consol_report/report/tb/workpaper）；省略则返回按作用域分组的并集"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """按 Formula_Scope 过滤公式列表；省略 scope 时返回全局并集（按作用域分组）。"""
    # ── 指定作用域：弹窗按域加载（Req 24.1/24.2）──────────────────────
    if scope is not None:
        if scope not in FORMULA_SCOPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "INVALID_FORMULA_SCOPE",
                    "message": (
                        f"非法作用域 '{scope}'，须为 "
                        f"{'/'.join(FORMULA_SCOPES)} 之一"
                    ),
                },
            )
        formulas = await formula_scope_query_service.list_by_scope(
            db, project_id=project_id, scope=scope
        )
        return {
            "project_id": str(project_id),
            "scope": scope,
            "scope_label": SCOPE_LABEL_MAP.get(scope, scope),
            "count": len(formulas),
            "items": [formula_to_dict(f, scope) for f in formulas],
        }

    # ── 省略作用域：全局公式页取并集（Req 24.3）──────────────────────
    grouped = await formula_scope_query_service.list_grouped_by_scope(
        db, project_id=project_id
    )
    scopes_payload = {
        s: {
            "scope_label": SCOPE_LABEL_MAP.get(s, s),
            "count": len(items),
            "items": [formula_to_dict(f, s) for f in items],
        }
        for s, items in grouped.items()
    }
    total = sum(len(items) for items in grouped.values())
    return {
        "project_id": str(project_id),
        "total": total,
        "scopes": scopes_payload,
    }
