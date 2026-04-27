"""报表数据快照服务

功能：
- create_snapshot: 从 report_engine 生成快照 + 计算 trial_balance 哈希
- get_latest_snapshot: 获取最新快照
- check_stale: 比较当前哈希与快照哈希，检测是否过期
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.phase13_models import ReportSnapshot
from app.models.report_models import FinancialReport, FinancialReportType

logger = logging.getLogger(__name__)

# 报表类型简称映射
_REPORT_TYPE_MAP = {
    "BS": FinancialReportType.balance_sheet,
    "IS": FinancialReportType.income_statement,
    "CFS": FinancialReportType.cash_flow_statement,
    "EQ": FinancialReportType.equity_statement,
}


class ReportSnapshotService:
    """报表数据快照服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _compute_trial_balance_hash(
        self, project_id: UUID, year: int
    ) -> str:
        """计算 trial_balance 数据的 MD5 哈希

        查询项目+年度的所有试算表行，序列化为 JSON 后取 MD5。
        """
        result = await self.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
            )
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        rows = result.all()

        # 序列化为稳定的 JSON 字符串
        data_str = json.dumps(
            [
                {"code": r[0], "amount": str(r[1]) if r[1] is not None else None}
                for r in rows
            ],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.md5(data_str.encode("utf-8")).hexdigest()

    async def create_snapshot(
        self,
        project_id: UUID,
        year: int,
        user_id: UUID,
    ) -> list[ReportSnapshot]:
        """为四张报表创建数据快照

        1. 计算 trial_balance 哈希
        2. 从 financial_report 读取各报表行数据
        3. 序列化为 JSONB 存入 report_snapshot
        """
        tb_hash = await self._compute_trial_balance_hash(project_id, year)
        snapshots = []

        for short_type, report_type in _REPORT_TYPE_MAP.items():
            # 读取报表行数据
            result = await self.db.execute(
                sa.select(FinancialReport)
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.is_deleted == sa.false(),
                )
                .order_by(FinancialReport.row_code)
            )
            rows = result.scalars().all()

            # 序列化行数据
            data = {
                "rows": [
                    {
                        "row_code": r.row_code,
                        "row_name": r.row_name,
                        "current_period_amount": str(r.current_period_amount) if r.current_period_amount is not None else None,
                        "prior_period_amount": str(r.prior_period_amount) if r.prior_period_amount is not None else None,
                        "indent_level": r.indent_level,
                        "is_total_row": r.is_total_row,
                    }
                    for r in rows
                ]
            }

            snapshot = ReportSnapshot(
                project_id=project_id,
                year=year,
                report_type=short_type,
                data=data,
                source_trial_balance_hash=tb_hash,
                created_by=user_id,
            )
            self.db.add(snapshot)
            snapshots.append(snapshot)

        await self.db.flush()
        logger.info(
            "创建报表快照: project_id=%s, year=%d, hash=%s",
            project_id, year, tb_hash,
        )
        return snapshots

    async def get_latest_snapshot(
        self,
        project_id: UUID,
        year: int,
        report_type: str,
    ) -> ReportSnapshot | None:
        """获取最新快照"""
        result = await self.db.execute(
            sa.select(ReportSnapshot)
            .where(
                ReportSnapshot.project_id == project_id,
                ReportSnapshot.year == year,
                ReportSnapshot.report_type == report_type,
            )
            .order_by(ReportSnapshot.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def check_stale(self, snapshot_id: UUID) -> bool:
        """检测快照是否过期

        比较当前 trial_balance 哈希与快照保存的哈希。
        返回 True 表示数据已变更（过期）。
        """
        result = await self.db.execute(
            sa.select(ReportSnapshot).where(ReportSnapshot.id == snapshot_id)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return True

        current_hash = await self._compute_trial_balance_hash(
            snapshot.project_id, snapshot.year
        )
        return current_hash != snapshot.source_trial_balance_hash
