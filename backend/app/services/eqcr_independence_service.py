"""EQCR 年度独立性声明服务

Refinement Round 5 任务 23 — 需求 12

功能：
- 年度独立性声明提交/查询（落 ``annual_independence_declarations`` 表）
- 登录守卫：EQCR/partner/qc 无本年度声明时阻断访问 EQCR 工作台
- 声明问题集从 ``backend/data/independence_questions_annual.json`` 加载
  （唯一真源，不重复维护 Python 常量）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.independence_models import AnnualIndependenceDeclaration

logger = logging.getLogger(__name__)

# 年度声明问题集路径（唯一真源）
_QUESTIONS_PATH = (
    Path(__file__).parent.parent.parent / "data" / "independence_questions_annual.json"
)


def _count_risk_flags(answers: dict) -> int:
    """计算 'yes' 回答数（有风险回答数），用于抽查排序。"""
    if not isinstance(answers, dict):
        return 0
    return sum(1 for v in answers.values() if str(v).lower() == "yes")


class EqcrIndependenceService:
    """年度独立性声明服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_annual_declaration(
        self,
        user_id: UUID,
        year: int | None = None,
    ) -> bool:
        """检查用户是否已提交本年度独立性声明。"""
        target_year = year or datetime.now(timezone.utc).year

        stmt = sa.select(AnnualIndependenceDeclaration.id).where(
            AnnualIndependenceDeclaration.declarant_id == user_id,
            AnnualIndependenceDeclaration.declaration_year == target_year,
            AnnualIndependenceDeclaration.is_deleted == False,  # noqa: E712
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return row is not None

    async def submit_annual_declaration(
        self,
        user_id: UUID,
        year: int | None = None,
        answers: dict | None = None,
    ) -> dict:
        """提交年度独立性声明。

        - 若本年度已存在记录：更新（允许修正）
        - 若不存在：新建
        """
        target_year = year or datetime.now(timezone.utc).year
        answers_dict = answers or {}
        risk_count = _count_risk_flags(answers_dict)
        now = datetime.now(timezone.utc)

        # 查已有
        stmt = sa.select(AnnualIndependenceDeclaration).where(
            AnnualIndependenceDeclaration.declarant_id == user_id,
            AnnualIndependenceDeclaration.declaration_year == target_year,
            AnnualIndependenceDeclaration.is_deleted == False,  # noqa: E712
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            existing.answers = answers_dict
            existing.risk_flagged_count = risk_count
            existing.submitted_at = now
            record = existing
        else:
            record = AnnualIndependenceDeclaration(
                declarant_id=user_id,
                declaration_year=target_year,
                answers=answers_dict,
                risk_flagged_count=risk_count,
                submitted_at=now,
            )
            self.db.add(record)

        await self.db.flush()

        return {
            "status": "submitted",
            "year": target_year,
            "submitted_at": now.isoformat(),
            "risk_flagged_count": risk_count,
        }

    def get_annual_questions(self) -> list[dict]:
        """加载年度独立性声明问题集（JSON 唯一真源）。"""
        if _QUESTIONS_PATH.exists():
            with open(_QUESTIONS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.error(
            "[INDEPENDENCE] questions JSON not found at %s", _QUESTIONS_PATH
        )
        return []
