"""Read-only projection of standard-account parent balances for trial-balance responses."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.services.account_chart_service import standard_chart_entries

_AMOUNT_FIELDS = (
    "unadjusted_amount", "opening_balance", "rje_adjustment",
    "aje_adjustment", "wp_adjustment", "audited_amount",
)


def project_parent_balances(rows: list[dict]) -> list[dict]:
    """Show parent totals while preserving each row's independent contribution."""
    if not rows:
        return rows
    by_code = {str(row["standard_account_code"]): row for row in rows}
    chart_parents = {
        str(entry["code"]): str(entry["parent_code"])
        for entry in standard_chart_entries()
        if entry.get("code") and entry.get("parent_code")
    }
    children: dict[str, list[str]] = defaultdict(list)
    for code in by_code:
        parent = chart_parents.get(code)
        if parent in by_code and parent != code:
            children[parent].append(code)

    totals: dict[str, dict[str, Decimal | None]] = {}
    visiting: set[str] = set()

    def total_for(code: str) -> dict[str, Decimal | None]:
        if code in totals:
            return totals[code]
        if code in visiting:
            raise ValueError(f"Cycle in standard account hierarchy: {code}")
        visiting.add(code)
        result = {
            field: Decimal(str(by_code[code][field])) if by_code[code].get(field) is not None else None
            for field in _AMOUNT_FIELDS
        }
        for child in children[code]:
            for field, amount in total_for(child).items():
                if amount is not None:
                    result[field] = (result[field] or Decimal(0)) + amount
        visiting.remove(code)
        totals[code] = result
        return result

    projected = []
    for row in rows:
        code = str(row["standard_account_code"])
        copy = dict(row)
        copy["rollup_base"] = {field: row.get(field) for field in _AMOUNT_FIELDS} if children[code] else None
        if children[code]:
            for field, amount in total_for(code).items():
                copy[field] = str(amount) if amount is not None else None
        projected.append(copy)
    return projected
