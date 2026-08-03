"""I 循环（无形资产/开发支出/商誉/长期待摊/其他非流动/研发费用）语义科目定位规格。

科目映射真源 = `report_config` DB 实证：
  I1 `BS-032` = `TB('1701','期末余额')`（无形资产）+ 备抵 `IMP-011`=`TB('1702')`
  I2 `BS-033` = `TB('1711','期末余额')`（开发支出）
  I3 `BS-034` = `TB('1721','期末余额')`（商誉）+ 备抵 `IMP-012`=`TB('1722')`
  I4 `BS-035` = `TB('1801','期末余额')`（长期待摊费用）
  I5 `BS-039` = `TB('1901','期末余额')`（其他非流动资产）— 🔴 与 K2 共用 1901
  I6 研发费用 — 🔴 标准码未实证，不给兜底码（`6602` 是管理费用，属 K9）
  I6 研发费用（IS 行，损益类）

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


def _provision(key, names, fallback, label):
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=("减值损失",),
        fallback_standard_codes=fallback, label=label, is_provision=True,
    )


I1_SPEC = SemanticAccountSpec(
    row_code="BS-032",
    slots=(
        _gross("gross", ("无形资产",), ("1701",), "无形资产"),
        _provision("provision", ("无形资产减值准备",), ("1702",), "无形资产减值准备"),
    ),
)

I2_SPEC = SemanticAccountSpec(
    row_code="BS-033",
    slots=(_gross("gross", ("开发支出",), ("1711",), "开发支出"),),
)

I3_SPEC = SemanticAccountSpec(
    row_code="BS-034",
    slots=(
        _gross("gross", ("商誉",), ("1721",), "商誉"),
        _provision("provision", ("商誉减值准备",), ("1722",), "商誉减值准备"),
    ),
)

I4_SPEC = SemanticAccountSpec(
    row_code="BS-035",
    slots=(_gross("gross", ("长期待摊费用",), ("1801",), "长期待摊费用"),),
)

I5_SPEC = SemanticAccountSpec(
    row_code="BS-039",
    slots=(_gross("gross", ("其他非流动资产",), ("1901",), "其他非流动资产"),),
)

I6_SPEC = SemanticAccountSpec(
    row_code="IS-007",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("研发费用", "研究开发费用"),
            exclude_names=(),
            # 🔴 不给兜底码：`6602` 是**管理费用**（已被 K9 按 DB 实证认领），
            #    研发费用在本平台的标准码未经实证 → 宁缺勿造，靠科目名逐项目定位
            fallback_standard_codes=(),
            label="研发费用",
        ),
    ),
)


I_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "I1": I1_SPEC, "I2": I2_SPEC, "I3": I3_SPEC,
    "I4": I4_SPEC, "I5": I5_SPEC, "I6": I6_SPEC,
}

I_PL_CYCLES = frozenset({"I6"})
I_PL_POSITIVE_SIDE: dict[str, str] = {"I6": "debit"}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return I_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "I1_SPEC", "I2_SPEC", "I3_SPEC", "I4_SPEC", "I5_SPEC", "I6_SPEC",
    "I_CYCLE_SPECS", "I_PL_CYCLES", "I_PL_POSITIVE_SIDE", "spec_of",
]
