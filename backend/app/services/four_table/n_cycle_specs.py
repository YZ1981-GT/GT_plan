"""N 循环（递延税/应交税费/税金及附加/所得税费用）语义科目定位规格。

科目映射真源 = `report_config` DB 实证 + `n1-four-table-…` / `n-cycle-tax-…` spec：
  N1 `BS-036` = `TB('1811','期末余额')`（递延所得税资产）
  N2 应交税费（非标准取数，子科目按税种名归类）`BS-052` = `TB('2221')`
  N3 `BS-067` = `TB('2901','期末余额')`（递延所得税负债）
  N4 税金及附加（IS 行，损益类）`IS-003` = `TB('6403','本期发生额')`
  N5 所得税费用（IS 行，损益类）`IS-023` = `TB('6801','本期发生额')`

🔴 N4/N5 为损益类：`tb_balance.closing_balance` 结构性恒为 0，须取发生额。
🔴 N2 负债类（2221 应交税费方向为贷方）。

spec: .kiro/specs/semantic-account-resolver-full-rollout/

.. warning::
   🔴 **本文件的兜底码尚未逐项 DB 实证**（未核 `report_config` / `account_chart` /
   `tb_balance` 三方）。当前**没有任何 render 策略用它驱动取数**，故不影响运行。
   接线前必须逐个循环按平台铁律核对真源，否则会重演「取错整个科目族」级缺陷
   （已实证教训：本文件 M 循环 7/7 兜底码曾与平台实证值全不符，已按 DB 值修正）。
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计折旧", "累计摊销", "减值损失")


def _gross(key, names, fallback, label, extra_excludes=()):
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=_PROVISION_WORDS + extra_excludes,
        fallback_standard_codes=fallback, label=label,
    )


N1_SPEC = SemanticAccountSpec(
    row_code="BS-036",
    slots=(_gross("gross", ("递延所得税资产",), ("1811",), "递延所得税资产"),),
)

N2_SPEC = SemanticAccountSpec(
    row_code="BS-052",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("应交税费",),
            exclude_names=(), fallback_standard_codes=("2221",), label="应交税费",
        ),
    ),
)

N3_SPEC = SemanticAccountSpec(
    row_code="BS-067",
    slots=(_gross("gross", ("递延所得税负债",), ("2901",), "递延所得税负债"),),
)

N4_SPEC = SemanticAccountSpec(
    row_code="IS-003",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("税金及附加",),
            exclude_names=(), fallback_standard_codes=("6403",), label="税金及附加",
        ),
    ),
)

N5_SPEC = SemanticAccountSpec(
    row_code="IS-023",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("所得税费用",),
            exclude_names=(), fallback_standard_codes=("6801",), label="所得税费用",
        ),
    ),
)


N_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "N1": N1_SPEC, "N2": N2_SPEC, "N3": N3_SPEC, "N4": N4_SPEC, "N5": N5_SPEC,
}

N_PL_CYCLES = frozenset({"N4", "N5"})
N_PL_POSITIVE_SIDE: dict[str, str] = {
    "N4": "debit",   # 费用类借方正方向
    "N5": "debit",
}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return N_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "N1_SPEC", "N2_SPEC", "N3_SPEC", "N4_SPEC", "N5_SPEC",
    "N_CYCLE_SPECS", "N_PL_CYCLES", "N_PL_POSITIVE_SIDE", "spec_of",
]
