"""附注宽表公式预设加载与执行

加载 `国企版宽表公式预设.md` / `上市版宽表公式预设.md`
横向公式：期初余额 + 本期增加 - 本期减少 = 期末余额
纵向汇总：各明细行之和 = 合计行
不平衡时标记 warning 并显示差异金额

Requirements: 24.1, 24.2, 24.3, 24.4
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WideTableFormula:
    """A wide table formula definition."""
    section_code: str
    table_name: str = ""
    formula_type: str = "horizontal"  # horizontal / vertical
    expression: str = ""
    description: str = ""
    columns: list[str] = field(default_factory=list)  # Column names involved


@dataclass
class WideTableCheckResult:
    """Result of a wide table formula check."""
    section_code: str
    table_name: str = ""
    formula_type: str = "horizontal"
    passed: bool = True
    row_index: int = -1
    expected: Decimal = Decimal("0")
    actual: Decimal = Decimal("0")
    diff: Decimal = Decimal("0")
    warning_message: str = ""


# ---------------------------------------------------------------------------
# Preset files
# ---------------------------------------------------------------------------

_WIDE_TABLE_PRESET_FILES = {
    "soe": "附注模版/国企版宽表公式预设.md",
    "listed": "附注模版/上市版宽表公式预设.md",
}

# Default tolerance for balance checks
_DEFAULT_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# Preset Loader
# ---------------------------------------------------------------------------

def _parse_wide_table_preset(content: str) -> list[WideTableFormula]:
    """Parse a wide table preset MD file into formula definitions.

    Expected format:
    ## section_code: 章节名称
    - 横向: 期初余额 + 本期增加 - 本期减少 = 期末余额
    - 纵向: sum(明细行) = 合计行
    """
    formulas: list[WideTableFormula] = []
    current_section = ""
    current_table = ""

    section_pattern = re.compile(r"^#{1,4}\s+(\S+?)[:：\s](.+)?$")
    formula_pattern = re.compile(r"^[-*]\s*(横向|纵向|horizontal|vertical)[:：]\s*(.+)$")
    table_pattern = re.compile(r"^#{1,4}\s*表[：:]?\s*(.+)$")

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Section header
        sec_match = section_pattern.match(line)
        if sec_match:
            current_section = sec_match.group(1)
            continue

        # Table name
        tbl_match = table_pattern.match(line)
        if tbl_match:
            current_table = tbl_match.group(1).strip()
            continue

        # Formula line
        formula_match = formula_pattern.match(line)
        if formula_match:
            ftype_str = formula_match.group(1)
            expression = formula_match.group(2).strip()

            formula_type = "horizontal" if ftype_str in ("横向", "horizontal") else "vertical"

            formulas.append(WideTableFormula(
                section_code=current_section,
                table_name=current_table,
                formula_type=formula_type,
                expression=expression,
            ))

    return formulas


def load_wide_table_presets(template_type: str, base_dir: Path | None = None) -> list[WideTableFormula]:
    """Load wide table formula presets from MD file."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    rel_path = _WIDE_TABLE_PRESET_FILES.get(template_type, _WIDE_TABLE_PRESET_FILES["soe"])
    full_path = base_dir / rel_path

    if not full_path.exists():
        logger.warning("Wide table preset file not found: %s", full_path)
        return []

    try:
        content = full_path.read_text(encoding="utf-8-sig")
        return _parse_wide_table_preset(content)
    except Exception as e:
        logger.error("Failed to load wide table preset: %s", e)
        return []


# ---------------------------------------------------------------------------
# Execution Engine
# ---------------------------------------------------------------------------

