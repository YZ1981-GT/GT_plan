"""程序表自动填充服务

从 procedure_table_templates.json 加载模板定义，
对每个 item 按 auto_data_source 解析自动值，
与 FieldOverrideService 用户覆盖值合并，返回前端渲染数据。

Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.5
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment, Materiality
from app.services.field_override_service import FieldOverrideService

_logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "procedure_table_templates.json"


@lru_cache(maxsize=1)
def _load_templates() -> dict[str, Any]:
    with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_template(table_code: str) -> dict[str, Any] | None:
    """获取单个程序表模板定义"""
    tables = _load_templates().get("tables", {})
    return tables.get(table_code)


def list_table_codes() -> list[str]:
    """返回所有程序表编码"""
    return list(_load_templates().get("tables", {}).keys())


class ProcedureTableService:
    """程序表自动填充+渲染数据服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.override_svc = FieldOverrideService(db)

    async def get_procedure_table(
        self,
        project_id: UUID,
        year: int,
        table_code: str,
        business_category: str = "C",
    ) -> dict[str, Any]:
        """返回完整程序表数据（模板 + 自动值 + 用户覆盖）"""
        template = get_template(table_code)
        if template is None:
            raise ValueError(f"未知程序表编码: {table_code}")

        scope = f"procedure_table:{table_code}"
        overrides = await self.override_svc.get_batch(project_id, year, scope)

        items = []
        for item in template["items"]:
            item_key = str(item["seq"])
            # 自动填充
            auto_values = await self._resolve_auto_values(
                project_id, year, item, business_category
            )
            # 合并覆盖
            user_override = overrides.get(item_key, {})
            merged = FieldOverrideService.merge(auto_values, user_override)

            items.append({
                "_key": item_key,
                "seq": item["seq"],
                "content": item["content"],
                "ref_index": item.get("ref_index", ""),
                **merged,
            })

        return {
            "table_code": table_code,
            "table_name": template["name"],
            "items": items,
        }

    async def _resolve_auto_values(
        self,
        project_id: UUID,
        year: int,
        item: dict[str, Any],
        business_category: str,
    ) -> dict[str, Any]:
        """按 auto_data_source 解析自动值"""
        source = item.get("auto_data_source")
        result: dict[str, Any] = {
            "applicable": self._check_applicable(item, business_category),
            "executor": None,
            "summary": None,
        }

        if not source:
            return result

        try:
            if source == "adjustment_count_aje":
                count = await self._count_adjustments(project_id, year, "aje")
                result["summary"] = f"共{count}笔" if count else "无"
            elif source == "adjustment_count_rje":
                count = await self._count_adjustments(project_id, year, "rje")
                result["summary"] = f"共{count}笔" if count else "无"
            elif source == "adjustment_count_passed":
                count = await self._count_adjustments(project_id, year, "passed")
                result["summary"] = f"共{count}笔" if count else "无"
            elif source == "adjustment_count_consol":
                result["summary"] = "见合并底稿"
            elif source == "misstatement_summary":
                count = await self._count_adjustments(project_id, year, "passed")
                result["summary"] = f"未更正错报{count}笔" if count else "无未更正错报"
            elif source == "misstatement_evaluation":
                result["summary"] = "见 A13-3 评价"
            elif source == "materiality_set":
                mat = await self._get_materiality(project_id)
                result["summary"] = f"重要性水平 {mat:,.0f} 元" if mat else "待设置"
            elif source == "trial_balance_check":
                result["summary"] = "见试算平衡表"
            elif source == "cf_verification_status":
                status = await self._get_cf_verification_status(project_id, year)
                result["summary"] = status
                result["link"] = {"type": "cf_verification", "target": "cash_flow_verification"}
            elif source == "review_progress":
                from app.services.review_workflow_service import ReviewWorkflowService
                rw_svc = ReviewWorkflowService(self.db)
                progress = await rw_svc.get_review_progress(project_id, year)
                result["summary"] = f"复核{progress['submitted']}/{progress['total_levels']}级完成"
            elif source == "workpaper_completion_rate":
                from app.models.workpaper_models import WorkingPaper
                total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
                done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.status.in_(["completed", "reviewed"]),
                )
                total_r = await self.db.execute(total_stmt)
                done_r = await self.db.execute(done_stmt)
                total = total_r.scalar() or 0
                done = done_r.scalar() or 0
                pct = round(done / total * 100) if total else 0
                result["summary"] = f"编制完成{done}/{total}（{pct}%）"
            else:
                # 未实现的 data_source 保留空
                pass
        except Exception as e:
            _logger.warning("auto_data_source %s failed: %s", source, e)

        return result

    def _check_applicable(self, item: dict, business_category: str) -> str:
        """判定适用性：按模板项的 applicable_categories 和项目分类"""
        from app.services.business_category_service import get_category_prefix

        categories = item.get("applicable_categories")
        if not categories:
            return item.get("applicable_default", "yes")

        prefix = get_category_prefix(business_category)
        if prefix in categories:
            return item.get("applicable_default", "yes")
        return "na"

    async def _count_adjustments(self, project_id: UUID, year: int, adj_type: str) -> int:
        """按类型统计调整分录数"""
        if adj_type == "passed":
            # 未更正错报：review_status 枚举无 'passed' 值（draft/pending_review/
            # approved/rejected）。"未更正"的语义标记是 V078 的 passed_reason 列
            # （管理层不予更正原因）非空 → 该调整被 Passed（不予更正）。
            stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.passed_reason.isnot(None),
                Adjustment.is_deleted == sa.false(),
            )
        else:
            stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.adjustment_type == adj_type,
                Adjustment.is_deleted == sa.false(),
            )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_materiality(self, project_id: UUID) -> Decimal:
        stmt = sa.select(Materiality.overall_materiality).where(
            Materiality.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val else Decimal("0")

    async def _get_cf_verification_status(self, project_id: UUID, year: int) -> str:
        """获取 CF 核查完成状态摘要"""
        from app.models.cf_verification_models import CfVerificationResult

        stmt = sa.select(
            sa.func.count(),
            sa.func.count().filter(CfVerificationResult.pass_ == sa.true()),
        ).where(
            CfVerificationResult.project_id == project_id,
            CfVerificationResult.year == year,
        )
        result = await self.db.execute(stmt)
        total, passed = result.one()
        if total == 0:
            return "未执行"
        if passed == total:
            return f"全部通过（{total}项）"
        return f"通过{passed}/{total}项"


def invalidate_cache() -> None:
    _load_templates.cache_clear()
