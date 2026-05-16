"""NoteVariationAnalysisService — 变动分析自动生成

Requirements: 43.1, 43.2, 43.3, 43.5

功能：
- 变动率 > 20% 的科目自动生成变动分析段落模板
- 增加模板/减少模板（含金额/百分比/原因占位）
- {原因占位} 标记为待填写（黄色高亮）
- 变动率 ≤ 20% 不生成（除非手动要求）
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Variation analysis threshold (20%)
VARIATION_THRESHOLD = Decimal("0.20")

# Templates for variation analysis paragraphs
INCREASE_TEMPLATE = (
    "{科目名称}本期末较上期末增加{金额}元（增幅{百分比}%），"
    "主要系{原因占位}所致。"
)

DECREASE_TEMPLATE = (
    "{科目名称}本期末较上期末减少{金额}元（降幅{百分比}%），"
    "主要系{原因占位}所致。"
)


def _format_amount(amount: Decimal) -> str:
    """Format amount with thousand separators."""
    abs_amount = abs(amount)
    if abs_amount == 0:
        return "0.00"
    return f"{abs_amount:,.2f}"


def _format_percentage(rate: Decimal) -> str:
    """Format percentage with 2 decimal places."""
    return f"{abs(rate) * 100:.2f}"


class VariationAnalysisResult:
    """Result of variation analysis for a single account."""

    def __init__(
        self,
        row_code: str,
        row_name: str,
        current_amount: Decimal,
        prior_amount: Decimal,
        change_amount: Decimal,
        change_rate: Decimal,
        paragraph: str,
        needs_reason: bool = True,
    ):
        self.row_code = row_code
        self.row_name = row_name
        self.current_amount = current_amount
        self.prior_amount = prior_amount
        self.change_amount = change_amount
        self.change_rate = change_rate
        self.paragraph = paragraph
        self.needs_reason = needs_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_code": self.row_code,
            "row_name": self.row_name,
            "current_amount": float(self.current_amount),
            "prior_amount": float(self.prior_amount),
            "change_amount": float(self.change_amount),
            "change_rate": float(self.change_rate),
            "change_rate_percent": f"{abs(self.change_rate) * 100:.2f}%",
            "paragraph": self.paragraph,
            "needs_reason": self.needs_reason,
            "direction": "increase" if self.change_amount > 0 else "decrease",
        }


class NoteVariationAnalysisService:
    """Service for generating variation analysis paragraphs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_variation_analysis(
        self,
        project_id: UUID,
        year: int,
        threshold: Decimal | None = None,
        force_row_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate variation analysis for accounts exceeding threshold.

        Args:
            project_id: Project UUID
            year: Current year
            threshold: Override default 20% threshold
            force_row_codes: Generate for these row_codes regardless of threshold

        Returns:
            Dict with generated analyses and summary.

        Requirements: 43.1, 43.2, 43.3, 43.5
        """
        effective_threshold = threshold or VARIATION_THRESHOLD
        force_codes = set(force_row_codes or [])

        # Load current and prior year report data
        current_data = await self._load_report_data(project_id, year)
        prior_data = await self._load_report_data(project_id, year - 1)

        if not current_data:
            return {
                "status": "no_data",
                "message": "本年报表数据不存在，请先生成报表",
                "analyses": [],
                "generated_count": 0,
                "skipped_count": 0,
            }

        analyses: list[VariationAnalysisResult] = []
        skipped = 0

        for row_code, current_row in current_data.items():
            current_amount = Decimal(str(current_row.get("amount", 0) or 0))
            prior_row = prior_data.get(row_code, {})
            prior_amount = Decimal(str(prior_row.get("amount", 0) or 0))

            # Calculate change
            change_amount = current_amount - prior_amount

            # Calculate change rate
            if prior_amount == 0:
                if current_amount == 0:
                    change_rate = Decimal("0")
                else:
                    change_rate = Decimal("1")  # 100% increase from zero
            else:
                change_rate = change_amount / abs(prior_amount)

            # Check threshold
            exceeds_threshold = abs(change_rate) > effective_threshold
            is_forced = row_code in force_codes

            if not exceeds_threshold and not is_forced:
                skipped += 1
                continue

            # Skip zero changes
            if change_amount == 0:
                skipped += 1
                continue

            # Generate paragraph
            row_name = current_row.get("row_name", row_code)
            paragraph = self._generate_paragraph(
                row_name=row_name,
                change_amount=change_amount,
                change_rate=change_rate,
            )

            analyses.append(VariationAnalysisResult(
                row_code=row_code,
                row_name=row_name,
                current_amount=current_amount,
                prior_amount=prior_amount,
                change_amount=change_amount,
                change_rate=change_rate,
                paragraph=paragraph,
                needs_reason=True,
            ))

        # Sort by absolute change amount (largest first)
        analyses.sort(key=lambda a: abs(a.change_amount), reverse=True)

        return {
            "status": "success",
            "analyses": [a.to_dict() for a in analyses],
            "generated_count": len(analyses),
            "skipped_count": skipped,
            "threshold_used": f"{effective_threshold * 100:.0f}%",
        }

    def _generate_paragraph(
        self,
        row_name: str,
        change_amount: Decimal,
        change_rate: Decimal,
    ) -> str:
        """Generate a variation analysis paragraph from template.

        Requirements: 43.2, 43.3
        """
        if change_amount > 0:
            template = INCREASE_TEMPLATE
        else:
            template = DECREASE_TEMPLATE

        paragraph = template.replace("{科目名称}", row_name)
        paragraph = paragraph.replace("{金额}", _format_amount(change_amount))
        paragraph = paragraph.replace("{百分比}", _format_percentage(change_rate))
        # {原因占位} is kept as-is — marked for user to fill (yellow highlight)

        return paragraph

    async def _load_report_data(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, dict[str, Any]]:
        """Load report data as {row_code: {amount, row_name}}."""
        try:
            result = await self.db.execute(
                sa.text("""
                    SELECT row_code, row_name, current_period_amount
                    FROM financial_report
                    WHERE project_id = :pid AND year = :yr
                """),
                {"pid": str(project_id), "yr": year},
            )
            rows = result.fetchall()
            return {
                row[0]: {"amount": row[2], "row_name": row[1]}
                for row in rows
                if row[0]
            }
        except Exception as e:
            logger.warning("Failed to load report data for %s/%d: %s", project_id, year, e)
            return {}
