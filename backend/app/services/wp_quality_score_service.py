"""底稿质量评分服务（完整版）

Sprint 8 Task 8.1: 5 维度加权计算 + 触发时机。
公式：完整性 30% + 一致性 25% + 复核状态 20% + 程序完成率 15% + 自检通过率 10%
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 权重配置
WEIGHTS = {
    "completeness": 0.30,
    "consistency": 0.25,
    "review_status": 0.20,
    "procedure_rate": 0.15,
    "self_check_rate": 0.10,
}


class WpQualityScoreService:
    """底稿质量评分服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_score(self, wp_id: UUID) -> dict:
        """计算单个底稿的质量评分

        Returns:
            {score, dimensions: {completeness, consistency, review, procedure, self_check}}
        """
        wp = (await self.db.execute(sa.text(
            """SELECT id, parsed_data IS NOT NULL AS has_data,
                      COALESCE(consistency_status, 'unknown') AS consistency,
                      COALESCE(review_status, 'not_submitted') AS review_st,
                      COALESCE(procedure_completion_rate, 0) AS proc_rate
               FROM working_paper WHERE id = :wid"""
        ), {"wid": str(wp_id)})).first()

        if not wp:
            return {"score": 0, "dimensions": {}}

        # 1. 完整性 30%: parsed_data 存在 + 关键区域填充率
        completeness = 100 if wp.has_data else 0

        # 2. 一致性 25%
        consistency_map = {"consistent": 100, "unknown": 50, "inconsistent": 0, "unchecked": 30}
        consistency = consistency_map.get(wp.consistency, 50)

        # 3. 复核状态 20%
        review_map = {
            "reviewed": 100, "approved": 100,
            "submitted": 60, "pending_review": 60,
            "not_submitted": 0, "rejected": 10,
        }
        review = review_map.get(wp.review_st, 0)

        # 4. 程序完成率 15%
        procedure = int(float(wp.proc_rate))

        # 5. 自检通过率 10%
        self_check = await self._calc_self_check_rate(wp_id)

        # 加权计算
        score = int(
            completeness * WEIGHTS["completeness"]
            + consistency * WEIGHTS["consistency"]
            + review * WEIGHTS["review_status"]
            + procedure * WEIGHTS["procedure_rate"]
            + self_check * WEIGHTS["self_check_rate"]
        )
        score = max(0, min(100, score))

        # 持久化
        await self.db.execute(sa.text(
            "UPDATE working_paper SET quality_score = :s WHERE id = :wid"
        ), {"s": score, "wid": str(wp_id)})
        await self.db.flush()

        return {
            "score": score,
            "dimensions": {
                "completeness": completeness,
                "consistency": consistency,
                "review_status": review,
                "procedure_rate": procedure,
                "self_check_rate": self_check,
            },
        }

    async def batch_calculate(self, project_id: UUID, year: Optional[int] = None) -> list[dict]:
        """批量计算项目下所有底稿的质量评分"""
        q = "SELECT id FROM working_paper WHERE project_id = :pid AND is_deleted = false"
        params: dict = {"pid": str(project_id)}
        if year:
            q += " AND year = :yr"
            params["yr"] = year

        rows = (await self.db.execute(sa.text(q), params)).fetchall()
        results = []
        for row in rows:
            r = await self.calculate_score(UUID(row.id))
            r["wp_id"] = row.id
            results.append(r)
        return results

    async def get_dashboard(self, project_id: UUID) -> dict:
        """获取项目质量仪表盘数据"""
        rows = (await self.db.execute(sa.text("""
            SELECT quality_score, wp_status,
                   COALESCE(consistency_status, 'unknown') AS consistency
            FROM working_paper
            WHERE project_id = :pid AND is_deleted = false
        """), {"pid": str(project_id)})).fetchall()

        if not rows:
            return {"total": 0, "avg_score": 0, "distribution": {}, "by_status": {}}

        scores = [r.quality_score or 0 for r in rows]
        avg = round(sum(scores) / len(scores), 1)

        # 分数分布
        distribution = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for s in scores:
            if s >= 80:
                distribution["excellent"] += 1
            elif s >= 60:
                distribution["good"] += 1
            elif s >= 40:
                distribution["fair"] += 1
            else:
                distribution["poor"] += 1

        # 按一致性状态统计
        by_consistency = {}
        for r in rows:
            by_consistency.setdefault(r.consistency, 0)
            by_consistency[r.consistency] += 1

        return {
            "total": len(rows),
            "avg_score": avg,
            "distribution": distribution,
            "by_consistency": by_consistency,
        }

    async def _calc_self_check_rate(self, wp_id: UUID) -> int:
        """计算自检通过率（基于 cross_check_results）"""
        row = (await self.db.execute(sa.text("""
            SELECT COUNT(*) FILTER (WHERE status = 'pass') AS passed,
                   COUNT(*) AS total
            FROM cross_check_results
            WHERE project_id = (SELECT project_id FROM working_paper WHERE id = :wid)
        """), {"wid": str(wp_id)})).first()

        if not row or row.total == 0:
            return 50  # 未执行校验时默认 50
        return int(row.passed / row.total * 100)
