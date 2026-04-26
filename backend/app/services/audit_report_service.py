"""审计报告服务 — 模板加载 + 报告生成 + 段落编辑 + 财务数据刷新

核心功能：
- load_seed_templates: 从 JSON 种子数据加载审计报告模板
- generate_report: 根据意见类型+公司类型加载模板→填充占位符→写入 audit_report 表
- update_paragraph: 更新指定段落内容
- refresh_financial_data: 从 financial_report 取关键财务数据
- validate_finalize: finalize 前校验（上市公司 KAM 必填）

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventPayload
from app.models.report_models import (
    AuditReport,
    AuditReportTemplate,
    CompanyType,
    FinancialReport,
    FinancialReportType,
    OpinionType,
    ReportStatus,
)

logger = logging.getLogger(__name__)

SEED_DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "audit_report_templates_seed.json"
)


def _load_seed_data() -> dict:
    """加载审计报告模板种子数据"""
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


class AuditReportService:
    """审计报告服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 模板种子数据加载
    # ------------------------------------------------------------------
    async def load_seed_templates(self) -> int:
        """从 JSON 种子数据加载审计报告模板（幂等）。

        Validates: Requirements 6.1, 6.2
        """
        seed = _load_seed_data()
        templates = seed.get("templates", [])
        loaded = 0

        for tmpl_group in templates:
            opinion_type = OpinionType(tmpl_group["opinion_type"])
            company_type = CompanyType(tmpl_group["company_type"])

            for section in tmpl_group.get("sections", []):
                section_name = section["section_name"]
                section_order = section["section_order"]
                template_text = section["template_text"]
                is_required = section.get("is_required", True)

                # Upsert: check existing
                existing = await self.db.execute(
                    sa.select(AuditReportTemplate).where(
                        AuditReportTemplate.opinion_type == opinion_type,
                        AuditReportTemplate.company_type == company_type,
                        AuditReportTemplate.section_name == section_name,
                        AuditReportTemplate.is_deleted == sa.false(),
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.section_order = section_order
                    row.template_text = template_text
                    row.is_required = is_required
                else:
                    row = AuditReportTemplate(
                        opinion_type=opinion_type,
                        company_type=company_type,
                        section_name=section_name,
                        section_order=section_order,
                        template_text=template_text,
                        is_required=is_required,
                    )
                    self.db.add(row)
                loaded += 1

        await self.db.flush()
        return loaded

    # ------------------------------------------------------------------
    # 获取项目基本信息
    # ------------------------------------------------------------------
    async def _get_project_basic_info(self, project_id: UUID) -> dict:
        """从 project.wizard_state 读取 basic_info"""
        from app.models.core import Project
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()
        if not project or not project.wizard_state:
            return {}
        state = project.wizard_state
        return (
            state.get("steps", {}).get("basic_info", {}).get("data")
            or state.get("basic_info", {}).get("data")
            or {}
        )

    # ------------------------------------------------------------------
    # 获取模板列表
    # ------------------------------------------------------------------
    async def get_templates(
        self,
        opinion_type: OpinionType | None = None,
        company_type: CompanyType | None = None,
    ) -> list[AuditReportTemplate]:
        """获取审计报告模板列表"""
        query = sa.select(AuditReportTemplate).where(
            AuditReportTemplate.is_deleted == sa.false(),
        )
        if opinion_type:
            query = query.where(AuditReportTemplate.opinion_type == opinion_type)
        if company_type:
            query = query.where(AuditReportTemplate.company_type == company_type)
        query = query.order_by(
            AuditReportTemplate.opinion_type,
            AuditReportTemplate.company_type,
            AuditReportTemplate.section_order,
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 生成审计报告
    # ------------------------------------------------------------------
    async def generate_report(
        self,
        project_id: UUID,
        year: int,
        opinion_type: OpinionType,
        company_type: CompanyType = CompanyType.non_listed,
    ) -> AuditReport:
        """根据意见类型+公司类型加载模板→填充占位符→写入 audit_report 表。

        Validates: Requirements 6.3, 6.4
        """
        # 1. Load templates for the given opinion_type + company_type
        templates = await self._load_templates(opinion_type, company_type)
        if not templates:
            raise ValueError(
                f"未找到模板: opinion_type={opinion_type.value}, "
                f"company_type={company_type.value}"
            )

        # 2. Fetch financial data from financial_report
        financial_data = await self._fetch_financial_data(project_id, year)

        # 2b. Fetch project basic_info for entity_name etc.
        basic_info = await self._get_project_basic_info(project_id)

        # 3. Build paragraphs dict with placeholders filled
        placeholders = self._build_placeholders(project_id, year, financial_data, basic_info)
        paragraphs: dict[str, str] = {}
        for tmpl in templates:
            filled_text = self._fill_placeholders(tmpl.template_text, placeholders)
            paragraphs[tmpl.section_name] = filled_text

        # 4. Upsert audit_report
        existing = await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
                AuditReport.is_deleted == sa.false(),
            )
        )
        report = existing.scalar_one_or_none()

        if report:
            report.opinion_type = opinion_type
            report.company_type = company_type
            report.paragraphs = paragraphs
            report.financial_data = financial_data
            report.status = ReportStatus.draft
        else:
            report = AuditReport(
                project_id=project_id,
                year=year,
                opinion_type=opinion_type,
                company_type=company_type,
                paragraphs=paragraphs,
                financial_data=financial_data,
                status=ReportStatus.draft,
            )
            self.db.add(report)

        await self.db.flush()
        return report

    async def _load_templates(
        self,
        opinion_type: OpinionType,
        company_type: CompanyType,
    ) -> list[AuditReportTemplate]:
        """加载指定意见类型+公司类型的模板段落。

        策略：先加载完全匹配的段落，对于缺失的段落从 unqualified 同公司类型补充。
        """
        # Full match
        result = await self.db.execute(
            sa.select(AuditReportTemplate)
            .where(
                AuditReportTemplate.opinion_type == opinion_type,
                AuditReportTemplate.company_type == company_type,
                AuditReportTemplate.is_deleted == sa.false(),
            )
            .order_by(AuditReportTemplate.section_order)
        )
        templates = list(result.scalars().all())

        # If not unqualified and we only have the opinion paragraph,
        # supplement with unqualified templates for other sections
        if opinion_type != OpinionType.unqualified:
            existing_sections = {t.section_name for t in templates}
            fallback = await self.db.execute(
                sa.select(AuditReportTemplate)
                .where(
                    AuditReportTemplate.opinion_type == OpinionType.unqualified,
                    AuditReportTemplate.company_type == company_type,
                    AuditReportTemplate.is_deleted == sa.false(),
                )
                .order_by(AuditReportTemplate.section_order)
            )
            for fb_tmpl in fallback.scalars().all():
                if fb_tmpl.section_name not in existing_sections:
                    templates.append(fb_tmpl)

        # Sort by section_order
        templates.sort(key=lambda t: t.section_order)
        return templates

    async def _fetch_financial_data(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """从 financial_report 获取关键财务数据。

        Validates: Requirements 6.4
        """
        data: dict[str, str] = {}

        key_rows = {
            "total_assets": (FinancialReportType.balance_sheet, "BS-021"),
            "total_liabilities": (FinancialReportType.balance_sheet, "BS-044"),
            "total_equity": (FinancialReportType.balance_sheet, "BS-056"),
            "total_revenue": (FinancialReportType.income_statement, "IS-001"),
            "net_profit": (FinancialReportType.income_statement, "IS-019"),
        }

        for key, (report_type, row_code) in key_rows.items():
            result = await self.db.execute(
                sa.select(FinancialReport.current_period_amount).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.row_code == row_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            val = result.scalar_one_or_none()
            data[key] = str(val) if val is not None else "0"

        return data

    def _build_placeholders(
        self,
        project_id: UUID,
        year: int,
        financial_data: dict,
        basic_info: dict | None = None,
    ) -> dict[str, str]:
        """构建占位符替换字典，从项目基本信息读取单位名称等"""
        info = basic_info or {}
        entity_name = info.get("client_name") or "[被审计单位名称]"
        report_scope = info.get("report_scope") or "standalone"
        # 简称默认留空让用户手动填入
        entity_short_name = info.get("entity_short_name") or ""
        signing_partner = info.get("signing_partner_name") or "[签字注册会计师]"

        return {
            "entity_name": entity_name,
            "entity_short_name": entity_short_name if entity_short_name else f'"{entity_name}"',
            "audit_period": f"{year}年12月31日",
            "audit_year": str(year),
            "total_assets": financial_data.get("total_assets", "0"),
            "total_liabilities": financial_data.get("total_liabilities", "0"),
            "total_equity": financial_data.get("total_equity", "0"),
            "total_revenue": financial_data.get("total_revenue", "0"),
            "net_profit": financial_data.get("net_profit", "0"),
            "report_date": "[报告日期]",
            "signing_partner": signing_partner,
            "report_scope": "合并及母公司" if report_scope == "consolidated" else "",
        }

    def _fill_placeholders(self, text: str, placeholders: dict[str, str]) -> str:
        """替换模板文本中的占位符"""
        result = text
        for key, value in placeholders.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    # ------------------------------------------------------------------
    # 获取审计报告
    # ------------------------------------------------------------------
    async def get_report(
        self,
        project_id: UUID,
        year: int,
    ) -> AuditReport | None:
        """获取审计报告"""
        result = await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
                AuditReport.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 段落编辑 (Task 13.3)
    # ------------------------------------------------------------------
    async def update_paragraph(
        self,
        report_id: UUID,
        section_name: str,
        content: str,
    ) -> AuditReport | None:
        """更新审计报告指定段落内容。

        Validates: Requirements 6.6
        """
        result = await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.id == report_id,
                AuditReport.is_deleted == sa.false(),
            )
        )
        report = result.scalar_one_or_none()
        if report is None:
            return None

        paragraphs = dict(report.paragraphs) if report.paragraphs else {}
        paragraphs[section_name] = content
        report.paragraphs = paragraphs
        await self.db.flush()
        return report

    # ------------------------------------------------------------------
    # 财务数据刷新 (Task 13.4)
    # ------------------------------------------------------------------
    async def refresh_financial_data(
        self,
        project_id: UUID,
        year: int,
    ) -> AuditReport | None:
        """刷新审计报告中的财务数据引用。

        Validates: Requirements 6.5
        """
        report = await self.get_report(project_id, year)
        if report is None:
            return None

        financial_data = await self._fetch_financial_data(project_id, year)
        report.financial_data = financial_data
        await self.db.flush()
        return report

    async def on_reports_updated(self, payload: EventPayload) -> None:
        """监听 reports_updated 事件，刷新审计报告财务数据。

        Validates: Requirements 6.5
        """
        logger.info(
            "AuditReportService.on_reports_updated: project=%s",
            payload.project_id,
        )
        year = payload.year
        if not year:
            logger.warning("on_reports_updated: missing year, skipping")
            return

        await self.refresh_financial_data(payload.project_id, year)
        await self.db.flush()

    # ------------------------------------------------------------------
    # 状态更新 + KAM 校验 (Task 13.5)
    # ------------------------------------------------------------------
    async def update_status(
        self,
        report_id: UUID,
        status: ReportStatus,
    ) -> AuditReport | None:
        """更新审计报告状态，finalize 时执行 KAM 校验。

        Validates: Requirements 6.7
        """
        result = await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.id == report_id,
                AuditReport.is_deleted == sa.false(),
            )
        )
        report = result.scalar_one_or_none()
        if report is None:
            return None

        # KAM validation for listed companies when finalizing
        if status == ReportStatus.final:
            validation_error = self._validate_finalize(report)
            if validation_error:
                raise ValueError(validation_error)

        report.status = status
        await self.db.flush()
        return report

    def _validate_finalize(self, report: AuditReport) -> str | None:
        """finalize 前校验。

        Validates: Requirements 6.7
        """
        if report.company_type == CompanyType.listed:
            paragraphs = report.paragraphs or {}
            kam_content = paragraphs.get("关键审计事项段", "")
            # Check if KAM section has actual content beyond the template boilerplate
            if not kam_content or "[请在此处添加关键审计事项]" in kam_content:
                return (
                    "上市公司审计报告必须包含至少一个关键审计事项(KAM)，"
                    "请编辑「关键审计事项段」后再定稿"
                )
        return None
