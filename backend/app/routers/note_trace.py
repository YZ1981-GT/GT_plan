"""附注来源追溯 API

Phase 3 F1 双向穿透：附注 cell → 报表行 → TB 科目

- GET /api/projects/{pid}/notes/trace-source?cell_id={cell_id}

cell_id 格式: "{note_section}:{row_index}:{col_index}"
  例: "五、1:0:0" 表示附注章节"五、1"第 0 行第 0 列

Requirements: F1.1
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.audit_platform_models import ReportLineMapping, TbBalance
from app.models.core import User
from app.models.report_models import DisclosureNote, FinancialReport

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/notes",
    tags=["note-trace"],
)


# ── Response schemas ──


class ReportLineInfo(BaseModel):
    line_code: str
    item_name: str
    amount: float | None = None


class TbAccountInfo(BaseModel):
    code: str
    name: str
    closing_balance: float | None = None


class TraceSourceResponse(BaseModel):
    source_type: str  # "report_line" | "tb_account" | "formula" | "none"
    report_line: ReportLineInfo | None = None
    tb_accounts: list[TbAccountInfo] = []


# ── Helpers ──


def _parse_cell_id(cell_id: str) -> tuple[str, int, int]:
    """Parse cell_id format: 'note_section:row_index:col_index'

    Returns (note_section, row_index, col_index).
    Raises ValueError on invalid format.
    """
    parts = cell_id.rsplit(":", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid cell_id format: {cell_id}")
    note_section = parts[0]
    try:
        row_index = int(parts[1])
        col_index = int(parts[2])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid cell_id format: {cell_id}")
    return note_section, row_index, col_index


def _extract_cell_formula(table_data: dict, row_index: int, col_index: int) -> str | None:
    """Extract formula or account reference from a cell in table_data.

    Cells may store formulas in different formats:
    - row["_cell_formulas"][str(col_index)] = "=REPORT('BS-001', 'current')"
    - row["account_codes"] = ["1001", "1002"]
    - row["label"] matches a known account name
    """
    rows = table_data.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return None

    row = rows[row_index]

    # Check for explicit cell formulas
    cell_formulas = row.get("_cell_formulas", {})
    formula = cell_formulas.get(str(col_index))
    if formula:
        return formula

    # Check for account_codes on the row (direct TB reference)
    account_codes = row.get("account_codes", [])
    if account_codes:
        return f"=TB({','.join(account_codes)})"

    return None


def _extract_account_codes_from_row(table_data: dict, row_index: int) -> list[str]:
    """Extract account codes directly from a row's metadata."""
    rows = table_data.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return []
    row = rows[row_index]
    return row.get("account_codes", [])


def _extract_row_label(table_data: dict, row_index: int) -> str:
    """Extract the label of a row."""
    rows = table_data.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return ""
    return rows[row_index].get("label", "")


def _extract_cell_value(table_data: dict, row_index: int, col_index: int) -> float | None:
    """Extract the numeric value of a cell."""
    rows = table_data.get("rows", [])
    if row_index < 0 or row_index >= len(rows):
        return None
    row = rows[row_index]
    values = row.get("values", row.get("cells", []))
    if col_index < 0 or col_index >= len(values):
        return None
    val = values[col_index]
    if isinstance(val, dict):
        val = val.get("value") or val.get("manual_value")
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── Endpoint ──


