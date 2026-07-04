"""F2 存货 HTML 化 — wp_code → componentType 契约（替代旧 audit-sheet 断言）."""

from __future__ import annotations

F2_MAIN = "f2-inventory-main"
F2_VAL = "f2-inventory-valuation-impairment"
F2_SPE = "f2-inventory-special"
F2_STOCKTAKE = "f2-stocktake-bundle"

F1_PREPAYMENT = "f1-prepayment"
F3_NOTES = "f3-notes-payable"
F4_PAYABLE = "f4-accounts-payable"
F5_COST = "f5-cost-of-sales"

F_CYCLE_HTML_TYPES = frozenset({
    F1_PREPAYMENT, F3_NOTES, F4_PAYABLE, F5_COST,
    F2_MAIN, F2_VAL, F2_SPE, F2_STOCKTAKE,
    "confirmation-hub", "a-program-console",
    "confirmation-summary", "confirmation-entity-verify",
    "confirmation-followup", "confirmation-diff-reconcile",
    "confirmation-diff-checklist", "confirmation-alternative-f05",
    "confirmation-alternative-f06", "confirmation-reliability",
    "confirmation-fraud-risk",
})

F2_MAIN_CODES = (
    "F2", "F2A", "F2-1", "F2-2", "F2-3", "F2-4", "F2-5", "F2-6", "F2-7", "F2-8",
    "F2-9", "F2-10", "F2-11", "F2-12", "F2-13", "F2-14", "F2-16", "F2-18", "F2-19",
    "F2-20", "F2-29", "F2-30", "F2-31", "F2-32", "F2-note-listed", "F2-note-soe",
)

F2_VAL_CODES = (
    "F2-33", "F2-34", "F2-35", "F2-38", "F2-39", "F2-40", "F2-41", "F2-42",
    "F2-43", "F2-44", "F2-47", "F2-48", "F2-49", "F2-52",
)

F2_SPE_CODES = (
    "F2-55A", "F2-55", "F2-56", "F2-57", "F2-58", "F2-61A", "F2-61", "F2-62",
    "F2-63", "F2-64", "F2-65", "F2-66", "F2-67", "F2-68", "F2-69", "F2-70",
    "F2-71", "F2-72",
)

F2_STOCKTAKE_CODES = (
    "F2-21A", "F2-21", "F2-22", "F2-23", "F2-24", "F2-25", "F2-26",
)

F2_HTML_MIGRATED: dict[str, str] = {}
for c in F2_MAIN_CODES:
    F2_HTML_MIGRATED[c] = F2_MAIN
for c in F2_VAL_CODES:
    F2_HTML_MIGRATED[c] = F2_VAL
for c in F2_SPE_CODES:
    F2_HTML_MIGRATED[c] = F2_SPE
for c in F2_STOCKTAKE_CODES:
    F2_HTML_MIGRATED[c] = F2_STOCKTAKE


def expected_f2_component_type(wp_code: str) -> str | None:
    return F2_HTML_MIGRATED.get(wp_code)
