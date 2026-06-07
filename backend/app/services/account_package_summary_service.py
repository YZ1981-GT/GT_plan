"""科目工作包摘要服务

职责：
- 读取注册表，解析 wp_code 到 wp_id。
- 聚合 sheet 列表、程序状态（placeholder）、外部卡片、stale 状态。
- 缺失 sheet/schema 时返回 missing_sources 卡片但不阻断工作包打开。
- 函证摘要只读取 confirmation_service 暴露的 summary/metrics，
  不维护函证明细，不覆盖函证状态。

边界声明（Task 6.1）：
- D0 = 销售循环函证底稿汇总视图。
- ConfirmationHub / confirmation_service 是函证事实唯一真源。
- D1/D2 工作包只消费函证 summary/metrics（覆盖率、差异金额、未解决事项）。
- 本服务不得写入、删除、更新 confirmation 相关表。
- 函证无数据时返回 {status: "missing", coverage_rate: null}，
  不在底稿侧自行计算覆盖率。

Requirements: 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex
from app.models.confirmation_models import Confirmation
from app.services.account_package_registry_service import AccountPackageRegistryService

logger = logging.getLogger(__name__)

# 生产 schema 根目录
_PRODUCTION_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
)


@dataclass
class AccountPackageSummaryDTO:
    """工作包摘要 DTO"""

    registry_status: str  # "loaded" | "not_found" | "invalid"
    mapping_status: str  # effective mapping status
    program_status_summary: dict = field(default_factory=lambda: {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "not_applicable": 0,
    })
    external_cards: list[dict] = field(default_factory=list)
    stale_summary: dict = field(default_factory=lambda: {
        "has_stale": False,
        "stale_items": [],
    })
    missing_sources: list[dict] = field(default_factory=list)


class AccountPackageSummaryService:
    """科目工作包摘要服务"""

    def __init__(
        self,
        db: AsyncSession,
        registry_service: AccountPackageRegistryService | None = None,
    ) -> None:
        self._db = db
        self._registry = registry_service or AccountPackageRegistryService()

    async def resolve_wp_code_to_id(
        self, project_id: uuid.UUID, wp_code: str
    ) -> uuid.UUID | None:
        """解析 wp_code 到项目内 wp_id（WpIndex.id）"""
        stmt = select(WpIndex.id).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == wp_code,
            WpIndex.is_deleted == False,  # noqa: E712
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def get_summary(
        self, project_id: uuid.UUID, account_package_id: str
    ) -> AccountPackageSummaryDTO:
        """获取工作包摘要

        即使部分 sheet/schema 缺失，仍返回摘要（missing_sources 列出缺失项）。
        """
        pkg = self._registry.get_package(account_package_id)
        if pkg is None:
            return AccountPackageSummaryDTO(
                registry_status="not_found",
                mapping_status="unknown",
            )

        # Validate registry
        errors = self._registry.validate()
        if errors:
            logger.warning("Registry validation errors: %s", errors)

        # Effective mapping status
        mapping_status = self._registry.get_effective_mapping_status(pkg)

        # Resolve wp_codes and detect missing sources
        missing_sources: list[dict] = []
        sheets = pkg.get("sheets", [])
        source_wp_codes = set()
        for sheet in sheets:
            code = sheet.get("source_wp_code")
            if code:
                source_wp_codes.add(code)

        # Check wp_code resolution
        for code in source_wp_codes:
            wp_id = await self.resolve_wp_code_to_id(project_id, code)
            if wp_id is None:
                # Find all sheets referencing this missing wp_code
                for sheet in sheets:
                    if sheet.get("source_wp_code") == code:
                        missing_sources.append({
                            "wp_code": code,
                            "sheet_name": sheet.get("sheet_name", ""),
                            "reason": "wp_index_not_found",
                        })

        # Check schema file existence
        for sheet in sheets:
            schema_ref = sheet.get("schema_ref")
            if schema_ref:
                schema_path = _PRODUCTION_SCHEMA_DIR / schema_ref
                if not schema_path.exists():
                    missing_sources.append({
                        "wp_code": sheet.get("source_wp_code", pkg.get("primary_wp_code", "")),
                        "sheet_name": sheet.get("sheet_name", ""),
                        "reason": "schema_file_not_found",
                    })

        # External cards
        external_cards = []
        for card_type in pkg.get("external_cards", []):
            external_cards.append({
                "card_type": card_type,
                "status": "placeholder",
                "summary_data": {},
                "jump_link": f"/confirmations?type={card_type}",
            })

        # Program status — placeholder until Task 3
        total_programs = len([
            s for s in sheets if s.get("sheet_type") == "procedure"
        ])
        program_status_summary = {
            "total": total_programs,
            "completed": 0,
            "pending": total_programs,
            "not_applicable": 0,
        }

        # Stale summary — placeholder
        stale_summary = {
            "has_stale": False,
            "stale_items": [],
        }

        return AccountPackageSummaryDTO(
            registry_status="loaded",
            mapping_status=mapping_status,
            program_status_summary=program_status_summary,
            external_cards=external_cards,
            stale_summary=stale_summary,
            missing_sources=missing_sources,
        )

    def get_package_list(self, cycle: str | None = None) -> list[dict]:
        """获取工作包列表（从注册表）"""
        if cycle:
            return self._registry.get_packages_by_cycle(cycle)
        return self._registry.get_packages()

    def get_package_detail(self, account_package_id: str) -> dict | None:
        """获取单个工作包详情（从注册表）"""
        return self._registry.get_package(account_package_id)

    async def get_confirmation_summary(
        self, project_id: uuid.UUID, account_package_id: str
    ) -> dict:
        """读取函证事实真源摘要（只读消费，不写入）

        Task 6.2: D2 摘要从 confirmation_service 读取函证 metrics。
        本方法只做 SELECT 聚合，不会 INSERT/UPDATE/DELETE confirmation 表。

        当 confirmation_service 无数据时返回 {status: "missing", coverage_rate: null}，
        不在底稿侧自行计算覆盖率。

        Returns:
            dict with keys: status, total, sent, returned, matched, discrepancy,
                            coverage_rate, diff_total
        """
        pkg = self._registry.get_package(account_package_id)
        if pkg is None:
            return {"status": "missing", "coverage_rate": None}

        # 检查该工作包是否有 confirmation_summary 外部卡片
        external_cards = pkg.get("external_cards", [])
        if "confirmation_summary" not in external_cards:
            return {"status": "not_applicable", "coverage_rate": None}

        # 从 confirmation 表只读聚合（confirmation_service 是唯一真源）
        primary_wp_code = pkg.get("primary_wp_code", "")
        wp_id = await self.resolve_wp_code_to_id(project_id, primary_wp_code)

        if wp_id is None:
            return {"status": "missing", "coverage_rate": None}

        # 只读查询：按 project_id 和关联 wp_id 统计函证状态
        stmt = (
            select(
                Confirmation.status,
                func.count().label("cnt"),
            )
            .where(
                Confirmation.project_id == project_id,
                Confirmation.wp_id == wp_id,
            )
            .group_by(Confirmation.status)
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        if not rows:
            return {"status": "missing", "coverage_rate": None}

        # 聚合结果
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row[0]] = row[1]

        total = sum(status_counts.values())
        returned = status_counts.get("returned", 0)
        matched = status_counts.get("matched", 0)
        discrepancy = status_counts.get("discrepancy", 0)

        # 覆盖率 = (已回函 + 相符 + 差异) / 总数
        responded = returned + matched + discrepancy
        coverage_rate = responded / total if total > 0 else None

        # 差异总额 — 只读聚合
        diff_stmt = (
            select(func.coalesce(func.sum(Confirmation.diff_amount), 0))
            .where(
                Confirmation.project_id == project_id,
                Confirmation.wp_id == wp_id,
                Confirmation.status == "discrepancy",
            )
        )
        diff_result = await self._db.execute(diff_stmt)
        diff_total = float(diff_result.scalar_one() or 0)

        return {
            "status": "loaded",
            "total": total,
            "sent": status_counts.get("sent", 0),
            "returned": returned,
            "matched": matched,
            "discrepancy": discrepancy,
            "coverage_rate": coverage_rate,
            "diff_total": diff_total,
        }
