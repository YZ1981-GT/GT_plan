"""四表库取数共享件（跨循环复用，禁止各循环再造方言）。

模块划分::

    report_line_accounts.py     报表映射规则驱动的科目定位（原值 / 备抵 / 附加科目）
    semantic_account_resolver.py 语义（科目名）驱动的**逐项目**科目定位 —— 标准码在
                                 各项目并不一致（`account_mapping` 同一原始码在不同项目
                                 映射到不同标准码；标准科目表本身各项目也不同），故新循环
                                 优先用它，`report_config` 降级为提示 + 冲突检测
    leaf_aggregation.py         tb_balance 叶子科目聚合（叶子和 == 父科目额）
    g_cycle_adjudication_prefill.py  G 循环审定表「从四表库带入未审数」统一载荷
                                 （逐叶子明细 + 建议落点，归类在前端做）
    i_cycle_accounts.py         I1~I6 分段科目动态解析（按准则挑行 + 行名校验 + 冲突诊断）
    i1_asset_categories.py      I1 无形资产类别单一真源（11 类，按科目名归类）
    i_cycle_prefill.py          I 类预填行集构建（纯函数）
    i_cycle_extraction.py       I 类取数编排（六个 render 策略的唯一入口）

首批消费者：D1 应收票据（`d_cycle_extraction/d1_account_resolver` 薄壳委托）、
K1 其他应收款（`wp_render_strategies/_k1_other_receivables`）；
I 类六循环走 `i_cycle_extraction.load_i_cycle_extraction`。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
"""

from .e1_restricted_buckets import (
    E1_RESTRICTED_BUCKET_BY_KEY,
    E1_RESTRICTED_BUCKETS,
    UNRESTRICTED,
    E1RestrictedBucket,
    bucket_defs_payload,
    classify_e1_restricted_leaf,
)
from .g_cycle_adjudication_prefill import (
    PERIOD_BALANCE,
    PERIOD_CURRENT,
    SlotView,
    balance_amounts,
    build_g_adjudication_prefill,
    normalize_slots,
    pl_occurrence,
    slot_of_code,
)
from .leaf_aggregation import (
    CONVENTION_AS_STORED,
    CONVENTION_DIRECTIONAL,
    LeafRow,
    LeafTotals,
    aggregate_by_specs,
    aggregate_leaves,
    filter_by_code_specs,
    filter_by_prefixes,
    leaf_sign_map,
    leaf_signs,
    parent_totals,
    resolve_leaf_totals,
    select_leaves,
    sql_prefixes_for_specs,
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
    to_original_codes,
    to_original_codes_with_flag,
)
from .tb_query import (
    fetch_tb_subtree,
    fetch_trial_balance_amounts,
    fetch_trial_balance_rows,
)
from .semantic_account_resolver import (
    RESOLVED_FROM_CLIENT_CHART,
    RESOLVED_FROM_NONE,
    RESOLVED_FROM_REPORT_CONFIG,
    RESOLVED_FROM_STANDARD_CHART,
    ChartRow,
    ResolvedSlot,
    SemanticAccountResult,
    SemanticAccountSlot,
    SemanticAccountSpec,
    is_top_level_code,
    match_slot_in_chart,
    normalize_account_name,
    resolve_semantic_accounts,
)

__all__ = [
    "CONVENTION_AS_STORED",
    "CONVENTION_DIRECTIONAL",
    "PERIOD_BALANCE",
    "PERIOD_CURRENT",
    "SlotView",
    "balance_amounts",
    "build_g_adjudication_prefill",
    "normalize_slots",
    "pl_occurrence",
    "slot_of_code",
    "E1_RESTRICTED_BUCKETS",
    "E1_RESTRICTED_BUCKET_BY_KEY",
    "E1RestrictedBucket",
    "UNRESTRICTED",
    "bucket_defs_payload",
    "classify_e1_restricted_leaf",
    "RESOLVED_FROM_CLIENT_CHART",
    "RESOLVED_FROM_FALLBACK",
    "RESOLVED_FROM_NONE",
    "RESOLVED_FROM_REPORT",
    "RESOLVED_FROM_REPORT_CONFIG",
    "RESOLVED_FROM_STANDARD_CHART",
    "ChartRow",
    "LeafRow",
    "LeafTotals",
    "ReportLineAccountSpec",
    "ReportLineAccounts",
    "ResolvedSlot",
    "SemanticAccountResult",
    "SemanticAccountSlot",
    "SemanticAccountSpec",
    "aggregate_by_specs",
    "aggregate_leaves",
    "extract_signed_codes",
    "fetch_tb_subtree",
    "fetch_trial_balance_amounts",
    "fetch_trial_balance_rows",
    "filter_by_code_specs",
    "filter_by_prefixes",
    "is_top_level_code",
    "leaf_sign_map",
    "leaf_signs",
    "match_slot_in_chart",
    "minimal_prefix_set",
    "normalize_account_name",
    "normalize_standard_prefix",
    "parent_totals",
    "resolve_leaf_totals",
    "resolve_report_line_accounts",
    "resolve_semantic_accounts",
    "select_leaves",
    "split_gross_provision",
    "sql_prefixes_for_specs",
    "to_leaf_rows",
    "to_original_codes",
    "to_original_codes_with_flag",
]
