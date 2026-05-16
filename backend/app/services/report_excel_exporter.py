"""报表 Excel 导出引擎 — 基于致同模板填充

基于 `审计报告模板/{版本}/{范围}/` 下的 xlsx 模板文件，
使用 openpyxl 复制模板后填入数据（保留原有格式/边框/字体/列宽）。

生成 4 个 Sheet：资产负债表、利润表、现金流量表、所有者权益变动表。

Requirements: 3.1-3.15
"""
from __future__ import annotations

import copy
import logging
import os
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side, numbers
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template map: (template_type, report_scope) → relative path from repo root
# ---------------------------------------------------------------------------

TEMPLATE_MAP: dict[str, str] = {
    "soe_consolidated": "审计报告模板/国企版/合并/1.1-2025国企财务报表.xlsx",
    "soe_standalone": "审计报告模板/国企版/单体/1.1-2025国企财务报表.xlsx",
    "listed_consolidated": "审计报告模板/上市版/合并_上市/2.股份年审－经审计的财务报表-202601.xlsx",
    "listed_standalone": "审计报告模板/上市版/单体_上市/2.股份年审－经审计的财务报表-202601.xlsx",
}

# Report type → Chinese sheet name
REPORT_TYPE_SHEET_NAMES: dict[str, str] = {
    "balance_sheet": "资产负债表",
    "income_statement": "利润表",
    "cash_flow_statement": "现金流量表",
    "equity_statement": "所有者权益变动表",
}

# Amount number format
AMOUNT_FORMAT = '#,##0.00'
NEGATIVE_FORMAT = '#,##0.00;[Red](#,##0.00)'

# Font for amounts
AMOUNT_FONT = Font(name="Arial Narrow", size=10)
BOLD_AMOUNT_FONT = Font(name="Arial Narrow", size=10, bold=True)

# Indentation: 2 Chinese character widths per level ≈ 4 regular chars
INDENT_CHARS_PER_LEVEL = 4


