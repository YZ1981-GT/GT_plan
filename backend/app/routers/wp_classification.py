"""底稿 sheet 归类查询端点

GET /api/wp-classifications
按 design §5.1.4 实现：查询 9 类归属（前端组件路由依据）。

Requirements: 1.2
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper
from app.routers.wp_render_config import _maybe_custom_classifications
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    WpClassificationService,
    derive_component_type,
)
import sqlalchemy as sa

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/wp-classifications",
    tags=["wp-classifications"],
)


# ─── Response schemas ────────────────────────────────────────────────────────


class ClassificationItem(BaseModel):
    sheet_name: str
    class_code: str | None = None
    componentType: str
    scope: str
    is_real_workpaper: bool
    delegated_module: str | None = None
    has_override: bool = False


class ClassificationsResponse(BaseModel):
    wp_code: str
    project_id: str
    classifications: list[ClassificationItem]


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("", response_model=ClassificationsResponse)
async def get_wp_classifications(
    wp_code: str = Query(..., description="底稿编码（必填）"),
    project_id: UUID = Query(..., description="项目 ID（必填）"),
    template_version_id: UUID | None = Query(None, description="模板版本 ID（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询底稿 9 类归属（前端组件路由依据）。

    返回 wp_code 下所有 sheet 的归类信息，含 componentType 派生结果。

    EARS:
    - WHEN wp_code + project_id 有归类记录 THEN 返回 classifications 列表
    - IF 无归类记录 THEN 返回 404
    """
    classification_service = WpClassificationService(db)

    try:
        classifications = await classification_service.get_classification(
            wp_code=wp_code,
            project_id=project_id,
            template_version_id=template_version_id,
        )
    except ClassificationNotFoundError:
        classifications = []

    if not classifications:
        wp_index = (
            await db.execute(
                sa.select(WpIndex).where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        working_paper = None
        if wp_index is not None:
            working_paper = (
                await db.execute(
                    sa.select(WorkingPaper).where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.wp_index_id == wp_index.id,
                        WorkingPaper.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
        if wp_index is not None and working_paper is not None:
            classifications = await _maybe_custom_classifications(
                db,
                project_id,
                wp_code,
                wp_index.wp_name,
                classifications,
                working_paper,
            )

    if not classifications:
        raise HTTPException(
            status_code=404,
            detail=f"No classification found for wp_code='{wp_code}'",
        )

    # 构建响应：为每个 sheet 派生 componentType
    items: list[ClassificationItem] = []
    for c in classifications:
        try:
            component_type = derive_component_type(c)
        except ClassificationNotFoundError:
            component_type = "skip"

        items.append(
            ClassificationItem(
                sheet_name=c.sheet_name,
                class_code=c.class_code,
                componentType=component_type,
                scope=c.scope,
                is_real_workpaper=c.is_real_workpaper,
                delegated_module=c.delegated_module,
                has_override=c.has_override,
            )
        )

    return ClassificationsResponse(
        wp_code=wp_code,
        project_id=str(project_id),
        classifications=items,
    )
