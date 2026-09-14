"""科目工作包结论上下文服务 — Facade

Task 7.2: D2-C 结论上下文向 workpaper-ai-conclusion-copilot 暴露结构化字段。

此文件为向后兼容 facade：
- get_conclusion_context 委托给 WorkpaperAIConclusionContextService（canonical）
- get_pending_ai_drafts / has_pending_ai_draft 保持原有实现（唯一职责）

Requirements: 2.5, 3.4
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import AiContentLog
from app.services.account_package_registry_service import AccountPackageRegistryService
from app.services.account_package_summary_service import AccountPackageSummaryService
from app.services.workpaper_ai_conclusion_context_service import (
    WorkpaperAIConclusionContextService,
    AIConclusionContext,
)


@dataclass
class ConclusionContext:
    """结论上下文 DTO，暴露给 AI copilot（向后兼容）"""

    account_package_id: str
    wp_code: str
    sheet_type: str = "conclusion"
    field_sources: list[dict] = field(default_factory=list)
    confirmation_summary: dict = field(default_factory=dict)
    bad_debt_ecl: dict = field(default_factory=dict)
    analysis_summary: dict = field(default_factory=dict)
    adjustment_impact: dict = field(default_factory=dict)
    disclosure_impact: dict = field(default_factory=dict)


def _convert_ai_context_to_conclusion_context(
    ai_ctx: AIConclusionContext,
) -> ConclusionContext:
    """将 canonical AIConclusionContext 转为旧 ConclusionContext 格式"""
    # field_sources: 新服务返回 dict，旧接口期望 list[dict]
    field_sources_list: list[dict] = []
    if ai_ctx.field_sources:
        entries = ai_ctx.field_sources.get("field_source_entries", {})
        for sheet_name, sources in entries.items():
            if isinstance(sources, list):
                for src in sources:
                    field_sources_list.append({"sheet_name": sheet_name, **src})
            elif isinstance(sources, dict):
                field_sources_list.append({"sheet_name": sheet_name, **sources})

    return ConclusionContext(
        account_package_id=ai_ctx.account_package_id,
        wp_code=ai_ctx.wp_code,
        sheet_type="conclusion",
        field_sources=field_sources_list,
        confirmation_summary=ai_ctx.confirmation_summary,
        bad_debt_ecl=ai_ctx.bad_debt_ecl,
        analysis_summary=ai_ctx.analysis_summary,
        adjustment_impact=ai_ctx.adjustment_impact,
        disclosure_impact=ai_ctx.disclosure_impact,
    )


class AccountPackageConclusionContextService:
    """科目工作包结论上下文服务 — Facade

    get_conclusion_context 委托给 WorkpaperAIConclusionContextService。
    get_pending_ai_drafts / has_pending_ai_draft 保持本地实现。
    """

    def __init__(
        self,
        db: AsyncSession,
        registry_service: AccountPackageRegistryService | None = None,
    ) -> None:
        self._db = db
        self._registry = registry_service or AccountPackageRegistryService()
        self._delegate = WorkpaperAIConclusionContextService(db, self._registry)

    async def get_conclusion_context(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        wp_id: uuid.UUID | None = None,
    ) -> ConclusionContext:
        """获取结论上下文（委托给 canonical 服务后转换格式）"""
        ai_ctx = await self._delegate.build_context(project_id, account_package_id)
        return _convert_ai_context_to_conclusion_context(ai_ctx)

    async def get_pending_ai_drafts(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        wp_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """读取工作包 pending AI 草稿（Task 7.3）

        从现有 ai_content_log 表读取，不重复建表。
        使用 target_cell 前缀匹配定位到特定工作包。

        AI 草稿定位必须包含：account_package_id, wp_id, sheet_type, field_id。
        target_cell 格式: "workpaper:<wp_id>:<field_id>"

        Returns:
            list of pending AI draft records with locator info
        """
        # 构建查询：从 ai_content_log 读取 pending 状态的记录
        stmt = (
            select(AiContentLog)
            .where(
                AiContentLog.project_id == project_id,
                AiContentLog.confirm_action == "pending",
            )
        )

        # 如果有 wp_id，限定到特定底稿
        if wp_id is not None:
            stmt = stmt.where(AiContentLog.wp_id == wp_id)
        else:
            # 尝试解析 primary_wp_code 到 wp_id
            pkg = self._registry.get_package(account_package_id)
            if pkg:
                primary_wp_code = pkg.get("primary_wp_code", "")
                summary_service = AccountPackageSummaryService(self._db, self._registry)
                resolved_wp_id = await summary_service.resolve_wp_code_to_id(
                    project_id, primary_wp_code
                )
                if resolved_wp_id:
                    stmt = stmt.where(AiContentLog.wp_id == resolved_wp_id)

        stmt = stmt.order_by(AiContentLog.generated_at.desc()).limit(20)

        result = await self._db.execute(stmt)
        records = result.scalars().all()

        drafts = []
        for rec in records:
            # 解析 target_cell 提取 field_id
            target_cell = rec.target_cell or ""
            parts = target_cell.split(":")
            field_id = parts[2] if len(parts) >= 3 else None

            drafts.append({
                "id": str(rec.id),
                "account_package_id": account_package_id,
                "wp_id": str(rec.wp_id) if rec.wp_id else None,
                "sheet_type": "conclusion",
                "field_id": field_id,
                "generated_content": rec.generated_content,
                "model": rec.model,
                "confidence": float(rec.confidence) if rec.confidence else None,
                "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
            })

        return drafts

    async def has_pending_ai_draft(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        wp_id: uuid.UUID | None = None,
    ) -> bool:
        """检查工作包是否有 pending AI 草稿（Task 7.3）

        从现有 ai_content_log 表快速计数，不重复建表。
        """
        stmt = (
            select(func.count())
            .select_from(AiContentLog)
            .where(
                AiContentLog.project_id == project_id,
                AiContentLog.confirm_action == "pending",
            )
        )

        if wp_id is not None:
            stmt = stmt.where(AiContentLog.wp_id == wp_id)
        else:
            pkg = self._registry.get_package(account_package_id)
            if pkg:
                primary_wp_code = pkg.get("primary_wp_code", "")
                summary_service = AccountPackageSummaryService(self._db, self._registry)
                resolved_wp_id = await summary_service.resolve_wp_code_to_id(
                    project_id, primary_wp_code
                )
                if resolved_wp_id:
                    stmt = stmt.where(AiContentLog.wp_id == resolved_wp_id)

        result = await self._db.execute(stmt)
        count = result.scalar_one()
        return int(count or 0) > 0
