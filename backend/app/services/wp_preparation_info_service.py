"""底稿编制信息服务 — 从 router 下沉的纯 service 层

提供 build_preparation_info(db, project_id, wp_id) 异步方法，
返回底稿表头编制信息字典（7 字段），供 B-Index / C-Note 策略
及 get_preparation_info 端点共用。

消除策略文件反向 import router 的循环依赖隐患。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex, WorkingPaper

logger = logging.getLogger(__name__)


async def build_preparation_info(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
) -> dict[str, str]:
    """编制信息 JOIN（workpaper 级表头 + B-Index 共用）。

    从项目、人员分配、底稿三方面拼装编制信息，
    每个字段独立 try/except 降级，确保单字段查询失败不影响其余。

    Args:
        db: 异步数据库会话
        project_id: 项目 UUID
        wp_id: 底稿 UUID

    Returns:
        包含以下 7 个键的字典，值均为 str（失败时为空字符串）：
        - entity_name: 被审计单位名称（项目名称）
        - period_end: 审计期间截止日（YYYY-MM-DD）
        - preparer: 编制人姓名（优先底稿级 assigned_to，回退项目级 preparer）
        - prep_date: 编制日期（底稿创建日期 YYYY-MM-DD）
        - reviewer: 复核人姓名
        - review_date: 复核日期（预留，当前返回空）
        - index_no: 底稿编号（wp_code）
    """
    info: dict[str, str] = {
        "entity_name": "",
        "period_end": "",
        "preparer": "",
        "prep_date": "",
        "reviewer": "",
        "review_date": "",
        "index_no": "",
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT name, audit_period_end FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.first()
        if proj_row:
            info["entity_name"] = proj_row[0] or ""
            info["period_end"] = str(proj_row[1])[:10] if proj_row[1] else ""
    except Exception as e:
        logger.warning("preparation_info: 项目信息失败: %s", e)

    if not info["entity_name"]:
        try:
            from app.models.core import Project

            proj = await db.get(Project, project_id)
            if proj:
                info["entity_name"] = proj.name or ""
                if not info["period_end"] and getattr(proj, "audit_period_end", None):
                    info["period_end"] = str(proj.audit_period_end)[:10]
        except Exception as e:
            logger.warning("preparation_info: ORM 项目信息降级失败: %s", e)

    try:
        staff_result = await db.execute(
            sa.text("""
                SELECT pa.role, s.name
                FROM project_assignments pa
                JOIN staff_members s ON s.id = pa.staff_id
                WHERE pa.project_id = :pid
                  AND pa.role IN ('preparer', 'reviewer', 'partner', 'manager')
            """),
            {"pid": str(project_id)},
        )
        for role, name in staff_result:
            if role == "preparer":
                info["preparer"] = name or ""
            elif role in ("reviewer", "manager"):
                if not info["reviewer"] or role == "reviewer":
                    info["reviewer"] = name or ""
    except Exception as e:
        logger.warning("preparation_info: 人员信息失败: %s", e)

    try:
        wp_row = (
            await db.execute(
                sa.select(WorkingPaper.created_at, WpIndex.wp_code, WorkingPaper.assigned_to)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == wp_id)
            )
        ).first()
        if wp_row:
            if wp_row[0]:
                info["prep_date"] = str(wp_row[0])[:10]
            info["index_no"] = wp_row[1] or ""
            # 底稿级编制人优先（assigned_to）：表头编制人应是本底稿被分配人，
            # 而非项目级 preparer。仅当底稿未分配时才回退到项目级 preparer。
            wp_assignee_id = wp_row[2]
            if wp_assignee_id:
                try:
                    assignee_row = (
                        await db.execute(
                            sa.text(
                                "SELECT username FROM users WHERE id = :uid"
                            ),
                            {"uid": str(wp_assignee_id)},
                        )
                    ).first()
                    if assignee_row and assignee_row[0]:
                        info["preparer"] = assignee_row[0]
                except Exception as e:
                    logger.debug("preparation_info: 底稿级编制人取名降级: %s", e)
    except Exception as e:
        logger.warning("preparation_info: 底稿信息失败: %s", e)

    return info
