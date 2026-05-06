"""底稿程序要求聚合服务 — Round 4 需求 1

聚合三个数据源：
1. wp_manuals（底稿使用说明，按循环加载操作手册）
2. procedures（关联到本底稿的审计程序列表）
3. continuous_audit prior_year_summary（上年同底稿结论摘要）

供前端 ProgramRequirementsSidebar 使用。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_manual_service import get_operation_manual

logger = logging.getLogger(__name__)


async def get_workpaper_requirements(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
) -> dict[str, Any]:
    """聚合底稿的程序要求信息

    Returns:
        {
            "manual": str | None,
            "procedures": [
                {
                    "id": str,
                    "procedure_code": str,
                    "procedure_name": str,
                    "status": str,
                    "execution_status": str,
                    "sort_order": int,
                    "assigned_to": str | None,
                }
            ],
            "prior_year_summary": {
                "wp_code": str,
                "wp_name": str,
                "conclusion": str | None,
                "status": str,
            } | None,
        }
    """
    # 1. 获取底稿信息（需要 wp_code / audit_cycle）
    wp_info = await _get_workpaper_info(db, project_id, wp_id)
    if not wp_info:
        return {"manual": None, "procedures": [], "prior_year_summary": None}

    wp_code = wp_info["wp_code"]
    audit_cycle = wp_info["audit_cycle"]

    # 2. 获取操作手册内容（按循环）
    manual = _get_manual_for_cycle(audit_cycle)

    # 3. 获取关联到本底稿的程序列表
    procedures = await _get_related_procedures(db, project_id, wp_id, wp_code, audit_cycle)

    # 4. 获取上年同底稿结论摘要
    prior_year_summary = await _get_prior_year_summary(db, project_id, wp_info)

    return {
        "manual": manual,
        "procedures": procedures,
        "prior_year_summary": prior_year_summary,
    }


async def _get_workpaper_info(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> dict[str, Any] | None:
    """获取底稿基本信息"""
    result = await db.execute(
        sa.select(
            WorkingPaper.id,
            WorkingPaper.wp_index_id,
            WorkingPaper.parsed_data,
            WorkingPaper.status,
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.audit_cycle,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if not row:
        return None

    return {
        "id": row.id,
        "wp_index_id": row.wp_index_id,
        "parsed_data": row.parsed_data,
        "status": str(row.status) if row.status else None,
        "wp_code": row.wp_code,
        "wp_name": row.wp_name,
        "audit_cycle": row.audit_cycle,
    }


def _get_manual_for_cycle(audit_cycle: str | None) -> str | None:
    """获取循环对应的操作手册内容"""
    if not audit_cycle:
        return None
    try:
        return get_operation_manual(audit_cycle, max_chars=8000)
    except Exception as e:
        logger.warning("获取操作手册失败 cycle=%s: %s", audit_cycle, e)
        return None


async def _get_related_procedures(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    wp_code: str | None,
    audit_cycle: str | None,
) -> list[dict[str, Any]]:
    """获取关联到本底稿的程序列表

    查询策略：
    1. 优先通过 ProcedureInstance.wp_id 精确匹配
    2. 其次通过 ProcedureInstance.wp_code 匹配
    3. 最后通过 audit_cycle 匹配同循环的所有程序
    """
    # 策略 1: 通过 wp_id 精确匹配
    result = await db.execute(
        sa.select(ProcedureInstance)
        .where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.wp_id == wp_id,
            ProcedureInstance.is_deleted == sa.false(),
        )
        .order_by(ProcedureInstance.sort_order)
    )
    rows = result.scalars().all()

    # 策略 2: 通过 wp_code 匹配
    if not rows and wp_code:
        result = await db.execute(
            sa.select(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_deleted == sa.false(),
            )
            .order_by(ProcedureInstance.sort_order)
        )
        rows = result.scalars().all()

    # 策略 3: 通过 audit_cycle 匹配
    if not rows and audit_cycle:
        result = await db.execute(
            sa.select(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == audit_cycle,
                ProcedureInstance.is_deleted == sa.false(),
            )
            .order_by(ProcedureInstance.sort_order)
        )
        rows = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "procedure_code": p.procedure_code,
            "procedure_name": p.procedure_name,
            "status": p.status,
            "execution_status": p.execution_status,
            "sort_order": p.sort_order,
            "assigned_to": str(p.assigned_to) if p.assigned_to else None,
        }
        for p in rows
    ]


async def _get_prior_year_summary(
    db: AsyncSession,
    project_id: UUID,
    wp_info: dict[str, Any],
) -> dict[str, Any] | None:
    """获取上年同底稿的结论摘要

    通过 projects.prior_year_project_id 找到上年项目，
    再通过 wp_index_id 对应的 wp_code 找到上年同底稿。
    """
    # 查找当前项目的 prior_year_project_id
    result = await db.execute(
        sa.text("SELECT prior_year_project_id FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    row = result.first()
    if not row or not row[0]:
        return None

    prior_project_id = row[0]
    wp_code = wp_info.get("wp_code")
    if not wp_code:
        return None

    # 在上年项目中查找同 wp_code 的底稿
    result = await db.execute(
        sa.select(
            WorkingPaper.id,
            WorkingPaper.status,
            WorkingPaper.parsed_data,
            WpIndex.wp_code,
            WpIndex.wp_name,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == prior_project_id,
            WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false(),
        )
        .limit(1)
    )
    prior_wp = result.first()
    if not prior_wp:
        return None

    # 提取结论
    parsed_data = prior_wp.parsed_data or {}
    conclusion = parsed_data.get("conclusion")

    return {
        "wp_id": str(prior_wp.id),
        "wp_code": prior_wp.wp_code,
        "wp_name": prior_wp.wp_name,
        "conclusion": conclusion,
        "status": str(prior_wp.status) if prior_wp.status else None,
    }
