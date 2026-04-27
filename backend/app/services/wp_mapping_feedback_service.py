"""底稿推荐反馈闭环服务

Phase 12 P2-4: 记录推荐采纳/跳过/手动添加，统计采纳率，优化推荐规则。
"""
from __future__ import annotations

import logging
import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase12_models import WpRecommendationFeedback

logger = logging.getLogger(__name__)


class WpMappingFeedbackService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_feedback(
        self, project_id: UUID, wp_code: str, action: str, user_id: UUID | None = None,
        project_type: str | None = None, industry: str | None = None,
    ) -> dict:
        fb = WpRecommendationFeedback(
            id=uuid.uuid4(), project_id=project_id, wp_code=wp_code,
            action=action, action_by=user_id,
            project_type=project_type, industry=industry,
        )
        self.db.add(fb)
        await self.db.flush()
        return {"id": str(fb.id), "action": action}

    async def get_recommend_stats(self, project_id: UUID | None = None) -> dict:
        base = sa.select(
            WpRecommendationFeedback.action,
            func.count().label("cnt"),
        ).group_by(WpRecommendationFeedback.action)
        if project_id:
            base = base.where(WpRecommendationFeedback.project_id == project_id)
        rows = (await self.db.execute(base)).all()
        counts = {r.action: r.cnt for r in rows}
        accepted = counts.get("accepted", 0)
        skipped = counts.get("skipped", 0)
        manually = counts.get("manually_added", 0)
        total = accepted + skipped + manually
        return {
            "adoption_rate": round(accepted / (accepted + skipped) * 100, 1) if (accepted + skipped) else 0,
            "omission_rate": round(manually / total * 100, 1) if total else 0,
            "total_recommendations": total,
            "by_category": [],
        }
