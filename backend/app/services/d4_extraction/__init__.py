"""D4 营业收入四表取数（报表行驱动的动态科目定位）。

模块划分::

    account_scope.py   报表行 → 科目定位 → account_mapping 反解 → 收入/成本镜像配对
    occurrence.py      损益类发生额取数口径（tb_ledger 单侧 / trial_balance 符号归一）

🔴 本包**不重复实现**共享件已有能力：
  * 报表行解析          → `four_table.resolve_report_line_accounts`
  * 区间码展开          → `four_table.sql_prefixes_for_specs` / `filter_by_code_specs`
  * 叶子聚合 + 符号约定 → `four_table.resolve_leaf_totals`（发生额恒按原样求和）

spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/
"""

from .account_scope import (
    D4_COST_FALLBACK,
    D4_COST_ROW_CODE,
    D4_REVENUE_FALLBACK,
    D4_REVENUE_ROW_CODE,
    D4_ROOT_PAIRS,
    D4AccountScope,
    SegmentPair,
    build_d4_source_codes,
    code_in_specs,
    converge_to_d4_semantics,
    expand_specs_to_project_standards,
    fetch_d4_leaf_rows,
    fetch_d4_rows,
    pair_revenue_cost_leaves,
    resolve_d4_accounts,
    split_leaf_head_suffix,
    strip_segment_name_prefix,
)
from .occurrence import (
    COST_SIDE,
    REVENUE_SIDE,
    ledger_occurrence_expr,
    ledger_occurrence_sql,
    normalize_trial_balance_pl,
)

__all__ = [
    "COST_SIDE",
    "D4AccountScope",
    "D4_COST_FALLBACK",
    "D4_COST_ROW_CODE",
    "D4_REVENUE_FALLBACK",
    "D4_REVENUE_ROW_CODE",
    "D4_ROOT_PAIRS",
    "REVENUE_SIDE",
    "SegmentPair",
    "build_d4_source_codes",
    "code_in_specs",
    "converge_to_d4_semantics",
    "expand_specs_to_project_standards",
    "fetch_d4_leaf_rows",
    "fetch_d4_rows",
    "ledger_occurrence_expr",
    "ledger_occurrence_sql",
    "normalize_trial_balance_pl",
    "pair_revenue_cost_leaves",
    "resolve_d4_accounts",
    "split_leaf_head_suffix",
    "strip_segment_name_prefix",
]
