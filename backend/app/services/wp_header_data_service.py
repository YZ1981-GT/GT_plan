"""底稿表头数据服务（纯数据，不写文件）

返回致同标准表头字段映射，供 HTML 渲染框架 / Univer 渲染器 / 导出使用。
与 wp_header_service.py（写 xlsx）互补——本服务只计算，不 IO。
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.workpaper_models import WpIndex

_logger = logging.getLogger(__name__)


async def get_header_data(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
    *,
    wp_name: str | None = None,
    assigned_to_name: str | None = None,
    reviewer_name: str | None = None,
    prepared_date: str | None = None,
    reviewed_date: str | None = None,
) -> dict[str, Any]:
    """返回致同标准表头字段映射。

    返回结构与前端 WorkpaperStandardHeader props 对齐：
    {entityName, wpName, indexNo, preparer, reviewer, preparedDate, reviewedDate, period}
    """
    proj = (
        await db.execute(sa.select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()

    if proj is None:
        return _empty_header(wp_code, wp_name)

    # 推导审计期间
    period_start = proj.audit_period_start
    period_end = proj.audit_period_end
    audit_year = proj.audit_year or (period_end.year if period_end else date.today().year)

    if not period_start:
        period_start = date(audit_year, 1, 1)
    if not period_end:
        period_end = date(audit_year, 12, 31)

    period_text = (
        f"{period_start.strftime('%Y年%m月%d日')}至{period_end.strftime('%Y年%m月%d日')}"
    )

    # 如果未传 wp_name，从 wp_index 查
    if not wp_name:
        idx = (
            await db.execute(
                sa.select(WpIndex.wp_name).where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        wp_name = idx or wp_code

    return {
        "entityName": proj.client_name or proj.name,
        "wpName": wp_name or wp_code,
        "indexNo": wp_code,
        "preparer": assigned_to_name or "",
        "reviewer": reviewer_name or "",
        "preparedDate": prepared_date or "",
        "reviewedDate": reviewed_date or "",
        "period": period_text,
    }


def _empty_header(wp_code: str | None, wp_name: str | None) -> dict[str, Any]:
    """项目不存在时返回空表头"""
    return {
        "entityName": "",
        "wpName": wp_name or wp_code or "",
        "indexNo": wp_code or "",
        "preparer": "",
        "reviewer": "",
        "preparedDate": "",
        "reviewedDate": "",
        "period": "",
    }
