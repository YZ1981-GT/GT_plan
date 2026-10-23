"""报表上期 / 期初金额来源（spec ``deliverable-trio-generation-accuracy`` §1.3）。

旧实现：上期 = 同一项目 ``year-1`` 的试算表按同一公式重算。真实库项目按年度建立、
同一项目只有单年度试算表 ⇒ 上期恒为 0（2026-10-16 实测四个真实项目所有报表上期均为 0.00）。

正确口径：
- **资产负债表 / 减值准备表**（时点报表）：「期初余额」= 本年试算表 ``opening_balance``
  按同一公式计算（含 ROW 合计）；本年试算表没有任何期初数时为 ``None``（留空，不写 0）。
- **利润表 / 现金流量表 / 权益变动表 / 补充资料**（期间报表）：
  ① 同项目存在 ``year-1`` 试算表 → 沿用同项目上年重算（多年度项目的既有行为）；
  ② 上年项目（``prior_year_project_id``，否则同 ``company_code`` + ``audit_year=year-1`` +
     同口径唯一项目；查找口径与 PREV 共用 ``prior_year_context``）的报表行：编码相同且行名一致优先，否则行名唯一匹配；
  ③ 上年项目只有试算表 → 用本年配置公式在上年项目试算表上求值；
  ④ 都没有 → ``None``。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.models.report_models import FinancialReport, FinancialReportType

logger = logging.getLogger(__name__)

_BALANCE_TYPES = frozenset(
    {FinancialReportType.balance_sheet, FinancialReportType.impairment_provision}
)


class PriorPeriodResolver:
    """单次报表生成内复用的上期解析器（缓存上年项目、期初可用性与 ROW 缓存）。"""

    def __init__(self, db, project_id: UUID, year: int, *, unadjusted: bool = False):
        from app.services.report_engine import ReportFormulaParser

        self.db = db
        self.project_id = project_id
        self.year = year
        self._opening_parser = ReportFormulaParser(db, project_id, year)
        self._opening_parser._use_opening = True
        self._opening_cache: dict[str, Decimal] = {}
        self._has_opening: bool | None = None
        self._same_prior_parser = ReportFormulaParser(db, project_id, year - 1)
        if unadjusted:
            self._same_prior_parser._use_unadjusted = True
        self._same_prior_cache: dict[str, Decimal] = {}
        self._same_has_prior_tb: bool | None = None
        self._prior_project_id: UUID | None = None
        self._prior_project_resolved = False
        self._prior_rows: dict[FinancialReportType, dict[str, Any]] = {}
        self._prior_tb_parser = None
        self._prior_tb_cache: dict[str, Decimal] = {}
        self._prior_has_tb: bool | None = None

    # ------------------------------------------------------------------
    async def prior_amount(self, report_type: FinancialReportType, config) -> Decimal | None:
        """返回该报表行的上期 / 期初金额；无来源返回 ``None``。"""
        formula = getattr(config, "formula", None)
        code = getattr(config, "row_code", None)
        if report_type in _BALANCE_TYPES:
            if not await self._opening_available():
                return None
            value = (
                await self._opening_parser.execute(formula, self._opening_cache)
                if formula
                else Decimal("0")
            )
            if code:
                self._opening_cache[code] = value
            return value

        if await self._same_project_has_prior_tb():
            value = (
                await self._same_prior_parser.execute(formula, self._same_prior_cache)
                if formula
                else Decimal("0")
            )
            if code:
                self._same_prior_cache[code] = value
            return value

        prior_pid = await self._find_prior_project()
        if prior_pid is None:
            return None
        hit = await self._prior_report_value(prior_pid, report_type, config)
        if hit is not _MISSING:
            return hit
        if await self._prior_project_has_tb(prior_pid):
            from app.services.report_engine import ReportFormulaParser

            if self._prior_tb_parser is None:
                self._prior_tb_parser = ReportFormulaParser(self.db, prior_pid, self.year - 1)
            value = (
                await self._prior_tb_parser.execute(formula, self._prior_tb_cache)
                if formula
                else Decimal("0")
            )
            if code:
                self._prior_tb_cache[code] = value
            return value
        return None

    # ------------------------------------------------------------------
    async def _opening_available(self) -> bool:
        if self._has_opening is None:
            from app.models.audit_platform_models import TrialBalance

            hit = (
                await self.db.execute(
                    sa.select(TrialBalance.id).where(
                        TrialBalance.project_id == self.project_id,
                        TrialBalance.year == self.year,
                        TrialBalance.is_deleted == sa.false(),
                        TrialBalance.opening_balance.is_not(None),
                        TrialBalance.opening_balance != 0,
                    ).limit(1)
                )
            ).first()
            self._has_opening = hit is not None
        return self._has_opening

    async def _same_project_has_prior_tb(self) -> bool:
        if self._same_has_prior_tb is None:
            self._same_has_prior_tb = await self._has_tb(self.project_id, self.year - 1)
        return self._same_has_prior_tb

    async def _prior_project_has_tb(self, prior_pid: UUID) -> bool:
        if self._prior_has_tb is None:
            self._prior_has_tb = await self._has_tb(prior_pid, self.year - 1)
        return self._prior_has_tb

    async def _has_tb(self, project_id: UUID, year: int) -> bool:
        from app.services.prior_year_context import has_trial_balance

        return await has_trial_balance(self.db, project_id, year)

    async def _find_prior_project(self) -> UUID | None:
        """上年项目（与 PREV 同一查找口径，``prior_year_context.find_prior_project``）。"""
        if self._prior_project_resolved:
            return self._prior_project_id
        self._prior_project_resolved = True
        from app.services.prior_year_context import find_prior_project

        self._prior_project_id = (await find_prior_project(self.db, self.project_id, self.year)).project_id
        return self._prior_project_id

    async def _prior_report_value(self, prior_pid: UUID, report_type, config):
        from app.services.report_template_binding import normalize_row_label

        cache = self._prior_rows.get(report_type)
        if cache is None:
            rows = (
                await self.db.execute(
                    sa.select(
                        FinancialReport.row_code,
                        FinancialReport.row_name,
                        FinancialReport.current_period_amount,
                    ).where(
                        FinancialReport.project_id == prior_pid,
                        FinancialReport.year == self.year - 1,
                        FinancialReport.report_type == report_type,
                        FinancialReport.is_deleted == sa.false(),
                    )
                )
            ).all()
            by_code = {r.row_code: r for r in rows}
            by_key: dict[tuple[str, str], list[Any]] = {}
            for r in rows:
                by_key.setdefault(normalize_row_label(r.row_name), []).append(r)
            cache = {"by_code": by_code, "by_key": by_key, "empty": not rows}
            self._prior_rows[report_type] = cache
        if cache["empty"]:
            return _MISSING
        key = normalize_row_label(getattr(config, "row_name", None))
        same = cache["by_code"].get(getattr(config, "row_code", None))
        if same is not None and normalize_row_label(same.row_name) == key:
            return same.current_period_amount
        cands = cache["by_key"].get(key) or []
        if len(cands) == 1:
            return cands[0].current_period_amount
        return None


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover
        return "<missing>"


_MISSING = _Missing()
