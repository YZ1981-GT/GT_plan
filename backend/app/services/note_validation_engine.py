"""附注校验引擎 — 8种校验规则 + 汇总结果

核心功能：
- validate_all: 执行全部校验规则
- BalanceValidator: 报表余额 vs 附注合计行
- SubItemValidator: 明细行求和 = 合计行
- WideTableValidator / VerticalValidator / CrossTableValidator / etc: 存根实现

Validates: Requirements 5.1, 5.2, 5.3, 5.5
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteValidationResult,
)

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"


def _load_seed_data() -> dict:
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Validator functions
# ------------------------------------------------------------------


async def validate_balance(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """余额核对：附注合计行 = 报表对应行金额。

    Validates: Requirements 5.1 (balance check)
    """
    findings = []
    table_data = note.table_data
    if not table_data or "rows" not in table_data:
        return findings

    # Find the template for this note to get report_row_code
    tmpl = _find_template(note.note_section, seed_templates)
    if not tmpl:
        return findings

    report_row_code = tmpl.get("report_row_code")
    if not report_row_code:
        return findings

    # Determine report_type from row_code prefix
    report_type = _row_code_to_report_type(report_row_code)
    if not report_type:
        return findings

    # Get report amount
    result = await db.execute(
        sa.select(FinancialReport.current_period_amount).where(
            FinancialReport.project_id == note.project_id,
            FinancialReport.year == note.year,
            FinancialReport.report_type == report_type,
            FinancialReport.row_code == report_row_code,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    report_amount = result.scalar_one_or_none()
    if report_amount is None:
        return findings

    # Find total row in note table_data
    total_amount = _get_total_row_amount(table_data)
    if total_amount is None:
        return findings

    diff = Decimal(str(report_amount)) - Decimal(str(total_amount))
    if diff != Decimal("0"):
        findings.append({
            "note_section": note.note_section,
            "table_name": note.section_title,
            "check_type": "balance",
            "severity": "error",
            "message": f"附注合计行({total_amount})与报表行({report_amount})不一致，差异{diff}",
            "expected_value": float(report_amount),
            "actual_value": float(total_amount),
        })

    return findings


async def validate_sub_item(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """其中项校验：明细行求和 = 合计行。

    Validates: Requirements 5.1 (sub_item check)
    """
    findings = []
    table_data = note.table_data
    if not table_data or "rows" not in table_data:
        return findings

    rows = table_data["rows"]
    # Find total row and sum detail rows
    detail_sum_current = Decimal("0")
    detail_sum_prior = Decimal("0")
    total_current = None
    total_prior = None

    for row in rows:
        values = row.get("values", [])
        is_total = row.get("is_total", False)
        if is_total:
            total_current = Decimal(str(values[0])) if len(values) > 0 else None
            total_prior = Decimal(str(values[1])) if len(values) > 1 else None
        else:
            if len(values) > 0:
                detail_sum_current += Decimal(str(values[0]))
            if len(values) > 1:
                detail_sum_prior += Decimal(str(values[1]))

    if total_current is not None:
        diff = detail_sum_current - total_current
        if diff != Decimal("0"):
            findings.append({
                "note_section": note.note_section,
                "table_name": note.section_title,
                "check_type": "sub_item",
                "severity": "error",
                "message": f"期末明细行合计({detail_sum_current})与合计行({total_current})不一致，差异{diff}",
                "expected_value": float(total_current),
                "actual_value": float(detail_sum_current),
            })

    if total_prior is not None:
        diff = detail_sum_prior - total_prior
        if diff != Decimal("0"):
            findings.append({
                "note_section": note.note_section,
                "table_name": note.section_title,
                "check_type": "sub_item",
                "severity": "error",
                "message": f"期初明细行合计({detail_sum_prior})与合计行({total_prior})不一致，差异{diff}",
                "expected_value": float(total_prior),
                "actual_value": float(detail_sum_prior),
            })

    return findings


async def validate_wide_table(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """宽表公式校验（存根）。"""
    return []


async def validate_vertical(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """纵向勾稽校验（存根）。"""
    return []


async def validate_cross_table(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """交叉校验（存根）。"""
    return []


async def validate_aging_transition(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """账龄衔接校验（存根）。"""
    return []


async def validate_completeness(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """完整性校验（存根）。"""
    return []


async def validate_llm_review(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """LLM审核（存根）。"""
    return []


# Validator registry
VALIDATORS = {
    "balance": validate_balance,
    "sub_item": validate_sub_item,
    "wide_table": validate_wide_table,
    "vertical": validate_vertical,
    "cross_table": validate_cross_table,
    "aging": validate_aging_transition,
    "completeness": validate_completeness,
    "llm_review": validate_llm_review,
}


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _find_template(note_section: str, templates: list[dict]) -> dict | None:
    for t in templates:
        if t.get("note_section") == note_section:
            return t
    return None


def _row_code_to_report_type(row_code: str) -> FinancialReportType | None:
    if row_code.startswith("BS-"):
        return FinancialReportType.balance_sheet
    elif row_code.startswith("IS-"):
        return FinancialReportType.income_statement
    elif row_code.startswith("CF-"):
        return FinancialReportType.cash_flow_statement
    elif row_code.startswith("EQ-"):
        return FinancialReportType.equity_statement
    return None


def _get_total_row_amount(table_data: dict) -> Decimal | None:
    """从 table_data 中获取合计行的期末余额（第一个 values 值）"""
    rows = table_data.get("rows", [])
    for row in rows:
        if row.get("is_total", False):
            values = row.get("values", [])
            if values:
                return Decimal(str(values[0]))
    return None


# ------------------------------------------------------------------
# NoteValidationEngine
# ------------------------------------------------------------------


class NoteValidationEngine:
    """附注校验引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_all(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """执行全部校验规则，返回校验结果。

        Validates: Requirements 5.2, 5.3
        """
        seed = _load_seed_data()
        templates = seed.get("account_mapping_template", [])
        check_presets = seed.get("check_presets", {})

        # Load all notes
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        notes = result.scalars().all()

        all_findings: list[dict] = []

        for note in notes:
            account_name = note.account_name or ""
            applicable_checks = check_presets.get(account_name, [])

            for check_type in applicable_checks:
                validator_fn = VALIDATORS.get(check_type)
                if validator_fn is None:
                    continue
                try:
                    findings = await validator_fn(self.db, note, templates)
                    all_findings.extend(findings)
                except Exception as e:
                    logger.warning(
                        "Validator %s failed for note %s: %s",
                        check_type, note.note_section, e,
                    )

        # Count by severity
        error_count = sum(1 for f in all_findings if f.get("severity") == "error")
        warning_count = sum(1 for f in all_findings if f.get("severity") == "warning")
        info_count = sum(1 for f in all_findings if f.get("severity") == "info")

        # Save to note_validation_results
        now = datetime.now(timezone.utc)
        validation_result = NoteValidationResult(
            project_id=project_id,
            year=year,
            validation_timestamp=now,
            findings=all_findings,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        )
        self.db.add(validation_result)
        await self.db.flush()

        return {
            "id": str(validation_result.id),
            "project_id": str(project_id),
            "year": year,
            "validation_timestamp": now.isoformat(),
            "findings": all_findings,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
        }

    async def get_latest_results(
        self,
        project_id: UUID,
        year: int,
    ) -> NoteValidationResult | None:
        """获取最新校验结果"""
        result = await self.db.execute(
            sa.select(NoteValidationResult)
            .where(
                NoteValidationResult.project_id == project_id,
                NoteValidationResult.year == year,
            )
            .order_by(NoteValidationResult.validation_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def confirm_finding(
        self,
        validation_id: UUID,
        finding_index: int,
        reason: str,
    ) -> bool:
        """确认校验发现为"已确认-无需修改"。

        Validates: Requirements 5.5
        """
        result = await self.db.execute(
            sa.select(NoteValidationResult).where(
                NoteValidationResult.id == validation_id,
            )
        )
        validation = result.scalar_one_or_none()
        if validation is None:
            return False

        findings = validation.findings
        if not isinstance(findings, list) or finding_index >= len(findings):
            return False

        # Deep copy to force SQLAlchemy to detect the change
        import copy
        new_findings = copy.deepcopy(findings)
        new_findings[finding_index]["confirmed"] = True
        new_findings[finding_index]["confirm_reason"] = reason
        validation.findings = new_findings

        # Explicit UPDATE for SQLite compatibility
        await self.db.execute(
            sa.update(NoteValidationResult)
            .where(NoteValidationResult.id == validation_id)
            .values(findings=new_findings)
        )
        await self.db.flush()
        return True
