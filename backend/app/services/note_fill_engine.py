"""附注数据填充引擎 — 4 种取数模式 + 自动填充 + 填充率统计

Requirements: 36.1, 36.2, 36.3, 25.1-25.6

模式 1（合计取数）：从底稿审定表合计行取期末/期初余额
模式 2（明细取数）：从底稿审定表明细行逐行取数
模式 3（分类取数）：从底稿按类别汇总（如按账龄/按性质）
模式 4（变动取数）：从底稿本期增加/减少列取数
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class FetchMode(str, Enum):
    """取数模式"""
    TOTAL = "total"       # 合计取数
    DETAIL = "detail"     # 明细取数
    CATEGORY = "category" # 分类取数
    CHANGE = "change"     # 变动取数


@dataclass
class CellValue:
    """单元格填充值"""
    row_index: int
    col_name: str
    value: Decimal | str | None
    source: str = ""  # tb/wp/report/adjustment/manual
    is_auto: bool = True


@dataclass
class FillStats:
    """填充率统计"""
    total_cells: int = 0
    filled_cells: int = 0
    unfillable_cells: int = 0  # 标记为"待填写"

    @property
    def fill_rate(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return round(self.filled_cells / self.total_cells * 100, 1)


@dataclass
class SectionFillResult:
    """章节填充结果"""
    section_code: str
    cells: list[CellValue] = field(default_factory=list)
    stats: FillStats = field(default_factory=FillStats)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fill Engine
# ---------------------------------------------------------------------------

class NoteFillEngine:
    """附注数据填充引擎

    支持 4 种取数模式，从试算表/底稿/报表自动填充附注表格数据。
    """

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 模式 1：合计取数
    # ------------------------------------------------------------------

    def fetch_total(
        self,
        section_code: str,
        wp_data: dict[str, Any] | None = None,
        report_row_data: dict[str, Any] | None = None,
    ) -> SectionFillResult:
        """模式 1（合计取数）：从底稿审定表合计行取期末/期初余额

        Args:
            section_code: 附注章节编码
            wp_data: 底稿数据 {total_row: {period_end, period_start}}
            report_row_data: 报表行次数据 {current_period_amount, prior_period_amount}
        """
        result = SectionFillResult(section_code=section_code)
        cells: list[CellValue] = []

        # 优先从底稿取数
        source_data = wp_data or {}
        total_row = source_data.get("total_row", {})

        period_end = total_row.get("period_end") or (
            report_row_data.get("current_period_amount") if report_row_data else None
        )
        period_start = total_row.get("period_start") or (
            report_row_data.get("prior_period_amount") if report_row_data else None
        )

        result.stats.total_cells = 2
        if period_end is not None:
            cells.append(CellValue(row_index=0, col_name="期末余额", value=Decimal(str(period_end)), source="wp"))
            result.stats.filled_cells += 1
        else:
            result.stats.unfillable_cells += 1

        if period_start is not None:
            cells.append(CellValue(row_index=0, col_name="期初余额", value=Decimal(str(period_start)), source="wp"))
            result.stats.filled_cells += 1
        else:
            result.stats.unfillable_cells += 1

        result.cells = cells
        return result

    # ------------------------------------------------------------------
    # 模式 2：明细取数
    # ------------------------------------------------------------------

    def fetch_detail(
        self,
        section_code: str,
        detail_rows: list[dict[str, Any]] | None = None,
    ) -> SectionFillResult:
        """模式 2（明细取数）：从底稿审定表明细行逐行取数

        Args:
            section_code: 附注章节编码
            detail_rows: [{name, period_end, period_start, ...}]
        """
        result = SectionFillResult(section_code=section_code)
        cells: list[CellValue] = []
        rows = detail_rows or []

        result.stats.total_cells = len(rows) * 2  # 每行期末+期初

        for i, row in enumerate(rows):
            pe = row.get("period_end")
            ps = row.get("period_start")

            if pe is not None:
                cells.append(CellValue(row_index=i, col_name="期末余额", value=Decimal(str(pe)), source="wp_detail"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

            if ps is not None:
                cells.append(CellValue(row_index=i, col_name="期初余额", value=Decimal(str(ps)), source="wp_detail"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

        result.cells = cells
        return result

    # ------------------------------------------------------------------
    # 模式 3：分类取数
    # ------------------------------------------------------------------

    def fetch_category(
        self,
        section_code: str,
        category_data: list[dict[str, Any]] | None = None,
    ) -> SectionFillResult:
        """模式 3（分类取数）：从底稿按类别汇总（如按账龄/按性质）

        Args:
            section_code: 附注章节编码
            category_data: [{category, amount, percentage}]
        """
        result = SectionFillResult(section_code=section_code)
        cells: list[CellValue] = []
        categories = category_data or []

        result.stats.total_cells = len(categories) * 2  # 金额 + 比例

        for i, cat in enumerate(categories):
            amount = cat.get("amount")
            pct = cat.get("percentage")

            if amount is not None:
                cells.append(CellValue(row_index=i, col_name="金额", value=Decimal(str(amount)), source="wp_category"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

            if pct is not None:
                cells.append(CellValue(row_index=i, col_name="比例", value=Decimal(str(pct)), source="wp_category"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

        result.cells = cells
        return result

    # ------------------------------------------------------------------
    # 模式 4：变动取数
    # ------------------------------------------------------------------

    def fetch_change(
        self,
        section_code: str,
        change_data: list[dict[str, Any]] | None = None,
    ) -> SectionFillResult:
        """模式 4（变动取数）：从底稿本期增加/减少列取数

        Args:
            section_code: 附注章节编码
            change_data: [{name, opening, increase, decrease, closing}]
        """
        result = SectionFillResult(section_code=section_code)
        cells: list[CellValue] = []
        rows = change_data or []

        result.stats.total_cells = len(rows) * 4  # 期初/增加/减少/期末

        for i, row in enumerate(rows):
            for col_name, key in [
                ("期初余额", "opening"),
                ("本期增加", "increase"),
                ("本期减少", "decrease"),
                ("期末余额", "closing"),
            ]:
                val = row.get(key)
                if val is not None:
                    cells.append(CellValue(row_index=i, col_name=col_name, value=Decimal(str(val)), source="wp_change"))
                    result.stats.filled_cells += 1
                else:
                    result.stats.unfillable_cells += 1

        result.cells = cells
        return result

    # ------------------------------------------------------------------
    # 统一入口：按 fetch_mode 分发
    # ------------------------------------------------------------------

    def fill_section(
        self,
        section_code: str,
        fetch_mode: str,
        wp_data: dict[str, Any] | None = None,
        report_row_data: dict[str, Any] | None = None,
        detail_rows: list[dict[str, Any]] | None = None,
        category_data: list[dict[str, Any]] | None = None,
        change_data: list[dict[str, Any]] | None = None,
    ) -> SectionFillResult:
        """按 fetch_mode 分发到对应取数模式"""
        mode = FetchMode(fetch_mode) if fetch_mode else FetchMode.TOTAL

        if mode == FetchMode.TOTAL:
            return self.fetch_total(section_code, wp_data=wp_data, report_row_data=report_row_data)
        elif mode == FetchMode.DETAIL:
            return self.fetch_detail(section_code, detail_rows=detail_rows)
        elif mode == FetchMode.CATEGORY:
            return self.fetch_category(section_code, category_data=category_data)
        elif mode == FetchMode.CHANGE:
            return self.fetch_change(section_code, change_data=change_data)
        else:
            return SectionFillResult(section_code=section_code, errors=[f"Unknown fetch_mode: {fetch_mode}"])

    # ------------------------------------------------------------------
    # 从试算表自动填充
    # ------------------------------------------------------------------

    def fill_from_trial_balance(
        self,
        section_code: str,
        tb_current: dict[str, Decimal] | None = None,
        tb_prior: dict[str, Decimal] | None = None,
        adjustments: dict[str, Decimal] | None = None,
    ) -> SectionFillResult:
        """从试算表自动填充期末/期初/变动列

        Args:
            section_code: 附注章节编码
            tb_current: {account_code: closing_balance}
            tb_prior: {account_code: opening_balance}
            adjustments: {account_code: adjustment_amount}
        """
        result = SectionFillResult(section_code=section_code)
        cells: list[CellValue] = []

        current = tb_current or {}
        prior = tb_prior or {}
        adj = adjustments or {}

        all_codes = set(current.keys()) | set(prior.keys()) | set(adj.keys())
        result.stats.total_cells = len(all_codes) * 3  # 期末+期初+变动

        for i, code in enumerate(sorted(all_codes)):
            if code in current:
                cells.append(CellValue(row_index=i, col_name="期末余额", value=current[code], source="tb"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

            if code in prior:
                cells.append(CellValue(row_index=i, col_name="期初余额", value=prior[code], source="tb_prior"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

            if code in adj:
                cells.append(CellValue(row_index=i, col_name="本期变动", value=adj[code], source="adjustment"))
                result.stats.filled_cells += 1
            else:
                result.stats.unfillable_cells += 1

        result.cells = cells
        return result

    # ------------------------------------------------------------------
    # 汇总填充率统计
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_stats(results: list[SectionFillResult]) -> FillStats:
        """汇总多个章节的填充率统计"""
        total = FillStats()
        for r in results:
            total.total_cells += r.stats.total_cells
            total.filled_cells += r.stats.filled_cells
            total.unfillable_cells += r.stats.unfillable_cells
        return total
