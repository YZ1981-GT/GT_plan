"""金额解析器抽象 (AmountResolver) — 公式引擎统一 L3 取数适配层

把"金额从哪取"抽象为可注入接口，让公式引擎的一套求值逻辑
同时服务单体报表、合并报表、附注、底稿、预览等多个数据源。

设计原则（关联 ADR-CONSOL-101 / design.md §四 组件3）：
- Resolver 只负责"取数"，不含公式解析/求值（那是 L1 内核的职责）。
- 单体注入 TrialBalanceResolver（读 trial_balance.audited_amount 等列，保留列名映射 + 未审模式）。
- 合并注入 ConsolTrialResolver（读 consol_trial.consol_amount）。
- 附注注入 NoteResolver（读 disclosure_notes.table_data JSONB）。
- 底稿注入 WPResolver（读 working_paper.parsed_data JSONB）。
- 预览注入 DisplayResolver（返回 Decimal("0")，mock/preview 模式）。
- 全程 Decimal，无 float 中转（关联属性 Q6）。

Validates: Requirements 1.1, 1.2, 1.7, 3.2
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.consolidation_models import ConsolTrial
from app.models.report_models import DisclosureNote
from app.models.workpaper_models import WpIndex, WorkingPaper

# 列名 → TrialBalance 字段映射（与 report_engine._COLUMN_MAP 保持一致）
_COLUMN_MAP = {
    "期末余额": "audited_amount",
    "审定数": "audited_amount",
    "年初余额": "opening_balance",
    "期初余额": "opening_balance",
    "本期发生额": "_period_amount",  # special: audited - opening
    "未审数": "unadjusted_amount",
    "RJE调整": "rje_adjustment",
    "AJE调整": "aje_adjustment",
}


@runtime_checkable
class AmountResolver(Protocol):
    """金额解析协议：公式引擎经此取数，与数据源解耦。

    resolve_tb  — 解析单个科目金额（TB 函数）。
    resolve_sum — 解析科目区间合计（SUM_TB 函数）。
    """

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        ...

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        ...


class TrialBalanceResolver:
    """单体报表数据源：读 trial_balance。

    完整保留原 report_engine._resolve_tb/_resolve_sum_tb 的列名映射 +
    未审模式 + 行缓存语义（R1：复用引擎不破坏单体行为）。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int, *, use_unadjusted: bool = False):
        self.db = db
        self.project_id = project_id
        self.year = year
        self._use_unadjusted = use_unadjusted
        self._tb_cache: dict[str, TrialBalance | None] = {}

    async def _get_tb_row(self, account_code: str) -> TrialBalance | None:
        if account_code in self._tb_cache:
            return self._tb_cache[account_code]
        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == self.project_id,
                TrialBalance.year == self.year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        self._tb_cache[account_code] = row
        return row

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        row = await self._get_tb_row(account_code)
        if row is None:
            return Decimal("0")

        if self._use_unadjusted and column_name in ("期末余额", "审定数"):
            return row.unadjusted_amount or Decimal("0")

        field = _COLUMN_MAP.get(column_name)
        if field is None:
            return Decimal("0")

        if field == "_period_amount":
            amount = (row.unadjusted_amount or Decimal("0")) if self._use_unadjusted else (row.audited_amount or Decimal("0"))
            opening = row.opening_balance or Decimal("0")
            return amount - opening

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start_code, end_code = parts[0].strip(), parts[1].strip()

        field = _COLUMN_MAP.get(column_name)
        if field is None:
            return Decimal("0")

        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == self.project_id,
                TrialBalance.year == self.year,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()

        total = Decimal("0")
        for row in rows:
            if self._use_unadjusted and column_name in ("期末余额", "审定数"):
                total += row.unadjusted_amount or Decimal("0")
            elif field == "_period_amount":
                amount = (row.unadjusted_amount or Decimal("0")) if self._use_unadjusted else (row.audited_amount or Decimal("0"))
                opening = row.opening_balance or Decimal("0")
                total += amount - opening
            else:
                val = getattr(row, field, None)
                total += val if val is not None else Decimal("0")
            self._tb_cache[row.standard_account_code] = row

        return total


