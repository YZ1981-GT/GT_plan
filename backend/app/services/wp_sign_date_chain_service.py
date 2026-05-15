"""签字日期链校验 — 编制日期≤复核日期≤合伙人签字日期≤审计报告日

Sprint 11 Task 11.9
"""

from __future__ import annotations

import uuid
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DateChainViolation:
    """日期链违规"""
    def __init__(self, field1: str, date1: date, field2: str, date2: date, message: str):
        self.field1 = field1
        self.date1 = date1
        self.field2 = field2
        self.date2 = date2
        self.message = message

    def to_dict(self) -> dict:
        return {
            "field1": self.field1,
            "date1": self.date1.isoformat() if self.date1 else None,
            "field2": self.field2,
            "date2": self.date2.isoformat() if self.date2 else None,
            "message": self.message,
        }


class WpSignDateChainService:
    """签字日期链校验服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_date_chain(
        self,
        *,
        wp_id: uuid.UUID,
        preparation_date: Optional[date] = None,
        review_date: Optional[date] = None,
        partner_sign_date: Optional[date] = None,
        report_date: Optional[date] = None,
    ) -> dict:
        """校验签字日期链：编制≤复核≤合伙人≤报告日"""
        violations = []

        dates = [
            ("preparation_date", "编制日期", preparation_date),
            ("review_date", "复核日期", review_date),
            ("partner_sign_date", "合伙人签字日期", partner_sign_date),
            ("report_date", "审计报告日", report_date),
        ]

        # 逐对比较
        for i in range(len(dates) - 1):
            field1, label1, d1 = dates[i]
            field2, label2, d2 = dates[i + 1]
            if d1 and d2 and d1 > d2:
                violations.append(DateChainViolation(
                    field1=field1,
                    date1=d1,
                    field2=field2,
                    date2=d2,
                    message=f"{label1}({d1}) 不应晚于 {label2}({d2})",
                ))

        return {
            "wp_id": str(wp_id),
            "valid": len(violations) == 0,
            "violations": [v.to_dict() for v in violations],
        }

    async def validate_project_date_chain(
        self,
        *,
        project_id: uuid.UUID,
    ) -> dict:
        """校验项目内所有底稿的签字日期链"""
        # Stub: 实际实现遍历项目所有底稿的签字记录
        return {
            "project_id": str(project_id),
            "total_checked": 0,
            "violations": [],
        }
