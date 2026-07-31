"""D1 应收票据科目定位 —— 报表规则映射驱动（替代硬编码科目前缀）.

spec: .kiro/specs/d1-extraction-chain-completion/
      (Requirements 1.1~1.6 / Property 1, 2, 3)

**2026-07-31 起本模块是薄壳**：通用逻辑（报表行 → 标准码 → 原值/备抵拆分 →
`account_mapping` 反解 → fail-open 兜底）已提升为跨循环共享件
`app/services/four_table/report_line_accounts.py`，本模块只保留 D1 的
**参数**（报表行 `BS-005`、兜底码 `1121`/`1231-01`、名称过滤词「应收票据」）
与 D1 专属返回类型 `D1AccountCodes`。K1 其他应收款是同一共享件的第二个消费者。
迁移零回归由 `backend/tests/d_cycle_extraction/test_d1_account_resolver.py` 守。

**为什么不能硬编码 `1121` / `1231` + 名称含「应收票据」**

四表库入库后的科目关系是三层，实证（DB 只读核查）如下::

    tb_balance.account_code          = 客户**原始码**   1121 / 1121.01 / 1231.01
            │  account_mapping(project_id, original_account_code → standard_account_code)
            ▼
    trial_balance.standard_account_code = **标准码**     1121 / 1231-01
            │  report_config.formula（按 applicable_standard）
            ▼
    报表行 BS-005「应收票据」
       soe_standalone       : TB('1121','期末余额') - TB('1231-01','期末余额')
       listed_* / soe_consol: TB('1121','期末余额')

即客户把「坏账准备_应收票据」编在 `1231.01`，平台标准码是 `1231-01`，而 `soe_standalone`
的 BS-005 公式正是引用 `1231-01` —— 所以**坏账科目应由报表规则映射解析，而不是名称猜测**。
名称猜测在客户科目命名不含「应收票据」（如「坏账准备_票据」）时会静默取不到数。

同时 `tb_balance` 存的是**原始码**，故解析出标准码后还须经 `account_mapping` 反解回该项目
的原始码集合，才能正确前缀匹配（`1231-01` 直接当前缀匹配不到 `1231.01`）。

**fail-open 铁律**：任一环失败（report_config 无该行 / account_chart 空 / account_mapping
空 / DB 异常）一律回退到与改动前等价的行为（`1121` 原值 + `1231` 坏账前缀），并在
`resolved_from` 标注来源，绝不阻断 render。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    ReportLineAccountSpec,
    _PROVISION_CODE_PREFIXES,
    _PROVISION_NAME_HINTS,
    _is_provision_code,
    fetch_applicable_standards as _fetch_applicable_standards,
    fetch_standard_chart_rows as _fetch_standard_chart_rows,
    normalize_standard_prefix,
    resolve_report_line_accounts,
    split_gross_provision,
    to_original_codes,
    to_original_codes_with_flag as _to_original_codes_with_flag,
)

logger = logging.getLogger(__name__)

# 报表行次（DB 实证：listed_standalone / listed_consolidated / soe_standalone /
# soe_consolidated 四个准则的「应收票据」行 row_code 均为 BS-005）
D1_REPORT_ROW_CODE = "BS-005"

# 兜底科目（标准码口径）：原值 1121、坏账准备 1231-01
D1_FALLBACK_GROSS = "1121"
D1_FALLBACK_PROVISION = "1231-01"
D1_FALLBACK_CODES = [D1_FALLBACK_GROSS, D1_FALLBACK_PROVISION]

# 坏账侧名称过滤（仅在 fallback 口径下叠加，防把应收账款/其他应收款坏账算进 D1）
D1_PROVISION_NAME_FILTER = "应收票据"

#: D1 的科目定位规格（喂给共享解析器）
D1_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code=D1_REPORT_ROW_CODE,
    fallback_gross=(D1_FALLBACK_GROSS,),
    fallback_provision=(D1_FALLBACK_PROVISION,),
    provision_name_filter=D1_PROVISION_NAME_FILTER,
)


@dataclass(frozen=True)
class D1AccountCodes:
    """D1 科目定位结果。

    Attributes:
        gross: 原值科目 —— **原始码**前缀集（用于 `tb_balance` / `tb_aux_balance`）。
        provision: 坏账准备科目 —— 原始码前缀集。
        gross_standard: 原值科目 —— **标准码**集（用于 `trial_balance`）。
        provision_standard: 坏账准备科目 —— 标准码集。
        resolved_from: `report_config`（报表规则映射解析成功）或 `fallback`（兜底）。
    """

    gross: list[str] = field(default_factory=list)
    provision: list[str] = field(default_factory=list)
    gross_standard: list[str] = field(default_factory=list)
    provision_standard: list[str] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_FALLBACK
    provision_resolved_from: str = RESOLVED_FROM_FALLBACK

    @property
    def use_provision_name_filter(self) -> bool:
        """坏账侧是否需要叠加名称过滤。

        报表映射已把坏账精确到 `1231-01`（该标准码语义就是「坏账准备-应收票据」），
        再叠名称过滤会把客户命名不含「应收票据」的子科目误杀 → 只有 fallback
        （拿的是宽口径 `1231` 前缀）才需要名称过滤把其它应收科目的坏账剔掉。
        """
        return self.provision_resolved_from == RESOLVED_FROM_FALLBACK

    def as_dict(self) -> dict:
        """供 render 输出 `tb_source_codes`（取数溯源，前端展示）。"""
        return asdict(self)


async def resolve_d1_account_codes(ctx) -> D1AccountCodes:
    """解析 D1 原值 / 坏账准备科目（报表规则映射驱动，全程 fail-open）。

    Returns:
        `D1AccountCodes`；任一环失败均返回可用结果（兜底 `1121` / `1231`），
        `resolved_from` 标注实际来源。`gross` 恒非空（Property 1）。
    """
    acc = await resolve_report_line_accounts(ctx, D1_ACCOUNT_SPEC)
    return D1AccountCodes(
        gross=list(acc.gross),
        provision=list(acc.provision),
        gross_standard=list(acc.gross_standard),
        provision_standard=list(acc.provision_standard),
        resolved_from=acc.resolved_from,
        provision_resolved_from=acc.provision_resolved_from,
    )


__all__ = [
    "D1_ACCOUNT_SPEC",
    "D1_FALLBACK_CODES",
    "D1_FALLBACK_GROSS",
    "D1_FALLBACK_PROVISION",
    "D1_PROVISION_NAME_FILTER",
    "D1_REPORT_ROW_CODE",
    "D1AccountCodes",
    "RESOLVED_FROM_FALLBACK",
    "RESOLVED_FROM_REPORT",
    "normalize_standard_prefix",
    "resolve_d1_account_codes",
    "split_gross_provision",
    "to_original_codes",
]

# 兼容：既有测试/调用方可能引用这些名（原本定义在本模块）
_ = (
    _PROVISION_NAME_HINTS,
    _PROVISION_CODE_PREFIXES,
    _is_provision_code,
    _fetch_applicable_standards,
    _fetch_standard_chart_rows,
    _to_original_codes_with_flag,
)