def check_horizontal_balance(
    row: dict[str, Any],
    opening_col: str = "opening",
    increase_col: str = "increase",
    decrease_col: str = "decrease",
    closing_col: str = "closing",
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> WideTableCheckResult:
    """Check horizontal formula: 期初余额 + 本期增加 - 本期减少 = 期末余额

    Requirements: 24.2
    """
    result = WideTableCheckResult(
        section_code="",
        formula_type="horizontal",
    )

    opening = Decimal(str(row.get(opening_col, 0) or 0))
    increase = Decimal(str(row.get(increase_col, 0) or 0))
    decrease = Decimal(str(row.get(decrease_col, 0) or 0))
    closing = Decimal(str(row.get(closing_col, 0) or 0))

    expected_closing = opening + increase - decrease
    diff = abs(expected_closing - closing)

    result.expected = expected_closing
    result.actual = closing
    result.diff = diff
    result.passed = diff <= tolerance

    if not result.passed:
        result.warning_message = (
            f"横向公式不平衡: 期初({opening}) + 增加({increase}) - 减少({decrease}) "
            f"= {expected_closing}, 实际期末 = {closing}, 差异 = {diff}"
        )

    return result


def check_vertical_summary(
    rows: list[dict[str, Any]],
    amount_col: str = "amount",
    tolerance: Decimal = _DEFAULT_TOLERANCE,
) -> WideTableCheckResult:
    """Check vertical formula: sum(明细行) = 合计行

    Requirements: 24.3
    """
    result = WideTableCheckResult(
        section_code="",
        formula_type="vertical",
    )

    total_value = Decimal("0")
    detail_sum = Decimal("0")
    found_total = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_total"):
            total_value = Decimal(str(row.get(amount_col, 0) or 0))
            found_total = True
        else:
            detail_sum += Decimal(str(row.get(amount_col, 0) or 0))

    if not found_total:
        result.passed = True
        result.warning_message = "未找到合计行，跳过纵向校验"
        return result

    diff = abs(detail_sum - total_value)
    result.expected = total_value
    result.actual = detail_sum
    result.diff = diff
    result.passed = diff <= tolerance

    if not result.passed:
        result.warning_message = (
            f"纵向汇总不平衡: 明细行合计 = {detail_sum}, "
            f"合计行 = {total_value}, 差异 = {diff}"
        )

    return result


class NoteWideTableEngine:
    """附注宽表公式引擎

    加载预设公式并对附注宽表数据执行横向/纵向校验。
    """

    def __init__(self, template_type: str = "soe"):
        self.template_type = template_type
        self._presets: list[WideTableFormula] | None = None

    def load_presets(self) -> list[WideTableFormula]:
        """Load presets (cached)."""
        if self._presets is None:
            self._presets = load_wide_table_presets(self.template_type)
        return self._presets

    def execute_checks(
        self,
        section_code: str,
        table_data: dict[str, Any],
        tolerance: Decimal = _DEFAULT_TOLERANCE,
    ) -> list[WideTableCheckResult]:
        """Execute all applicable wide table checks for a section.

        Args:
            section_code: The note section code
            table_data: Table data dict with 'rows' key
            tolerance: Balance tolerance (default 0.01)

        Returns:
            List of check results (both passed and failed)
        """
        results: list[WideTableCheckResult] = []
        rows = table_data.get("rows", [])
        if not rows:
            return results

        # Horizontal checks: check each row
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            # Skip total rows for horizontal check
            if row.get("is_total"):
                continue

            # Check if row has the required columns for horizontal formula
            has_horizontal_cols = any(
                k in row for k in ("opening", "increase", "decrease", "closing")
            )
            if has_horizontal_cols:
                check = check_horizontal_balance(row, tolerance=tolerance)
                check.section_code = section_code
                check.row_index = i
                results.append(check)

        # Vertical check: sum of detail rows = total row
        # Check for each amount column
        for col in ("closing", "opening", "amount"):
            col_rows = [r for r in rows if isinstance(r, dict) and col in r]
            if col_rows:
                check = check_vertical_summary(col_rows, amount_col=col, tolerance=tolerance)
                check.section_code = section_code
                results.append(check)
                break  # Only check one column

        return results

    def get_warnings(self, results: list[WideTableCheckResult]) -> list[dict[str, Any]]:
        """Extract warning messages from check results."""
        warnings = []
        for r in results:
            if not r.passed:
                warnings.append({
                    "section_code": r.section_code,
                    "table_name": r.table_name,
                    "formula_type": r.formula_type,
                    "row_index": r.row_index,
                    "diff_amount": float(r.diff),
                    "message": r.warning_message,
                })
        return warnings
