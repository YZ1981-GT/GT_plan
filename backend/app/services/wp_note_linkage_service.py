"""附注联动服务 — 附注取数+一致性校验+一键取数

Sprint 10 Task 10.12
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WpNoteLinkageService:
    """底稿与附注联动服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_note_data(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
        note_section_code: str,
    ) -> dict:
        """从底稿/试算表取数填入附注"""
        # 查询试算表中对应科目的审定数
        stmt = text("""
            SELECT standard_account_code, audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :yr
            ORDER BY standard_account_code
        """)
        result = await self.db.execute(stmt, {"pid": str(project_id), "yr": year})
        rows = result.fetchall()

        data = {}
        for row in rows:
            data[row[0]] = float(row[1]) if row[1] else 0.0

        return {
            "note_section_code": note_section_code,
            "source": "trial_balance",
            "data": data,
        }

    async def check_consistency(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
    ) -> dict:
        """校验附注与底稿/试算表数据一致性"""
        inconsistencies = []

        # Stub: 实际实现比对 disclosure_notes 中的金额与 trial_balance 审定数
        return {
            "project_id": str(project_id),
            "year": year,
            "consistent": len(inconsistencies) == 0,
            "inconsistencies": inconsistencies,
        }

    async def one_click_fetch(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
    ) -> dict:
        """一键取数 — 批量从试算表/底稿取数填入所有附注节"""
        updated_sections = 0

        # Stub: 实际实现遍历所有附注节，调用 fetch_note_data 填充
        logger.info(
            "One-click fetch for project=%s year=%s, updated %d sections",
            project_id, year, updated_sections,
        )

        return {
            "project_id": str(project_id),
            "year": year,
            "updated_sections": updated_sections,
        }