class ReportExcelExporter:
    """报表 Excel 导出引擎

    Design decision D2: 基于模板复制填充（非从零生成）。
    致同模板格式复杂（合并单元格/条件格式/打印设置），从零生成无法完美复现。
    如果模板文件不存在，则从零生成（fallback）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export(
        self,
        project_id: UUID,
        year: int,
        mode: str = "audited",
        report_types: list[str] | None = None,
        include_prior_year: bool = True,
    ) -> BytesIO:
        """导出报表 Excel

        Args:
            project_id: 项目 ID
            year: 年度
            mode: "audited" 或 "unadjusted"
            report_types: 指定导出哪些报表（默认全部 4 张）
            include_prior_year: 是否包含上年对比列

        Returns:
            BytesIO containing the xlsx file
        """
        # 1. Load project info
        project = await self._get_project(project_id)
        company_name = project.name if project else "未知公司"

        # 2. Determine template key
        template_type = getattr(project, "template_type", None) or "soe"
        report_scope = getattr(project, "report_scope", None) or "standalone"
        template_key = f"{template_type}_{report_scope}"

        # 3. Determine which report types to export
        if report_types:
            types_to_export = report_types
        else:
            types_to_export = list(REPORT_TYPE_SHEET_NAMES.keys())

        # 4. Load report data from DB
        report_data = await self._load_report_data(project_id, year, types_to_export)

        # 5. Try to load template, fallback to programmatic generation
        wb = self._load_template(template_key)
        if wb is None:
            # Fallback: generate from scratch
            wb = self._create_workbook_from_scratch(
                types_to_export, report_data, company_name, year,
                include_prior_year, mode,
            )
        else:
            # Fill template with data
            wb = self._fill_template(
                wb, types_to_export, report_data, company_name, year,
                include_prior_year, mode,
            )

        # 6. Write to BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _get_project(self, project_id: UUID) -> Any:
        """Load project from DB."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _load_report_data(
        self, project_id: UUID, year: int, report_types: list[str]
    ) -> dict[str, list[dict]]:
        """Load generated report rows from financial_report table."""
        data: dict[str, list[dict]] = {}
        for rt in report_types:
            try:
                report_type_enum = FinancialReportType(rt)
            except ValueError:
                continue

            result = await self.db.execute(
                select(FinancialReport)
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == report_type_enum,
                    FinancialReport.is_deleted == False,  # noqa: E712
                )
                .order_by(FinancialReport.row_code)
            )
            rows = result.scalars().all()
            data[rt] = [
                {
                    "row_code": r.row_code,
                    "row_name": r.row_name or "",
                    "current_period_amount": r.current_period_amount,
                    "prior_period_amount": r.prior_period_amount,
                    "indent_level": r.indent_level,
                    "is_total_row": r.is_total_row,
                    "formula_used": r.formula_used,
                }
                for r in rows
            ]
        return data

    def _load_template(self, template_key: str) -> Workbook | None:
        """Try to load xlsx template file. Returns None if not found."""
        rel_path = TEMPLATE_MAP.get(template_key)
        if not rel_path:
            return None

        # Try multiple base paths
        base_paths = [
            Path.cwd(),  # repo root
            Path.cwd().parent,  # if cwd is backend/
            Path(__file__).resolve().parent.parent.parent.parent,  # from service file
        ]

        for base in base_paths:
            full_path = base / rel_path
            if full_path.exists():
                try:
                    wb = load_workbook(str(full_path))
                    logger.info("Loaded template from %s", full_path)
                    return wb
                except Exception as e:
                    logger.warning("Failed to load template %s: %s", full_path, e)
                    return None

        logger.info("Template not found for key %s, will generate from scratch", template_key)
        return None

    def _fill_template(
        self,
        wb: Workbook,
        types_to_export: list[str],
        report_data: dict[str, list[dict]],
        company_name: str,
        year: int,
        include_prior_year: bool,
        mode: str,
    ) -> Workbook:
        """Fill template workbook with report data, preserving formatting."""
        for rt in types_to_export:
            sheet_name = REPORT_TYPE_SHEET_NAMES.get(rt)
            if not sheet_name:
                continue

            rows = report_data.get(rt, [])
            if not rows:
                continue

            # Find the sheet in template (try exact match, then partial)
            ws = None
            for name in wb.sheetnames:
                if sheet_name in name:
                    ws = wb[name]
                    break

            if ws is None:
                # Create new sheet if not in template
                ws = wb.create_sheet(title=sheet_name)
                self._write_sheet_from_scratch(
                    ws, rows, company_name, year, include_prior_year, mode, rt
                )
            else:
                # Fill existing template sheet
                self._fill_existing_sheet(
                    ws, rows, company_name, year, include_prior_year, mode
                )

        # Remove sheets not in export list
        sheets_to_keep = set()
        for rt in types_to_export:
            sn = REPORT_TYPE_SHEET_NAMES.get(rt, "")
            for name in wb.sheetnames:
                if sn and sn in name:
                    sheets_to_keep.add(name)

        # Don't remove sheets if we couldn't match any (safety)
        if sheets_to_keep:
            for name in list(wb.sheetnames):
                if name not in sheets_to_keep:
                    del wb[name]

        return wb

    def _fill_existing_sheet(
        self,
        ws,
        rows: list[dict],
        company_name: str,
        year: int,
        include_prior_year: bool,
        mode: str,
    ) -> None:
        """Fill data into an existing template sheet.

        Strategy: Find the data start row (after headers), then write row by row.
        Template typically has: Row 1=company name, Row 2=period, Row 3=unit,
        Row 4+=data rows with row_name in col A, amounts in col B/C.
        """
        # Find data start row by looking for first non-empty row after row 3
        data_start_row = 4  # Default assumption
        max_template_row = ws.max_row or 10

        # Write header info (preserve template formatting but update text)
        # Row 1: Company name
        self._safe_set_value(ws, 1, 1, company_name)
        # Row 2: Period
        period_text = f"{year}年12月31日" if "资产负债" in (ws.title or "") else f"{year}年度"
        self._safe_set_value(ws, 2, 1, period_text)

        # Write data rows starting from data_start_row
        for i, row in enumerate(rows):
            r = data_start_row + i
            # Column A: row name with indentation
            indent = "　" * row.get("indent_level", 0)  # Full-width space for indent
            cell_a = ws.cell(r, 1)
            if not isinstance(cell_a, MergedCell):
                cell_a.value = indent + row.get("row_name", "")
                if row.get("is_total_row"):
                    cell_a.font = Font(bold=True)

            # Column B: current period amount
            amount = row.get("current_period_amount")
            if amount is not None:
                cell_b = ws.cell(r, 2)
                if not isinstance(cell_b, MergedCell):
                    cell_b.value = float(amount)
                    self._apply_amount_format(cell_b, row.get("is_total_row", False))

            # Column C: prior period amount (if included)
            if include_prior_year:
                prior = row.get("prior_period_amount")
                if prior is not None:
                    cell_c = ws.cell(r, 3)
                    if not isinstance(cell_c, MergedCell):
                        cell_c.value = float(prior)
                        self._apply_amount_format(cell_c, row.get("is_total_row", False))

            # Apply total row formatting
            if row.get("is_total_row"):
                self._apply_total_row_style(ws, r, 3 if include_prior_year else 2)

    def _create_workbook_from_scratch(
        self,
        types_to_export: list[str],
        report_data: dict[str, list[dict]],
        company_name: str,
        year: int,
        include_prior_year: bool,
        mode: str,
    ) -> Workbook:
        """Generate workbook from scratch when template is not available."""
        wb = Workbook()
        # Remove default sheet
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

        for rt in types_to_export:
            sheet_name = REPORT_TYPE_SHEET_NAMES.get(rt)
            if not sheet_name:
                continue

            ws = wb.create_sheet(title=sheet_name)
            rows = report_data.get(rt, [])
            self._write_sheet_from_scratch(
                ws, rows, company_name, year, include_prior_year, mode, rt
            )

        return wb

    def _write_sheet_from_scratch(
        self,
        ws,
        rows: list[dict],
        company_name: str,
        year: int,
        include_prior_year: bool,
        mode: str,
        report_type: str,
    ) -> None:
        """Write a complete sheet from scratch with proper formatting."""
        # --- Header rows ---
        # Row 1: Company name (centered, bold)
        ws.cell(1, 1).value = company_name
        ws.cell(1, 1).font = Font(name="宋体", size=14, bold=True)
        ws.cell(1, 1).alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3 if include_prior_year else 2)

        # Row 2: Report period (centered)
        if report_type == "balance_sheet":
            period_text = f"{year}年12月31日"
        else:
            period_text = f"{year}年度"
        ws.cell(2, 1).value = period_text
        ws.cell(2, 1).font = Font(name="宋体", size=11)
        ws.cell(2, 1).alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=3 if include_prior_year else 2)

        # Row 3: Amount unit (right-aligned)
        mode_label = "未审数" if mode == "unadjusted" else "审定数"
        ws.cell(3, 1).value = f"单位：人民币元（{mode_label}）"
        ws.cell(3, 1).font = Font(name="宋体", size=9)
        ws.cell(3, 1).alignment = Alignment(horizontal="right")
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=3 if include_prior_year else 2)

        # Row 4: Column headers
        header_row = 4
        ws.cell(header_row, 1).value = "项　　目"
        ws.cell(header_row, 1).font = Font(bold=True)
        ws.cell(header_row, 1).alignment = Alignment(horizontal="center")

        ws.cell(header_row, 2).value = "期末余额" if report_type == "balance_sheet" else "本期金额"
        ws.cell(header_row, 2).font = Font(bold=True)
        ws.cell(header_row, 2).alignment = Alignment(horizontal="center")

        if include_prior_year:
            ws.cell(header_row, 3).value = "期初余额" if report_type == "balance_sheet" else "上期金额"
            ws.cell(header_row, 3).font = Font(bold=True)
            ws.cell(header_row, 3).alignment = Alignment(horizontal="center")

        # --- Data rows ---
        data_start = 5
        total_row_indices: list[int] = []  # Track total rows for SUM formulas
        child_start_map: dict[int, int] = {}  # total_row_excel_idx → first_child_excel_idx

        # Track children for SUM formula generation
        current_children_start = data_start

        for i, row in enumerate(rows):
            r = data_start + i

            # Column A: row name with indentation
            indent_level = row.get("indent_level", 0)
            indent_str = "　" * indent_level  # Full-width space
            ws.cell(r, 1).value = indent_str + row.get("row_name", "")

            # Apply indent via alignment
            ws.cell(r, 1).alignment = Alignment(
                indent=indent_level * 2,  # 2 units per level
                vertical="center",
            )

            is_total = row.get("is_total_row", False)

            # Column B: current period amount
            amount = row.get("current_period_amount")
            if is_total and i > 0:
                # Use SUM formula for total rows
                child_start = current_children_start
                child_end = r - 1
                if child_end >= child_start:
                    col_letter = get_column_letter(2)
                    ws.cell(r, 2).value = f"=SUM({col_letter}{child_start}:{col_letter}{child_end})"
                elif amount is not None:
                    ws.cell(r, 2).value = float(amount)
                # Reset children start for next group
                current_children_start = r + 1
            elif amount is not None:
                ws.cell(r, 2).value = float(amount)

            self._apply_amount_format(ws.cell(r, 2), is_total)

            # Column C: prior period amount
            if include_prior_year:
                prior = row.get("prior_period_amount")
                if is_total and i > 0:
                    child_start = child_start_map.get(r, data_start)
                    child_end = r - 1
                    if child_end >= data_start:
                        col_letter = get_column_letter(3)
                        ws.cell(r, 3).value = f"=SUM({col_letter}{child_start}:{col_letter}{child_end})"
                    elif prior is not None:
                        ws.cell(r, 3).value = float(prior)
                elif prior is not None:
                    ws.cell(r, 3).value = float(prior)

                self._apply_amount_format(ws.cell(r, 3), is_total)

            # Total row styling
            if is_total:
                self._apply_total_row_style(ws, r, 3 if include_prior_year else 2)
                total_row_indices.append(r)

            # Row name font
            if is_total:
                ws.cell(r, 1).font = Font(bold=True)

        # --- Column widths ---
        ws.column_dimensions["A"].width = 40  # Project name column
        ws.column_dimensions["B"].width = 18  # Amount column
        if include_prior_year:
            ws.column_dimensions["C"].width = 18

        # --- Print settings ---
        ws.print_area = f"A1:{get_column_letter(3 if include_prior_year else 2)}{data_start + len(rows) - 1}"
        ws.page_setup.orientation = "portrait"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

    def _apply_amount_format(self, cell, is_total: bool = False) -> None:
        """Apply amount formatting to a cell."""
        cell.number_format = NEGATIVE_FORMAT
        cell.alignment = Alignment(horizontal="right", vertical="center")
        if is_total:
            cell.font = BOLD_AMOUNT_FONT
        else:
            cell.font = AMOUNT_FONT

    @staticmethod
    def _safe_set_value(ws, row: int, col: int, value) -> None:
        """Safely set cell value, skipping MergedCell objects."""
        cell = ws.cell(row, col)
        if isinstance(cell, MergedCell):
            return
        cell.value = value

    def _apply_total_row_style(self, ws, row_idx: int, max_col: int) -> None:
        """Apply total row styling: bold font + top border."""
        thin_border_top = Border(
            top=Side(style="thin"),
        )
        for col in range(1, max_col + 1):
            cell = ws.cell(row_idx, col)
            # Merge existing border with top border
            existing = cell.border
            cell.border = Border(
                top=Side(style="thin"),
                bottom=existing.bottom if existing else None,
                left=existing.left if existing else None,
                right=existing.right if existing else None,
            )
            if col == 1:
                cell.font = Font(bold=True)