class ConsolTrialResolver:
    """合并报表数据源：读 consol_trial.consol_amount。

    取数口径与原 consol_report_service._resolve_consol_tb/_resolve_sum_consol 一致
    （迁移逻辑不改语义）：忽略列名，统一返回 consol_amount（合并数）。
    全程 async（A3：消除 sync self.db.query 的 MissingGreenlet 风险）。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int):
        self.db = db
        self.project_id = project_id
        self.year = year

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        result = await self.db.execute(
            sa.select(ConsolTrial.consol_amount).where(
                ConsolTrial.project_id == self.project_id,
                ConsolTrial.year == self.year,
                ConsolTrial.standard_account_code == account_code,
                ConsolTrial.is_deleted.is_(False),
            )
        )
        val = result.scalar_one_or_none()
        return val if val is not None else Decimal("0")

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start_code, end_code = parts[0].strip(), parts[1].strip()

        result = await self.db.execute(
            sa.select(ConsolTrial.consol_amount).where(
                ConsolTrial.project_id == self.project_id,
                ConsolTrial.year == self.year,
                ConsolTrial.standard_account_code >= start_code,
                ConsolTrial.standard_account_code <= end_code,
                ConsolTrial.is_deleted.is_(False),
            )
        )
        total = Decimal("0")
        for (val,) in result.all():
            if val is not None:
                total += val
        return total


class NoteResolver:
    """附注数据源（NOTE 函数）：读 disclosure_notes.table_data JSONB。

    取数逻辑：按 note_section（section_code）定位附注行，
    从 table_data JSONB 中按 field_name 提取金额。
    table_data 结构约定：{field_name: amount_value, ...} 或嵌套行列结构。
    全程 Decimal，无 float 中转。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int):
        self.db = db
        self.project_id = project_id
        self.year = year

    async def resolve_tb(self, section_code: str, field_name: str) -> Decimal:
        """按 note_section 查找附注，从 table_data 中提取指定字段金额。"""
        result = await self.db.execute(
            sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == self.project_id,
                DisclosureNote.year == self.year,
                DisclosureNote.note_section == section_code,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        table_data = result.scalar_one_or_none()
        if table_data is None:
            return Decimal("0")

        # table_data 是 JSONB，按 field_name 提取金额
        val = table_data.get(field_name) if isinstance(table_data, dict) else None
        if val is None:
            return Decimal("0")
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    async def resolve_sum(self, code_range: str, field_name: str) -> Decimal:
        """按 note_section 范围汇总附注金额。

        code_range 格式："section_start~section_end"（字符串范围比较）。
        """
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start_code, end_code = parts[0].strip(), parts[1].strip()

        result = await self.db.execute(
            sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == self.project_id,
                DisclosureNote.year == self.year,
                DisclosureNote.note_section >= start_code,
                DisclosureNote.note_section <= end_code,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        total = Decimal("0")
        for (table_data,) in result.all():
            if table_data is None or not isinstance(table_data, dict):
                continue
            val = table_data.get(field_name)
            if val is None:
                continue
            try:
                total += Decimal(str(val))
            except Exception:
                continue
        return total


class WPResolver:
    """底稿数据源（WP 函数）：读 working_paper.parsed_data JSONB。

    取数逻辑：通过 wp_index.wp_code 定位底稿索引，再关联 working_paper
    从 parsed_data JSONB 中按 column 提取金额。
    parsed_data 结构约定：{column_name: amount_value, ...}。
    全程 Decimal，无 float 中转。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int):
        self.db = db
        self.project_id = project_id
        self.year = year

    async def resolve_tb(self, wp_code: str, column: str) -> Decimal:
        """按 wp_code 查找底稿，从 parsed_data 中提取指定列金额。"""
        # 先通过 wp_index 找到 wp_index_id，再关联 working_paper
        result = await self.db.execute(
            sa.select(WorkingPaper.parsed_data).where(
                WorkingPaper.project_id == self.project_id,
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.wp_index_id == sa.select(WpIndex.id).where(
                    WpIndex.project_id == self.project_id,
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted == sa.false(),
                ).correlate_except(WpIndex).scalar_subquery(),
            )
        )
        parsed_data = result.scalar_one_or_none()
        if parsed_data is None:
            return Decimal("0")

        # parsed_data 是 JSONB，按 column 提取金额
        val = parsed_data.get(column) if isinstance(parsed_data, dict) else None
        if val is None:
            return Decimal("0")
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    async def resolve_sum(self, code_range: str, column: str) -> Decimal:
        """按 wp_code 范围汇总底稿金额。

        code_range 格式："wp_code_start~wp_code_end"（字符串范围比较）。
        """
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start_code, end_code = parts[0].strip(), parts[1].strip()

        result = await self.db.execute(
            sa.select(WorkingPaper.parsed_data).where(
                WorkingPaper.project_id == self.project_id,
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.wp_index_id.in_(
                    sa.select(WpIndex.id).where(
                        WpIndex.project_id == self.project_id,
                        WpIndex.wp_code >= start_code,
                        WpIndex.wp_code <= end_code,
                        WpIndex.is_deleted == sa.false(),
                    )
                ),
            )
        )
        total = Decimal("0")
        for (parsed_data,) in result.all():
            if parsed_data is None or not isinstance(parsed_data, dict):
                continue
            val = parsed_data.get(column)
            if val is None:
                continue
            try:
                total += Decimal(str(val))
            except Exception:
                continue
        return total


class DisplayResolver:
    """预览/mock 数据源（for formula preview, returns mock/zero values）。

    用于公式预览模式：所有取数请求返回 Decimal("0")，
    不触碰数据库，不需要 db session。
    替代 cell_formula_evaluator 的预览职责中的 DSL 部分。
    """

    def __init__(self) -> None:
        """DisplayResolver 不需要 db/project_id/year，纯 mock。"""
        pass

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        """预览模式：返回 Decimal("0")。"""
        return Decimal("0")

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        """预览模式：返回 Decimal("0")。"""
        return Decimal("0")
