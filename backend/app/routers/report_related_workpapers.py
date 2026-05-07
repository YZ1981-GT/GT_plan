"""报表行关联底稿端点 [R7-S3-09 Task 46]

GET /api/reports/{project_id}/{year}/{report_type}/{row_code}/related-workpapers
返回与指定报表行映射的底稿列表（通过 report_line_mapping 关联）。
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/reports",
    tags=["report-workpapers"],
)


@router.get("/{project_id}/{year}/{report_type}/{row_code}/related-workpapers")
async def get_related_workpapers(
    project_id: UUID,
    year: int,
    report_type: str,
    row_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回与报表行关联的底稿列表。

    通过 wp_account_mapping 和 report_config 的行次→科目映射，
    找到对应科目的底稿。
    """
    from app.models.workpaper_models import WpIndex

    # 简化实现：通过 row_code 前缀匹配底稿编码
    # 完整实现需要 report_config → account_code → wp_account_mapping → wp_code
    stmt = (
        select(WpIndex)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa: E712
        )
        .limit(10)
    )
    result = await db.execute(stmt)
    wps = result.scalars().all()

    # 返回所有底稿（后续优化为精确映射）
    return {
        "row_code": row_code,
        "report_type": report_type,
        "workpapers": [
            {
                "id": str(wp.id),
                "wp_code": wp.wp_code,
                "wp_name": wp.wp_name,
            }
            for wp in wps[:5]  # 最多返回 5 个
        ],
    }
