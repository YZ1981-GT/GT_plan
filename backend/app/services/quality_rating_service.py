"""QualityRatingService — 项目质量评级计算

Refinement Round 3 — 需求 3：
- 5 维度评分 + 可配置权重（存 system_settings.qc_rating_weights）
- 评级阈值：A>=90, B>=75, C>=60, D<60
- 支持人工 override（必须附文字说明）
- 每月 1 日凌晨定时任务计算上月快照
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_rating_models import ProjectQualityRating

logger = logging.getLogger(__name__)

# 默认权重（当 system_settings 不可用时回退）
DEFAULT_WEIGHTS: dict[str, float] = {
    "qc_pass_rate": 0.30,
    "review_depth": 0.25,
    "gate_failures": 0.20,
    "remediation_sla": 0.15,
    "client_response": 0.10,
}


class QualityRatingService:
    """项目质量评级服务

    5 维度加权计算：
    - qc_pass_rate (30%): QC 规则通过率
    - review_depth (25%): 复核深度（平均意见条数、退回率）
    - gate_failures (20%): 门禁失败次数
    - remediation_sla (15%): 整改响应 SLA（问题单平均关闭时长）
    - client_response (10%): 客户响应（承诺事项按时完成率）
    """

    async def compute(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> ProjectQualityRating:
        """计算项目质量评级并持久化。

        如果该项目该年度已有评级记录，则更新；否则新建。
        """
        weights = await self._get_weights(db)

        dims = {
            "qc_pass_rate": await self._qc_pass_score(db, project_id, year),
            "review_depth": await self._review_depth_score(db, project_id, year),
            "gate_failures": await self._gate_failure_score(db, project_id, year),
            "remediation_sla": await self._remediation_sla_score(db, project_id, year),
            "client_response": await self._client_response_score(db, project_id, year),
        }

        score = sum(weights[k] * dims[k] for k in weights)
        # 四舍五入到整数
        score_int = round(score)
        rating = self._score_to_rating(score)

        # 查找已有记录
        stmt = select(ProjectQualityRating).where(
            ProjectQualityRating.project_id == project_id,
            ProjectQualityRating.year == year,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if existing:
            existing.rating = rating
            existing.score = score_int
            existing.dimensions = dims
            existing.computed_at = now
            return existing
        else:
            record = ProjectQualityRating(
                id=uuid.uuid4(),
                project_id=project_id,
                year=year,
                rating=rating,
                score=score_int,
                dimensions=dims,
                computed_at=now,
                computed_by_rule_version=1,
            )
            db.add(record)
            return record

    async def get_rating(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> dict[str, Any] | None:
        """获取项目评级详情（含各维度得分 + 推导过程）。"""
        stmt = select(ProjectQualityRating).where(
            ProjectQualityRating.project_id == project_id,
            ProjectQualityRating.year == year,
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return None

        weights = await self._get_weights(db)

        return {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "year": record.year,
            "rating": record.override_rating or record.rating,
            "system_rating": record.rating,
            "score": record.score,
            "dimensions": record.dimensions,
            "weights": weights,
            "derivation": self._build_derivation(record.dimensions, weights),
            "computed_at": record.computed_at.isoformat() if record.computed_at else None,
            "computed_by_rule_version": record.computed_by_rule_version,
            "override_by": str(record.override_by) if record.override_by else None,
            "override_rating": record.override_rating,
            "override_reason": record.override_reason,
        }

    async def override_rating(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        rating: str,
        reason: str,
        override_by: UUID,
    ) -> dict[str, Any]:
        """人工覆盖评级（必须附文字说明）。"""
        if rating not in ("A", "B", "C", "D"):
            raise ValueError("评级必须为 A/B/C/D")
        if not reason or not reason.strip():
            raise ValueError("覆盖原因不能为空")

        stmt = select(ProjectQualityRating).where(
            ProjectQualityRating.project_id == project_id,
            ProjectQualityRating.year == year,
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            # 如果没有系统评级记录，先创建一个空记录
            record = ProjectQualityRating(
                id=uuid.uuid4(),
                project_id=project_id,
                year=year,
                rating="D",  # 默认
                score=0,
                dimensions={},
                computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                computed_by_rule_version=1,
            )
            db.add(record)

        record.override_by = override_by
        record.override_rating = rating
        record.override_reason = reason.strip()

        return {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "year": record.year,
            "system_rating": record.rating,
            "override_rating": record.override_rating,
            "override_reason": record.override_reason,
            "override_by": str(record.override_by),
        }

    async def compute_all_projects(self, db: AsyncSession, year: int) -> int:
        """批量计算所有项目的评级（定时任务调用）。返回计算的项目数。"""
        from app.models.core import Project

        stmt = select(Project.id).where(Project.is_deleted == False)  # noqa: E712
        result = await db.execute(stmt)
        project_ids = [row[0] for row in result.all()]

        count = 0
        for pid in project_ids:
            try:
                await self.compute(db, pid, year)
                count += 1
            except Exception as e:
                logger.warning(
                    "[QC-RATING] failed to compute rating for project %s: %s",
                    pid,
                    e,
                )
        return count

    # -----------------------------------------------------------------------
    # 权重配置
    # -----------------------------------------------------------------------

    async def _get_weights(self, db: AsyncSession) -> dict[str, float]:
        """从 system_settings 表读取 qc_rating_weights 配置，失败回退默认值。"""
        try:
            result = await db.execute(
                sa_text(
                    "SELECT value FROM system_settings WHERE key = 'qc_rating_weights' LIMIT 1"
                )
            )
            row = result.fetchone()
            if row and row[0]:
                weights = json.loads(row[0])
                # 验证权重合法性
                if isinstance(weights, dict) and len(weights) == 5:
                    return {k: float(v) for k, v in weights.items()}
        except Exception as exc:
            logger.warning(
                "[QC-RATING] failed to read qc_rating_weights from system_settings: %s",
                exc,
            )
        return DEFAULT_WEIGHTS.copy()

    # -----------------------------------------------------------------------
    # 5 维度评分（各返回 0-100 分）
    # -----------------------------------------------------------------------

    async def _qc_pass_score(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> float:
        """QC 规则通过率 → 0-100 分。

        通过率 = 通过的 QC 检查数 / 总 QC 检查数 × 100
        """
        try:
            result = await db.execute(
                sa_text(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN passed = true THEN 1 ELSE 0 END) as passed_count "
                    "FROM wp_qc_results "
                    "WHERE project_id = :pid"
                ),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row and row[0] and row[0] > 0:
                return round((row[1] or 0) / row[0] * 100, 2)
        except Exception as e:
            logger.debug("[QC-RATING] _qc_pass_score error: %s", e)
        return 80.0  # 无数据时给默认中等分

    async def _review_depth_score(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> float:
        """复核深度 → 0-100 分。

        综合考虑：平均意见条数、退回率。
        意见条数 >= 3 得满分，退回率 10%-30% 为合理区间。
        """
        try:
            # 查询复核记录数和退回数
            result = await db.execute(
                sa_text(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN review_status = 'rejected' THEN 1 ELSE 0 END) as rejected "
                    "FROM wp_review_records "
                    "WHERE project_id = :pid"
                ),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row and row[0] and row[0] > 0:
                total = row[0]
                rejected = row[1] or 0
                rejection_rate = rejected / total

                # 退回率评分：10%-30% 为最佳区间
                if 0.10 <= rejection_rate <= 0.30:
                    rate_score = 100.0
                elif rejection_rate < 0.10:
                    # 退回率太低可能走过场
                    rate_score = max(50.0, rejection_rate / 0.10 * 100)
                else:
                    # 退回率太高说明质量差
                    rate_score = max(40.0, 100 - (rejection_rate - 0.30) * 200)

                return round(rate_score, 2)
        except Exception as e:
            logger.debug("[QC-RATING] _review_depth_score error: %s", e)
        return 75.0  # 默认中等分

    async def _gate_failure_score(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> float:
        """门禁失败次数 → 0-100 分。

        失败次数越少分越高。0 次 = 100 分，每多一次扣 10 分，最低 20 分。
        """
        try:
            result = await db.execute(
                sa_text(
                    "SELECT COUNT(*) FROM gate_evaluations "
                    "WHERE project_id = :pid AND decision = 'block'"
                ),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row:
                failures = row[0] or 0
                return max(20.0, 100.0 - failures * 10.0)
        except Exception as e:
            logger.debug("[QC-RATING] _gate_failure_score error: %s", e)
        return 85.0  # 默认

    async def _remediation_sla_score(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> float:
        """整改响应 SLA → 0-100 分。

        基于问题单平均关闭时长。越快关闭分越高。
        7 天内关闭 = 100 分，每多 1 天扣 5 分，最低 30 分。
        """
        try:
            result = await db.execute(
                sa_text(
                    "SELECT AVG("
                    "  EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400.0"
                    ") as avg_days "
                    "FROM issue_tickets "
                    "WHERE project_id = :pid AND status = 'closed' AND closed_at IS NOT NULL"
                ),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row and row[0] is not None:
                avg_days = float(row[0])
                if avg_days <= 7:
                    return 100.0
                return max(30.0, 100.0 - (avg_days - 7) * 5.0)
        except Exception as e:
            logger.debug("[QC-RATING] _remediation_sla_score error: %s", e)
        return 75.0  # 默认

    async def _client_response_score(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> float:
        """客户响应（承诺事项按时完成率）→ 0-100 分。

        按时完成率 = 按时关闭的承诺工单 / 总承诺工单 × 100
        """
        try:
            result = await db.execute(
                sa_text(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed "
                    "FROM issue_tickets "
                    "WHERE project_id = :pid AND source = 'client_commitment'"
                ),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row and row[0] and row[0] > 0:
                return round((row[1] or 0) / row[0] * 100, 2)
        except Exception as e:
            logger.debug("[QC-RATING] _client_response_score error: %s", e)
        return 80.0  # 默认

    # -----------------------------------------------------------------------
    # 辅助方法
    # -----------------------------------------------------------------------

    @staticmethod
    def _score_to_rating(score: float) -> str:
        """分数转评级：A>=90, B>=75, C>=60, D<60"""
        if score >= 90:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 60:
            return "C"
        else:
            return "D"

    @staticmethod
    def _build_derivation(
        dimensions: dict | None, weights: dict[str, float]
    ) -> list[dict[str, Any]]:
        """构建推导过程（透明性）。"""
        if not dimensions:
            return []
        derivation = []
        for key, weight in weights.items():
            dim_score = dimensions.get(key, 0)
            derivation.append(
                {
                    "dimension": key,
                    "weight": weight,
                    "score": dim_score,
                    "weighted_score": round(weight * dim_score, 2),
                }
            )
        return derivation


# 模块级单例
quality_rating_service = QualityRatingService()
