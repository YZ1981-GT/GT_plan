"""报告占位符替换服务

功能：
- get_placeholders: 从 project.wizard_state.basic_info 构建占位符映射
- replace_in_text: 替换文本中的占位符
- apply_scope_replacements: 根据报表口径替换文本
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 报表口径替换字典（design.md §4.2）
# ---------------------------------------------------------------------------

SCOPE_REPLACEMENTS: dict[str, dict[str, str]] = {
    "consolidated": {
        "财务报表": "合并及母公司财务报表",
        "资产负债表": "合并及母公司资产负债表",
        "利润表": "合并及母公司利润表",
        "现金流量表": "合并及母公司现金流量表",
        "所有者权益变动表": "合并及母公司所有者权益变动表",
        "财务报表附注": "合并及母公司财务报表附注",
    },
    "standalone": {
        # 单体报表不需要替换，保持原文
    },
}


class ReportPlaceholderService:
    """报告占位符替换服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_placeholders(self, project_id: UUID) -> dict[str, str]:
        """从 project.wizard_state.basic_info 构建占位符映射

        占位符清单：
        - entity_name: 被审计单位全称
        - entity_short_name: 简称（默认全称加引号）
        - report_scope: 报表口径
        - audit_period: 审计期间
        - audit_year: 审计年度
        - signing_partner: 签字合伙人
        - report_date: 报告日期
        - firm_name: 事务所名称
        - cpa_name_1: 签字注册会计师1
        - cpa_name_2: 签字注册会计师2
        """
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()

        basic_info: dict = {}
        if project and project.wizard_state:
            state = project.wizard_state
            basic_info = (
                state.get("steps", {}).get("basic_info", {}).get("data")
                or state.get("basic_info", {}).get("data")
                or {}
            )

        entity_name = basic_info.get("client_name") or (project.client_name if project else "[被审计单位名称]")
        entity_short_name = basic_info.get("entity_short_name") or ""
        report_scope = basic_info.get("report_scope") or (project.report_scope if project else "standalone") or "standalone"
        audit_year = str(basic_info.get("audit_year") or "")
        signing_partner = basic_info.get("signing_partner_name") or "[签字注册会计师]"

        return {
            "entity_name": entity_name,
            "entity_short_name": entity_short_name if entity_short_name else f'"{entity_name}"',
            "report_scope": "合并及母公司" if report_scope == "consolidated" else "",
            "audit_period": f"{audit_year}年12月31日" if audit_year else "[审计期间]",
            "audit_year": audit_year or "[审计年度]",
            "signing_partner": signing_partner,
            "report_date": basic_info.get("report_date") or "[报告日期]",
            "firm_name": "致同会计师事务所（特殊普通合伙）",
            "cpa_name_1": basic_info.get("cpa_name_1") or "[注册会计师1]",
            "cpa_name_2": basic_info.get("cpa_name_2") or "[注册会计师2]",
        }

    @staticmethod
    def replace_in_text(text: str, placeholders: dict[str, str]) -> str:
        """替换文本中的 {xxx} 占位符"""
        result = text
        for key, value in placeholders.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    @staticmethod
    def apply_scope_replacements(text: str, report_scope: str) -> str:
        """根据报表口径替换文本

        consolidated → "财务报表" 替换为 "合并及母公司财务报表" 等
        standalone → 不替换
        """
        replacements = SCOPE_REPLACEMENTS.get(report_scope, {})
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