@router.get("/trace-source", response_model=TraceSourceResponse)
async def trace_note_source(
    project_id: UUID,
    cell_id: str = Query(..., description="Cell identifier: note_section:row_index:col_index"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """追溯附注 cell 的数据来源。

    查询附注 cell 的公式定义 → 解析来源报表行 → 查询报表行对应的 TB 科目。

    Returns:
        source_type: "report_line" | "tb_account" | "formula" | "none"
        report_line: 来源报表行信息（如有）
        tb_accounts: 构成 TB 科目列表
    """
    # 1. Parse cell_id
    try:
        note_section, row_index, col_index = _parse_cell_id(cell_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Load the disclosure note
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail=f"附注章节 '{note_section}' 不存在")

    if not note.table_data:
        return TraceSourceResponse(source_type="none")

    # 3. Extract cell info
    account_codes = _extract_account_codes_from_row(note.table_data, row_index)
    row_label = _extract_row_label(note.table_data, row_index)
    cell_value = _extract_cell_value(note.table_data, row_index, col_index)

    # 4. Determine the year from the note
    year = note.year

    # 5. Try to find the report line that maps to this cell's accounts
    # Strategy: use ReportLineMapping to find which report line these accounts belong to
    if account_codes:
        # Direct TB account reference — find the report line via mapping
        mapping_result = await db.execute(
            sa.select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code.in_(account_codes),
                ReportLineMapping.is_deleted == sa.false(),
                ReportLineMapping.is_confirmed == sa.true(),
            )
        )
        mappings = mapping_result.scalars().all()

        if mappings:
            # Use the first mapping's report line (they should all map to the same line)
            first_mapping = mappings[0]
            line_code = first_mapping.report_line_code
            line_name = first_mapping.report_line_name

            # Get the report line amount from FinancialReport
            report_row = await db.execute(
                sa.select(FinancialReport).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.row_code == line_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            fr = report_row.scalar_one_or_none()
            amount = float(fr.current_period_amount) if fr and fr.current_period_amount else cell_value

            report_line = ReportLineInfo(
                line_code=line_code,
                item_name=line_name,
                amount=amount,
            )
        else:
            # No mapping found — use row label as item name
            report_line = ReportLineInfo(
                line_code="",
                item_name=row_label or "未知",
                amount=cell_value,
            )

        # Query TB balances for these accounts
        tb_result = await db.execute(
            sa.select(TbBalance).where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
                TbBalance.account_code.in_(account_codes),
                TbBalance.is_deleted == sa.false(),
            ).order_by(sa.desc(sa.func.abs(TbBalance.closing_balance)))
        )
        tb_rows = tb_result.scalars().all()

        tb_accounts = [
            TbAccountInfo(
                code=tb.account_code,
                name=tb.account_name or "",
                closing_balance=float(tb.closing_balance) if tb.closing_balance else 0.0,
            )
            for tb in tb_rows
        ]

        return TraceSourceResponse(
            source_type="report_line" if mappings else "tb_account",
            report_line=report_line,
            tb_accounts=tb_accounts,
        )

    # 6. No direct account_codes — try to find via row_label matching in ReportLineMapping
    if row_label:
        # Try matching by report_line_name
        mapping_result = await db.execute(
            sa.select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.report_line_name == row_label,
                ReportLineMapping.is_deleted == sa.false(),
                ReportLineMapping.is_confirmed == sa.true(),
            )
        )
        mappings = mapping_result.scalars().all()

        if mappings:
            line_code = mappings[0].report_line_code
            line_name = mappings[0].report_line_name

            # Get report line amount
            report_row = await db.execute(
                sa.select(FinancialReport).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.row_code == line_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            fr = report_row.scalar_one_or_none()
            amount = float(fr.current_period_amount) if fr and fr.current_period_amount else cell_value

            # Get all account codes that map to this report line
            all_codes_result = await db.execute(
                sa.select(ReportLineMapping.standard_account_code).where(
                    ReportLineMapping.project_id == project_id,
                    ReportLineMapping.report_line_code == line_code,
                    ReportLineMapping.is_deleted == sa.false(),
                    ReportLineMapping.is_confirmed == sa.true(),
                )
            )
            all_account_codes = [r[0] for r in all_codes_result.all()]

            # Query TB balances
            tb_accounts: list[TbAccountInfo] = []
            if all_account_codes:
                tb_result = await db.execute(
                    sa.select(TbBalance).where(
                        TbBalance.project_id == project_id,
                        TbBalance.year == year,
                        TbBalance.account_code.in_(all_account_codes),
                        TbBalance.is_deleted == sa.false(),
                    ).order_by(sa.desc(sa.func.abs(TbBalance.closing_balance)))
                )
                tb_rows = tb_result.scalars().all()
                tb_accounts = [
                    TbAccountInfo(
                        code=tb.account_code,
                        name=tb.account_name or "",
                        closing_balance=float(tb.closing_balance) if tb.closing_balance else 0.0,
                    )
                    for tb in tb_rows
                ]

            return TraceSourceResponse(
                source_type="report_line",
                report_line=ReportLineInfo(
                    line_code=line_code,
                    item_name=line_name,
                    amount=amount,
                ),
                tb_accounts=tb_accounts,
            )

    # 7. No source found
    return TraceSourceResponse(source_type="none")
