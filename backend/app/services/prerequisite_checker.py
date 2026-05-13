"""前置条件校验器 — 每个生成操作前自动检查依赖数据是否就绪

Validates: Requirements F26 / Design D8

依赖链路：
    tb_balance → account_mapping → trial_balance → financial_report → working_papers/disclosure_notes

4 个操作的前置条件：
    - recalc: account_mapping 存在且 rate >= 50%
    - generate_reports: trial_balance > 0 行
    - generate_workpapers: template_set 已选择
    - generate_notes: financial_report > 0 行
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountMapping, TbBalance, TrialBalance
from app.models.report_models import FinancialReport
from app.models.core import Project
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class PrerequisiteChecker:
    """通用前置条件校验器，每个操作调用前自动检查"""

    async def check(self, db: AsyncSession, project_id: UUID, year: int, action: str) -> dict:
        """检查指定操作的前置条件是否满足。

        Args:
            db: 数据库会话
            project_id: 项目 ID
            year: 年度
            action: 操作名称，支持 "recalc" | "generate_reports" | "generate_workpapers" | "generate_notes"

        Returns:
            dict: {ok: bool, message: str, prerequisite_action: str | None}
        """
        checks = {
            "recalc": self._check_recalc_prerequisites,
            "generate_reports": self._check_report_prerequisites,
            "generate_workpapers": self._check_workpaper_prerequisites,
            "generate_notes": self._check_notes_prerequisites,
        }
        checker = checks.get(action)
        if not checker:
            return {"ok": True, "message": "", "prerequisite_action": None}
        return await checker(db, project_id, year)

    async def _check_recalc_prerequisites(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> dict:
        """recalc 前置条件：account_mapping 存在且映射率 >= 50%"""
        # 统计客户科目总数（从 tb_balance 去重 account_code）
        tb_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, year
        )
        total_accounts_result = await db.execute(
            sa.select(sa.func.count(sa.distinct(TbBalance.account_code))).where(tb_filter)
        )
        total_accounts = total_accounts_result.scalar_one() or 0

        if total_accounts == 0:
            return {
                "ok": False,
                "message": "请先导入账套数据（当前无余额表数据）",
                "prerequisite_action": "import_ledger",
            }

        # 统计已映射科目数
        mapping_count_result = await db.execute(
            sa.select(sa.func.count()).select_from(AccountMapping).where(
                AccountMapping.project_id == project_id,
                AccountMapping.is_deleted == sa.false(),
            )
        )
        mapping_count = mapping_count_result.scalar_one() or 0

        if mapping_count == 0:
            return {
                "ok": False,
                "message": "请先完成科目映射（当前映射率 0%）",
                "prerequisite_action": "auto_match",
            }

        # 计算映射率
        rate = round(mapping_count / total_accounts * 100, 1) if total_accounts > 0 else 0

        if rate < 50:
            return {
                "ok": False,
                "message": f"请先完成科目映射（当前映射率 {rate}%）",
                "prerequisite_action": "auto_match",
            }

        return {"ok": True, "message": "", "prerequisite_action": None}

    async def _check_report_prerequisites(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> dict:
        """generate_reports 前置条件：trial_balance > 0 行"""
        tb_count_result = await db.execute(
            sa.select(sa.func.count()).select_from(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_count = tb_count_result.scalar_one() or 0

        if tb_count == 0:
            return {
                "ok": False,
                "message": "请先执行试算表重算",
                "prerequisite_action": "recalc",
            }

        return {"ok": True, "message": "", "prerequisite_action": None}

    async def _check_workpaper_prerequisites(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> dict:
        """generate_workpapers 前置条件：template_set 已选择"""
        project_result = await db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        if project is None:
            return {
                "ok": False,
                "message": "项目不存在",
                "prerequisite_action": None,
            }

        # 检查 wizard_state 中是否有 template_set 配置
        wizard_state = project.wizard_state or {}
        template_set_data = wizard_state.get("template_set", {})
        template_set_id = template_set_data.get("template_set_id") if isinstance(template_set_data, dict) else None

        if not template_set_id:
            return {
                "ok": False,
                "message": "请先选择底稿模板集",
                "prerequisite_action": "select_template",
            }

        return {"ok": True, "message": "", "prerequisite_action": None}

    async def _check_notes_prerequisites(
        self, db: AsyncSession, project_id: UUID, year: int
    ) -> dict:
        """generate_notes 前置条件：financial_report > 0 行"""
        report_count_result = await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        report_count = report_count_result.scalar_one() or 0

        if report_count == 0:
            return {
                "ok": False,
                "message": "请先生成财务报表",
                "prerequisite_action": "generate_reports",
            }

        return {"ok": True, "message": "", "prerequisite_action": None}
