"""附注科目对照映射服务

Requirements: 23.4, 23.5, 23.6

建立报表行次 → 附注章节 → 表格的三级映射关系。
对每个表格标注校验角色（余额/宽表/交叉/其中项/描述）。
支持从报表行次自动取数填充附注合计行。
支持从试算表明细科目取数填充附注明细行。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_account_mapping import NoteAccountMapping

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MappingEntry:
    """单条映射记录"""
    report_row_code: str
    note_section_code: str
    table_index: int = 0
    validation_role: str | None = None  # 余额/宽表/交叉/其中项/描述
    wp_code: str | None = None
    fetch_mode: str | None = None  # total/detail/category/change


@dataclass
class SectionMapping:
    """章节级映射 — 一个附注章节对应的所有表格映射"""
    section_code: str
    tables: list[MappingEntry] = field(default_factory=list)


@dataclass
class FillResult:
    """填充结果"""
    section_code: str
    filled_cells: int = 0
    total_cells: int = 0
    source: str = ""  # report / tb_detail


# ---------------------------------------------------------------------------
# 默认映射数据（国企版核心科目）
# ---------------------------------------------------------------------------

_SOE_DEFAULT_MAPPINGS: list[dict[str, Any]] = [
    {"report_row_code": "BS-002", "note_section_code": "note_cash", "table_index": 0, "validation_role": "余额", "wp_code": "E1", "fetch_mode": "total"},
    {"report_row_code": "BS-004", "note_section_code": "note_notes_receivable", "table_index": 0, "validation_role": "宽表", "wp_code": "D1", "fetch_mode": "detail"},
    {"report_row_code": "BS-005", "note_section_code": "note_accounts_receivable", "table_index": 0, "validation_role": "其中项", "wp_code": "D2", "fetch_mode": "detail"},
    {"report_row_code": "BS-008", "note_section_code": "note_prepayments", "table_index": 0, "validation_role": "余额", "wp_code": "D3", "fetch_mode": "total"},
    {"report_row_code": "BS-010", "note_section_code": "note_inventory", "table_index": 0, "validation_role": "宽表", "wp_code": "F2", "fetch_mode": "detail"},
    {"report_row_code": "BS-020", "note_section_code": "note_fixed_assets", "table_index": 0, "validation_role": "宽表", "wp_code": "H1", "fetch_mode": "change"},
    {"report_row_code": "BS-025", "note_section_code": "note_intangible_assets", "table_index": 0, "validation_role": "宽表", "wp_code": "I1", "fetch_mode": "change"},
    {"report_row_code": "BS-030", "note_section_code": "note_short_term_borrowings", "table_index": 0, "validation_role": "余额", "wp_code": "L1", "fetch_mode": "total"},
    {"report_row_code": "BS-035", "note_section_code": "note_accounts_payable", "table_index": 0, "validation_role": "余额", "wp_code": "L2", "fetch_mode": "total"},
    {"report_row_code": "BS-040", "note_section_code": "note_employee_benefits", "table_index": 0, "validation_role": "宽表", "wp_code": "J1", "fetch_mode": "change"},
    {"report_row_code": "BS-050", "note_section_code": "note_paid_in_capital", "table_index": 0, "validation_role": "余额", "wp_code": "M1", "fetch_mode": "total"},
    {"report_row_code": "IS-001", "note_section_code": "note_revenue", "table_index": 0, "validation_role": "其中项", "wp_code": "D4", "fetch_mode": "category"},
    {"report_row_code": "IS-002", "note_section_code": "note_cost_of_sales", "table_index": 0, "validation_role": "余额", "wp_code": "F3", "fetch_mode": "total"},
    {"report_row_code": "IS-005", "note_section_code": "note_admin_expenses", "table_index": 0, "validation_role": "其中项", "wp_code": "K1", "fetch_mode": "detail"},
    {"report_row_code": "IS-007", "note_section_code": "note_finance_expenses", "table_index": 0, "validation_role": "其中项", "wp_code": "K3", "fetch_mode": "detail"},
]

_LISTED_DEFAULT_MAPPINGS: list[dict[str, Any]] = [
    {"report_row_code": "BS-002", "note_section_code": "note_cash", "table_index": 0, "validation_role": "余额", "wp_code": "E1", "fetch_mode": "total"},
    {"report_row_code": "BS-005", "note_section_code": "note_accounts_receivable", "table_index": 0, "validation_role": "其中项", "wp_code": "D2", "fetch_mode": "detail"},
    {"report_row_code": "BS-010", "note_section_code": "note_inventory", "table_index": 0, "validation_role": "宽表", "wp_code": "F2", "fetch_mode": "detail"},
    {"report_row_code": "BS-020", "note_section_code": "note_fixed_assets", "table_index": 0, "validation_role": "宽表", "wp_code": "H1", "fetch_mode": "change"},
    {"report_row_code": "BS-025", "note_section_code": "note_intangible_assets", "table_index": 0, "validation_role": "宽表", "wp_code": "I1", "fetch_mode": "change"},
    {"report_row_code": "IS-001", "note_section_code": "note_revenue", "table_index": 0, "validation_role": "其中项", "wp_code": "D4", "fetch_mode": "category"},
]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class NoteAccountMappingService:
    """附注科目对照映射服务"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_mappings_by_template(self, template_type: str) -> list[NoteAccountMapping]:
        """获取指定模板类型的所有映射"""
        if not self.db:
            return []
        stmt = select(NoteAccountMapping).where(
            NoteAccountMapping.template_type == template_type
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_mapping_for_row(self, template_type: str, report_row_code: str) -> list[NoteAccountMapping]:
        """获取指定报表行次的映射"""
        if not self.db:
            return []
        stmt = select(NoteAccountMapping).where(
            NoteAccountMapping.template_type == template_type,
            NoteAccountMapping.report_row_code == report_row_code,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_mapping_for_section(self, template_type: str, section_code: str) -> list[NoteAccountMapping]:
        """获取指定附注章节的映射"""
        if not self.db:
            return []
        stmt = select(NoteAccountMapping).where(
            NoteAccountMapping.template_type == template_type,
            NoteAccountMapping.note_section_code == section_code,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 三级映射构建
    # ------------------------------------------------------------------

    def build_section_mappings(self, mappings: list[NoteAccountMapping]) -> dict[str, SectionMapping]:
        """构建 section_code → SectionMapping 的字典"""
        result: dict[str, SectionMapping] = {}
        for m in mappings:
            if m.note_section_code not in result:
                result[m.note_section_code] = SectionMapping(section_code=m.note_section_code)
            entry = MappingEntry(
                report_row_code=m.report_row_code,
                note_section_code=m.note_section_code,
                table_index=m.table_index,
                validation_role=m.validation_role,
                wp_code=m.wp_code,
                fetch_mode=m.fetch_mode,
            )
            result[m.note_section_code].tables.append(entry)
        return result

    def build_row_to_sections(self, mappings: list[NoteAccountMapping]) -> dict[str, list[str]]:
        """构建 report_row_code → [section_codes] 的映射"""
        result: dict[str, list[str]] = {}
        for m in mappings:
            if m.report_row_code not in result:
                result[m.report_row_code] = []
            if m.note_section_code not in result[m.report_row_code]:
                result[m.report_row_code].append(m.note_section_code)
        return result

    # ------------------------------------------------------------------
    # 从报表行次取数填充附注合计行
    # ------------------------------------------------------------------

    def fill_from_report_row(
        self,
        mapping: MappingEntry,
        report_data: dict[str, Any],
    ) -> FillResult:
        """从报表行次数据填充附注合计行

        Args:
            mapping: 映射条目
            report_data: {row_code: {current_period_amount, prior_period_amount}}
        """
        result = FillResult(section_code=mapping.note_section_code, source="report")
        row_data = report_data.get(mapping.report_row_code)
        if row_data:
            result.total_cells = 2  # 期末 + 期初
            if row_data.get("current_period_amount") is not None:
                result.filled_cells += 1
            if row_data.get("prior_period_amount") is not None:
                result.filled_cells += 1
        return result

    # ------------------------------------------------------------------
    # 从试算表明细科目取数填充附注明细行
    # ------------------------------------------------------------------

    def fill_from_tb_detail(
        self,
        mapping: MappingEntry,
        tb_detail_data: list[dict[str, Any]],
    ) -> FillResult:
        """从试算表明细科目数据填充附注明细行

        Args:
            mapping: 映射条目
            tb_detail_data: [{account_code, account_name, closing_balance, opening_balance}]
        """
        result = FillResult(section_code=mapping.note_section_code, source="tb_detail")
        result.total_cells = len(tb_detail_data) * 2  # 每行期末+期初
        for row in tb_detail_data:
            if row.get("closing_balance") is not None:
                result.filled_cells += 1
            if row.get("opening_balance") is not None:
                result.filled_cells += 1
        return result

    # ------------------------------------------------------------------
    # 种子数据加载
    # ------------------------------------------------------------------

    async def seed_default_mappings(self, template_type: str = "soe") -> int:
        """加载默认映射数据到数据库"""
        if not self.db:
            return 0

        defaults = _SOE_DEFAULT_MAPPINGS if template_type == "soe" else _LISTED_DEFAULT_MAPPINGS
        count = 0
        for item in defaults:
            mapping = NoteAccountMapping(
                id=str(uuid4()),
                template_type=template_type,
                report_row_code=item["report_row_code"],
                note_section_code=item["note_section_code"],
                table_index=item.get("table_index", 0),
                validation_role=item.get("validation_role"),
                wp_code=item.get("wp_code"),
                fetch_mode=item.get("fetch_mode"),
            )
            self.db.add(mapping)
            count += 1
        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 纯内存映射（无 DB 时使用）
    # ------------------------------------------------------------------

    @staticmethod
    def get_default_mappings(template_type: str = "soe") -> list[MappingEntry]:
        """获取默认映射（不依赖数据库）"""
        defaults = _SOE_DEFAULT_MAPPINGS if template_type == "soe" else _LISTED_DEFAULT_MAPPINGS
        return [
            MappingEntry(
                report_row_code=item["report_row_code"],
                note_section_code=item["note_section_code"],
                table_index=item.get("table_index", 0),
                validation_role=item.get("validation_role"),
                wp_code=item.get("wp_code"),
                fetch_mode=item.get("fetch_mode"),
            )
            for item in defaults
        ]
