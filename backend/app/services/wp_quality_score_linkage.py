"""程序完成率→quality_score 联动

Sprint 2 Task 2.7:
  完成率变化时触发重算 quality_score。
  公式：完整性 30% + 一致性 25% + 复核状态 20% + 程序完成率 15% + 自检通过率 10%
  缓存到 working_paper.quality_score 字段。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_procedure_service import WpProcedureService

logger = logging.getLogger(__name__)


async def recalc_quality_score(db: AsyncSession, wp_id: UUID) -> int:
    """重算底稿质量评分并更新到 working_paper 表

    当前简化实现：
    - 完整性 30%: 基于 parsed_data 是否存在（有=100，无=0）
    - 一致性 25%: 基于 consistency_status（consistent=100, unknown=50, inconsistent=0）
    - 复核状态 20%: 基于 review_status（reviewed=100, submitted=50, not_submitted=0）
    - 程序完成率 15%: 从 workpaper_procedures 计算
    - 自检通过率 10%: 暂固定 50（待自检模块接入）

    返回 0-100 整数评分。
    """
    # 获取底稿基本信息
    wp_row = (await db.execute(
        sa.text("""
            SELECT parsed_data IS NOT NULL AS has_data,
                   COALESCE(consistency_status, 'unknown') AS consistency,
                   COALESCE(review_status, 'not_submitted') AS review_st
            FROM working_paper
            WHERE id = :wp_id
        """),
        {"wp_id": str(wp_id)},
    )).first()

    if not wp_row:
        return 0

    # 1. 完整性 30%
    completeness = 100 if wp_row.has_data else 0

    # 2. 一致性 25%
    consistency_map = {"consistent": 100, "unknown": 50, "inconsistent": 0}
    consistency = consistency_map.get(wp_row.consistency, 50)

    # 3. 复核状态 20%
    review_map = {
        "reviewed": 100,
        "approved": 100,
        "submitted": 50,
        "pending_review": 50,
        "not_submitted": 0,
    }
    review = review_map.get(wp_row.review_st, 0)

    # 4. 程序完成率 15%
    svc = WpProcedureService(db)
    proc_rate = await svc.calc_completion_rate(wp_id)
    proc_score = int(proc_rate * 100)

    # 5. 自检通过率 10%（暂固定 50）
    self_check = 50

    # 加权计算
    score = int(
        completeness * 0.30
        + consistency * 0.25
        + review * 0.20
        + proc_score * 0.15
        + self_check * 0.10
    )
    score = max(0, min(100, score))

    # 更新到 working_paper 表
    await db.execute(
        sa.text("""
            UPDATE working_paper
            SET quality_score = :score,
                procedure_completion_rate = :rate
            WHERE id = :wp_id
        """),
        {"score": score, "rate": round(proc_rate * 100, 2), "wp_id": str(wp_id)},
    )
    await db.flush()

    logger.info(
        "quality_score recalculated: wp_id=%s score=%d proc_rate=%.2f%%",
        wp_id, score, proc_rate * 100,
    )
    return score
