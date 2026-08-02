"""四表库取数共享件（跨循环复用，禁止各循环再造方言）。

模块划分::

    report_line_accounts.py   报表映射规则驱动的科目定位（原值 / 备抵 / 附加科目）
    leaf_aggregation.py       tb_balance 叶子科目聚合（叶子和 == 父科目额）
    i_cycle_accounts.py       I1~I6 分段科目动态解析（按准则挑行 + 行名校验 + 冲突诊断）
    i1_asset_categories.py    I1 无形资产类别单一真源（11 类，按科目名归类）
    i_cycle_prefill.py        I 类预填行集构建（纯函数）
    i_cycle_extraction.py     I 类取数编排（六个 render 策略的唯一入口）

首批消费者：D1 应收票据（`d_cycle_extraction/d1_account_resolver` 薄壳委托）、
K1 其他应收款（`wp_render_strategies/_k1_other_receivables`）；
I 类六循环走 `i_cycle_extraction.load_i_cycle_extraction`。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
"""

from .leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    parent_totals,
    select_leaves,
    to_leaf_rows,
)
from .report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    ReportLineAccounts,
    ReportLineAccountSpec,
    extract_signed_codes,
    minimal_prefix_set,
    normalize_standard_prefix,
    resolve_report_line_accounts,
    split_gross_provision,
)

__all__ = [
    "LeafRow",
    "RESOLVED_FROM_FALLBACK",
    "RESOLVED_FROM_REPORT",
    "ReportLineAccountSpec",
    "ReportLineAccounts",
    "aggregate_leaves",
    "extract_signed_codes",
    "filter_by_prefixes",
    "minimal_prefix_set",
    "normalize_standard_prefix",
    "parent_totals",
    "resolve_report_line_accounts",
    "select_leaves",
    "split_gross_provision",
    "to_leaf_rows",
]
