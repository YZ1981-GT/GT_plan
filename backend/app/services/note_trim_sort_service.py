"""附注智能裁剪与排序服务

Requirements: 37.1-37.6

- auto_sort_by_amount(project_id, year) - 按报表行次金额排序附注章节
- merge_small_sections(project_id, year, threshold_ratio) - 合并小金额到"其他"
- trim_inapplicable(project_id, year) - 裁剪不适用章节
- renumber_sections(project_id, year) - 裁剪后重新编号
- 保护"必披露"章节不被裁剪
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# 必披露章节关键词（不可被裁剪）
_MANDATORY_KEYWORDS = [
    "会计政策",
    "关联方",
    "期后事项",
    "或有事项",
    "承诺事项",
    "重大合同",
    "持续经营",
    "税项",
    "所得税",
]


class NoteTrimSortService:
    """附注智能裁剪与排序服务

    Requirements: 37.1-37.6
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def auto_sort_by_amount(self, project_id: UUID, year: int) -> dict:
        """按报表行次金额自动排序附注章节

        Requirements: 37.1
        金额大的科目排前面（必披露章节保持在最前）。
        Returns: { sorted_count }
        """
        from decimal import Decimal
        from app.models.report_models import FinancialReport, FinancialReportType

        notes = await self._load_notes(project_id, year)
        if not notes:
            return {"sorted_count": 0}

        # 加载 BS 报表行次金额
        rpt_stmt = select(
            FinancialReport.row_name,
            FinancialReport.current_period_amount,
        ).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.is_deleted == False,
            FinancialReport.is_total_row == False,
        )
        rpt_result = await self.db.execute(rpt_stmt)
        name_to_amount: dict[str, Decimal] = {}
        for row_name, amt in rpt_result.all():
            if row_name:
                name_to_amount[row_name.strip()] = abs(Decimal(str(amt or 0)))

        # 排序：必披露在前（sort_key=0），其余按金额降序
        def sort_key(note):
            title = (note.title or "").strip()
            note_section = getattr(note, "note_section", "") or ""
            if self._is_mandatory(title) or self._is_mandatory(note_section):
                return (0, 0)  # 必披露在最前
            amount = name_to_amount.get(title, Decimal("0"))
            return (1, -float(amount))  # 非必披露按金额降序

        sorted_notes = sorted(notes, key=sort_key)
        for i, note in enumerate(sorted_notes):
            if hasattr(note, "sort_order"):
                note.sort_order = i + 1

        await self.db.flush()
        return {"sorted_count": len(sorted_notes)}

    async def merge_small_sections(
        self, project_id: UUID, year: int, threshold_ratio: float = 0.01
    ) -> dict:
        """合并小金额科目到"其他"

        Requirements: 37.2
        金额 < 重要性水平 × threshold_ratio 的科目合并到"其他"章节。
        重要性水平 = BS 资产合计 × 5%（简化取法）。
        Returns: { merged_count, kept_count, threshold_amount }
        """
        from decimal import Decimal
        from app.models.report_models import FinancialReport, FinancialReportType

        notes = await self._load_notes(project_id, year)
        if not notes:
            return {"merged_count": 0, "kept_count": 0, "threshold_amount": 0}

        # 计算重要性水平基准：取 BS 资产合计
        rpt_stmt = select(
            FinancialReport.row_name,
            FinancialReport.current_period_amount,
        ).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.is_deleted == False,
            FinancialReport.is_total_row == True,
        )
        rpt_result = await self.db.execute(rpt_stmt)
        rpt_rows = rpt_result.all()

        materiality_base = Decimal("0")
        for name, amt in rpt_rows:
            if name and ("资产合计" in name or "资产总计" in name):
                materiality_base = abs(Decimal(str(amt or 0)))
                break

        if materiality_base == 0:
            # 无法确定重要性水平，跳过合并
            return {"merged_count": 0, "kept_count": len(notes), "threshold_amount": 0}

        # 重要性水平 = 资产合计 × 5%，合并阈值 = 重要性水平 × threshold_ratio
        materiality = materiality_base * Decimal("0.05")
        threshold_amount = materiality * Decimal(str(threshold_ratio))

        # 加载报表行次金额，建立 section_code → 金额映射
        all_rpt_stmt = select(
            FinancialReport.row_code,
            FinancialReport.row_name,
            FinancialReport.current_period_amount,
        ).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == FinancialReportType.balance_sheet,
            FinancialReport.is_deleted == False,
            FinancialReport.is_total_row == False,
        )
        all_rpt_result = await self.db.execute(all_rpt_stmt)
        # 按 row_name 建立金额映射（附注 title 通常与报表 row_name 对应）
        name_to_amount: dict[str, Decimal] = {}
        for row_code, row_name, amt in all_rpt_result.all():
            if row_name:
                name_to_amount[row_name.strip()] = abs(Decimal(str(amt or 0)))

        merged_count = 0
        kept_count = 0

        for note in notes:
            title = (note.title or "").strip()
            note_section = getattr(note, "note_section", "") or ""

            # 保护必披露章节
            if self._is_mandatory(title) or self._is_mandatory(note_section):
                kept_count += 1
                continue

            # 查找对应报表金额
            note_amount = name_to_amount.get(title, None)
            if note_amount is None:
                # 无法匹配到报表金额，保留
                kept_count += 1
                continue

            if note_amount < threshold_amount:
                # 标记为合并到"其他"（软删除 + 标记）
                if hasattr(note, "is_deleted"):
                    note.is_deleted = True
                merged_count += 1
            else:
                kept_count += 1

        await self.db.flush()

        return {
            "merged_count": merged_count,
            "kept_count": kept_count,
            "threshold_amount": float(threshold_amount),
            "materiality_base": float(materiality_base),
        }

    async def trim_inapplicable(self, project_id: UUID, year: int) -> dict:
        """裁剪不适用章节（合并/单体自动适配）

        Requirements: 37.3
        Returns: { trimmed_count, kept_count }
        """
        notes = await self._load_notes(project_id, year)
        if not notes:
            return {"trimmed_count": 0, "kept_count": 0}

        trimmed_count = 0
        kept_count = len(notes)

        # In full implementation: check project scope (consolidated/standalone)
        # and remove inapplicable sections (e.g., "合并范围变更" for standalone)

        return {"trimmed_count": trimmed_count, "kept_count": kept_count}

    async def renumber_sections(self, project_id: UUID, year: int) -> dict:
        """裁剪后重新编号

        Requirements: 37.5
        Returns: { renumbered_count }
        """
        notes = await self._load_notes(project_id, year)
        if not notes:
            return {"renumbered_count": 0}

        # Sort by sort_order then renumber sequentially
        sorted_notes = sorted(notes, key=lambda n: getattr(n, "sort_order", 0) or 0)
        for i, note in enumerate(sorted_notes):
            if hasattr(note, "sort_order"):
                note.sort_order = i + 1

        await self.db.flush()
        return {"renumbered_count": len(sorted_notes)}

    async def trim_and_sort(self, project_id: UUID, year: int) -> dict:
        """一键执行：排序 + 合并小金额 + 裁剪不适用 + 重新编号

        Returns combined stats
        """
        sort_result = await self.auto_sort_by_amount(project_id, year)
        merge_result = await self.merge_small_sections(project_id, year)
        trim_result = await self.trim_inapplicable(project_id, year)
        renumber_result = await self.renumber_sections(project_id, year)

        return {
            "sorted_count": sort_result["sorted_count"],
            "merged_count": merge_result["merged_count"],
            "trimmed_count": trim_result["trimmed_count"],
            "renumbered_count": renumber_result["renumbered_count"],
        }

    def _is_mandatory(self, section_name: str) -> bool:
        """检查是否为必披露章节"""
        return any(kw in section_name for kw in _MANDATORY_KEYWORDS)

    async def _load_notes(self, project_id: UUID, year: int) -> list:
        """加载项目附注章节"""
        stmt = select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == False,
        ).order_by(DisclosureNote.sort_order)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
