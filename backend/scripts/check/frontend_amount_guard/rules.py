"""
NUMERIC_CANDIDATE_RULES – the single source of truth for numeric display
node identification and violation predicates.

Design reference: §17 G6.
"""
from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# Include / Exclude constants (§15 A8, revised by §16 F9 / N8)
# ──────────────────────────────────────────────────────────────
INCLUDE_GLOBS: tuple[str, ...] = (
    "src/**/*.vue",
    "src/**/*.ts",
    "src/**/*.tsx",
    "src/**/*.js",
    "src/**/*.jsx",
    "src/**/*.mjs",
    "src/**/*.cjs",
)

EXCLUDE_GLOBS: tuple[str, ...] = (
    "**/__tests__/**",
    "**/*.spec.*",
    "**/*.test.*",
    "src/stories/**",
    "src/test/**",
    "src/*.d.ts",
)

# ──────────────────────────────────────────────────────────────
# §17 G6 ① – Explicit kind sources (highest priority)
# If any matches, the node is NOT an unknown numeric candidate.
# ──────────────────────────────────────────────────────────────

#: Component tags whose presence determines the kind.
EXPLICIT_KIND_COMPONENTS: dict[str, str] = {
    "GtAmountCell": "amount",
    "gt-amount-cell": "amount",
    "g-t-amount-cell": "amount",
}

#: Components that accept an explicit `kind` prop.
KIND_PROP_COMPONENTS: tuple[str, ...] = (
    "GtMeasureCell",
    "gt-measure-cell",
    "g-t-measure-cell",
)

#: Formatter calls where column definition is passed as argument
#: (kind comes from runtime column definition → "declared").
RUNTIME_KIND_CALLEES: tuple[str, ...] = (
    "formatMeasure",
)

#: GtColumn object literal key that carries measure kind.
GT_COLUMN_KIND_KEY: str = "measureKind"

# ──────────────────────────────────────────────────────────────
# §17 G6 ② – Structural signals (S1–S4)
# Any signal → node is a numeric candidate.
# ──────────────────────────────────────────────────────────────

#: S1 – right-aligned el-table-column (static or literal binding)
S1_RIGHT_ALIGN_ATTRS: tuple[str, ...] = ("align", "header-align")

#: S2 – numeric conversion / formatting calls in output expressions
S2_NUMERIC_CALLS: tuple[str, ...] = (
    "toFixed",
    "toLocaleString",
    "Number",
    "parseFloat",
)

#: S2 – constructor / class references
S2_NUMERIC_CONSTRUCTORS: tuple[str, ...] = (
    "Intl.NumberFormat",
    "Decimal",
)

#: S3 – legacy numeric formatters from utils/formatters.ts
#: Guard: every export from that file MUST be classified as numeric or non-numeric;
#: an unclassified new export is a guard failure.
LEGACY_NUMERIC_FORMATTERS: frozenset[str] = frozenset({
    "fmtAmount",
    "fmtNumber",
    "fmtPercent",
    "fmtPct",
    "fmtCurrency",
    "fmtDecimal",
    "formatNumber",
    "formatAmount",
    "displayAmount",
    "amountFormatter",
    "toCurrency",
    "formatCurrency",
    "formatDecimal",
    "toFixedStr",
})

#: Exports from utils/formatters.ts known to be NON-numeric.
LEGACY_NON_NUMERIC_FORMATTERS: frozenset[str] = frozenset({
    "fmtDate",
    "fmtDateTime",
    "fmtDateRange",
    "fmtBoolean",
    "fmtText",
    "fmtStatus",
    "fmtFileSize",
    "fmtDuration",
    "parseServerTime",
    "formatDate",
    "formatTime",
    "stripHtml",
    "truncateText",
    "escapeHtml",
    "fmtDateShort",
})

#: S4 – GtColumn object literal with type: 'number'
S4_GT_COLUMN_NUMBER_TYPE: str = "number"

# ──────────────────────────────────────────────────────────────
# §17 G6 ③ – NOT display nodes (excluded from analysis)
# ──────────────────────────────────────────────────────────────
NON_DISPLAY_ELEMENTS: frozenset[str] = frozenset({
    "el-input",
    "el-input-number",
    "ElInput",
    "ElInputNumber",
    "WpAmountInput",
    "wp-amount-input",
})

NON_DISPLAY_ATTRS: frozenset[str] = frozenset({
    "data-gt-value",
})

# ──────────────────────────────────────────────────────────────
# §17 G6 ④ – Amount keywords (for triage annotation, not standalone signal)
# ──────────────────────────────────────────────────────────────
AMOUNT_KEYWORDS_EN: frozenset[str] = frozenset({
    "amount", "balance", "debit", "credit",
    "cost", "price", "principal", "interest",
    "payable", "receivable", "salary", "fund",
    "equity", "capital", "fee", "charge",
    "discount", "profit", "loss", "revenue",
    "expense", "income", "net_asset", "netasset",
    "tax",
})

AMOUNT_KEYWORDS_ZH: frozenset[str] = frozenset({
    "金额", "余额", "借方", "贷方", "发生额",
    "审定", "未审", "调整",
    "税金", "税额", "成本", "价格", "合计", "小计",
    "总计", "总额", "本金", "利息", "应付", "应收",
})

# ──────────────────────────────────────────────────────────────
# §17 G6 ⑤ – Core violation predicates (a–d)
# ──────────────────────────────────────────────────────────────
# These are checked by the analyzer; a match is a hard failure
# in core-matrix files, not a ledger entry.

# a) Unknown numeric in core matrix → violation (implicit, no constant needed)

# b) Amount formatter applied to a known non-amount kind
VIOLATION_AMOUNT_FMT_ON_NON_AMOUNT: str = "amount_formatter_on_non_amount"

# c) <GtAmountCell> with :unit or unit attribute (§15 A7)
VIOLATION_GT_AMOUNT_CELL_WITH_UNIT: str = "gt_amount_cell_with_unit"

# d) Core el-table-v2 cellRenderer / headerCellRenderer with fixed px fontSize
VIOLATION_V2_FIXED_PX_FONT: str = "v2_fixed_px_font_size"

# All core violation codes
CORE_VIOLATION_CODES: frozenset[str] = frozenset({
    VIOLATION_AMOUNT_FMT_ON_NON_AMOUNT,
    VIOLATION_GT_AMOUNT_CELL_WITH_UNIT,
    VIOLATION_V2_FIXED_PX_FONT,
})

# ──────────────────────────────────────────────────────────────
# Scan scope drift sentinel
# ──────────────────────────────────────────────────────────────
SCAN_SCOPE_DRIFT: str = "SCAN_SCOPE_DRIFT"
