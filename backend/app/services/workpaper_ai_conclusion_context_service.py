"""AI 结论上下文组装服务

Task 1 (workpaper-ai-conclusion-copilot spec):
为 D1-C / D2-C 科目结论 AI 副驾驶组装结构化上下文。

职责：
- 聚合审定表摘要、程序状态、字段来源、调整影响（D1-C 基础上下文）。
- D2-C 增加函证摘要、坏账/ECL、分析程序结果、披露影响。
- 缺失上下文进入 `missing` 列表，标记来源和影响说明。
- 不直接解析 generated schema，只从 summary_service、field source contract
  和 AI 目标绑定读取。

约束 (1.4):
- 不导入 wp_render_schema_service。
- 不引用 generated/*.yaml 文件。
- 不直接解析 YAML schema。

Requirements: 3.1, 3.2, 3.3
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.account_package_registry_service import AccountPackageRegistryService
from app.services.account_package_summary_service import AccountPackageSummaryService
from app.services.account_package_program_status_service import (
    AccountPackageProgramStatusService,
)

logger = logging.getLogger(__name__)

# 语义注册表路径（只读 field_sources，不解析 generated schema）
_SEMANTIC_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
    / "d1_d2_semantic_registry.json"
)


@dataclass
class MissingContextItem:
    """缺失上下文条目"""

    source: str
    reason: str
    impact: str


@dataclass
class AIConclusionContext:
    """AI 结论上下文 DTO

    结构化数据用于 AI 结论草稿生成 prompt。
    """

    project_id: str
    account_package_id: str
    wp_code: str
    conclusion_sheet: str
    audit_sheet_summary: dict = field(default_factory=dict)
    program_status_summary: dict = field(default_factory=dict)
    field_sources: dict = field(default_factory=dict)
    confirmation_summary: dict = field(default_factory=dict)
    bad_debt_ecl: dict = field(default_factory=dict)
    analysis_summary: dict = field(default_factory=dict)
    adjustment_impact: dict = field(default_factory=dict)
    disclosure_impact: dict = field(default_factory=dict)
    missing: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """序列化为 dict（用于 prompt 注入和 API 响应）"""
        return {
            "project_id": self.project_id,
            "account_package_id": self.account_package_id,
            "wp_code": self.wp_code,
            "conclusion_sheet": self.conclusion_sheet,
            "audit_sheet_summary": self.audit_sheet_summary,
            "program_status_summary": self.program_status_summary,
            "field_sources": self.field_sources,
            "confirmation_summary": self.confirmation_summary,
            "bad_debt_ecl": self.bad_debt_ecl,
            "analysis_summary": self.analysis_summary,
            "adjustment_impact": self.adjustment_impact,
            "disclosure_impact": self.disclosure_impact,
            "missing": self.missing,
        }


class WorkpaperAIConclusionContextService:
    """AI 结论上下文组装服务

    从 account_package_summary_service、program_status_service 和
    语义注册表 field_sources 契约读取，不直接解析 generated schema。
    """

    def __init__(
        self,
        db: AsyncSession,
        registry_service: AccountPackageRegistryService | None = None,
    ) -> None:
        self._db = db
        self._registry = registry_service or AccountPackageRegistryService()
        self._summary_service = AccountPackageSummaryService(db, self._registry)
        self._program_status_service = AccountPackageProgramStatusService(db)

    async def build_context(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
    ) -> AIConclusionContext:
        """组装 AI 结论上下文

        根据 wp_code 自动区分 D1-C / D2-C 上下文深度。
        """
        pkg = self._registry.get_package(account_package_id)
        if pkg is None:
            return AIConclusionContext(
                project_id=str(project_id),
                account_package_id=account_package_id,
                wp_code="",
                conclusion_sheet="",
                missing=[{
                    "source": "registry",
                    "reason": "package_not_found",
                    "impact": "无法获取工作包注册信息，上下文组装终止",
                }],
            )

        wp_code = pkg.get("primary_wp_code", "")
        conclusion_sheet = f"{wp_code}-C"

        missing: list[dict] = []

        # 1. 审定表摘要（D1/D2 共用）
        audit_sheet_summary = self._get_audit_sheet_summary(pkg, missing)

        # 2. 程序状态摘要
        program_status_summary = await self._get_program_status_summary(
            project_id, account_package_id, missing
        )

        # 3. 字段来源（从语义注册表契约读取）
        field_sources = self._get_field_sources(wp_code, missing)

        # 4. 调整影响（D1/D2 共用）
        adjustment_impact = self._get_adjustment_impact(pkg, missing)

        # D2 特有上下文
        confirmation_summary: dict = {}
        bad_debt_ecl: dict = {}
        analysis_summary: dict = {}
        disclosure_impact: dict = {}

        if wp_code == "D2":
            # 5. 函证摘要
            confirmation_summary = await self._get_confirmation_summary(
                project_id, account_package_id, missing
            )
            # 6. 坏账/ECL
            bad_debt_ecl = self._get_bad_debt_ecl(pkg, missing)
            # 7. D2-5 分析程序
            analysis_summary = self._get_analysis_summary(pkg, missing)
            # 8. 披露影响
            disclosure_impact = self._get_disclosure_impact(pkg, missing)

        return AIConclusionContext(
            project_id=str(project_id),
            account_package_id=account_package_id,
            wp_code=wp_code,
            conclusion_sheet=conclusion_sheet,
            audit_sheet_summary=audit_sheet_summary,
            program_status_summary=program_status_summary,
            field_sources=field_sources,
            confirmation_summary=confirmation_summary,
            bad_debt_ecl=bad_debt_ecl,
            analysis_summary=analysis_summary,
            adjustment_impact=adjustment_impact,
            disclosure_impact=disclosure_impact,
            missing=missing,
        )

    # ------------------------------------------------------------------
    # 私有方法：各上下文模块提取
    # ------------------------------------------------------------------

    def _get_audit_sheet_summary(
        self, pkg: dict, missing: list[dict]
    ) -> dict:
        """从注册表 sheets 提取审定表摘要"""
        audit_sheets = [
            {
                "sheet_name": s.get("sheet_name", ""),
                "source_wp_code": s.get("source_wp_code", ""),
            }
            for s in pkg.get("sheets", [])
            if s.get("sheet_type") == "audit_sheet"
        ]
        if not audit_sheets:
            missing.append({
                "source": "audit_sheet_summary",
                "reason": "no_audit_sheet_in_registry",
                "impact": "审定表数据不可用，AI 无法引用期初/期末差异",
            })
            return {}
        return {
            "has_audit_sheet": True,
            "audit_sheets": audit_sheets,
            "count": len(audit_sheets),
        }

    async def _get_program_status_summary(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        missing: list[dict],
    ) -> dict:
        """从 program_status_service 获取程序状态汇总"""
        statuses = await self._program_status_service.get_all_statuses(
            project_id, account_package_id
        )
        if not statuses:
            missing.append({
                "source": "program_status_summary",
                "reason": "no_program_status_records",
                "impact": "审计程序执行状态不可用，AI 无法判断程序完成情况",
            })
            return {}

        total = len(statuses)
        completed = sum(1 for s in statuses if s.status == "completed")
        pending = sum(1 for s in statuses if s.status == "pending")
        not_applicable = sum(1 for s in statuses if s.status == "not_applicable")

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "not_applicable": not_applicable,
            "completion_rate": completed / total if total > 0 else 0,
        }

    def _get_field_sources(
        self, wp_code: str, missing: list[dict]
    ) -> dict:
        """从语义注册表 field_sources 契约读取字段来源

        不解析 generated schema，只读 d1_d2_semantic_registry.json 中
        明确声明的 field_sources 条目。
        """
        registry = self._load_semantic_registry()
        if registry is None:
            missing.append({
                "source": "field_sources",
                "reason": "semantic_registry_not_found",
                "impact": "字段来源契约不可用，AI 无法引用字段溯源信息",
            })
            return {}

        # 收集该 wp_code 下所有有 field_sources 的 sheet
        sources: dict[str, Any] = {}
        for sheet_name, entry in registry.get("sheets", {}).items():
            if entry.get("wp_code") != wp_code:
                continue
            sheet_field_sources = entry.get("field_sources")
            if sheet_field_sources:
                sources[sheet_name] = sheet_field_sources

        if not sources:
            missing.append({
                "source": "field_sources",
                "reason": "no_field_sources_for_wp_code",
                "impact": "字段来源契约无对应条目，AI 无法展示来源追溯",
            })
            return {}

        return {
            "has_field_sources": True,
            "sheets_with_sources": list(sources.keys()),
            "field_source_entries": sources,
        }

    def _get_adjustment_impact(
        self, pkg: dict, missing: list[dict]
    ) -> dict:
        """从注册表识别调整分录影响"""
        adj_sheets = [
            {
                "sheet_name": s.get("sheet_name", ""),
                "source_wp_code": s.get("source_wp_code", ""),
            }
            for s in pkg.get("sheets", [])
            if s.get("sheet_type") == "adjustment"
        ]
        downstream = pkg.get("downstream", [])

        if not adj_sheets:
            missing.append({
                "source": "adjustment_impact",
                "reason": "no_adjustment_sheets",
                "impact": "调整分录信息不可用，AI 无法引用审计调整金额",
            })
            return {}

        return {
            "has_adjustments": True,
            "adjustment_sheets": adj_sheets,
            "downstream_affected": downstream,
        }

    async def _get_confirmation_summary(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        missing: list[dict],
    ) -> dict:
        """从 summary_service 读取函证摘要（D2 特有）"""
        summary = await self._summary_service.get_confirmation_summary(
            project_id, account_package_id
        )
        status = summary.get("status", "missing")
        if status == "missing":
            missing.append({
                "source": "confirmation_summary",
                "reason": "confirmation_service_no_data",
                "impact": "函证覆盖率和差异金额无法引用",
            })
            return {}
        if status == "not_applicable":
            return {"status": "not_applicable"}
        return summary

    def _get_bad_debt_ecl(
        self, pkg: dict, missing: list[dict]
    ) -> dict:
        """从注册表识别坏账/ECL 相关 sheets（D2 特有）

        D2-3, D2-8, D2-9, D2-10 相关 sheets。
        """
        ecl_keywords = ["坏账", "减值", "ECL", "预期信用损失", "账龄"]
        ecl_sheets = []
        for sheet in pkg.get("sheets", []):
            name = sheet.get("sheet_name", "")
            sheet_type = sheet.get("sheet_type", "")
            if any(kw in name for kw in ecl_keywords) and sheet_type == "analysis":
                ecl_sheets.append({
                    "sheet_name": name,
                    "sheet_type": sheet_type,
                    "source_wp_code": sheet.get("source_wp_code", ""),
                })

        if not ecl_sheets:
            missing.append({
                "source": "bad_debt_ecl",
                "reason": "no_ecl_analysis_sheets",
                "impact": "坏账/ECL 分析数据不可用，AI 无法引用减值测算结论",
            })
            return {}

        return {
            "has_ecl_data": True,
            "ecl_sheets": ecl_sheets,
            "count": len(ecl_sheets),
        }

    def _get_analysis_summary(
        self, pkg: dict, missing: list[dict]
    ) -> dict:
        """从注册表识别 D2-5 分析程序（D2 特有）"""
        analysis_sheets = [
            {
                "sheet_name": s.get("sheet_name", ""),
                "source_wp_code": s.get("source_wp_code", ""),
            }
            for s in pkg.get("sheets", [])
            if s.get("sheet_type") == "analysis"
        ]

        if not analysis_sheets:
            missing.append({
                "source": "analysis_summary",
                "reason": "no_analysis_sheets",
                "impact": "分析程序结果不可用，AI 无法引用趋势和差异分析",
            })
            return {}

        return {
            "has_analysis": True,
            "analysis_sheets": analysis_sheets,
            "count": len(analysis_sheets),
        }

    def _get_disclosure_impact(
        self, pkg: dict, missing: list[dict]
    ) -> dict:
        """从注册表识别披露影响（D2 特有）"""
        disclosure_sheets = [
            {
                "sheet_name": s.get("sheet_name", ""),
                "schema_ref": s.get("schema_ref"),
            }
            for s in pkg.get("sheets", [])
            if s.get("sheet_type") == "disclosure"
        ]

        if not disclosure_sheets:
            missing.append({
                "source": "disclosure_impact",
                "reason": "no_disclosure_sheets",
                "impact": "附注披露信息不可用，AI 无法引用披露要求",
            })
            return {}

        return {
            "has_disclosure": True,
            "disclosure_sheets": disclosure_sheets,
            "count": len(disclosure_sheets),
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _load_semantic_registry(self) -> dict | None:
        """加载语义注册表（只读 field_sources 契约，不解析 generated schema）"""
        try:
            if not _SEMANTIC_REGISTRY_PATH.exists():
                return None
            with open(_SEMANTIC_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load semantic registry: %s", e)
            return None
