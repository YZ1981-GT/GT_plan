"""D 循环（应收/预收/营收）语义科目定位规格 — 跨 D1~D7 单一真源。

科目映射真源 = `report_config` DB 实证（`d-cycle-extraction-chain-completion` spec）：
  D1 `BS-005` = `TB('1121','期末余额') − TB('1231-01','期末余额')`（应收票据）
  D2 `BS-006` = `TB('1122','期末余额') − TB('1231-02','期末余额')`（应收账款）
  D3 `BS-046` = `TB('2203','期末余额')`（预收款项 / 合同负债旧科目）
  D4 营业收入（IS 行，损益类）
  D5 `BS-007` = `TB('1124','期末余额')`（应收款项融资）—— 🔴 1124 在活体科目表不存在
  D6 `BS-011` = `TB('1141','期末余额')`（合同资产）
  D7 `BS-047` = `TB('2205','期末余额')`（合同负债）

🔴 D3/D7 为负债类（`is_liability=True`）—— 2203 预收款项 / 2205 合同负债方向均为贷方。

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


# ─────────────────────────────────── D1~D7 ───────────────────────────────────

D1_SPEC = SemanticAccountSpec(
    row_code="BS-005",
    slots=(
        _gross("gross", ("应收票据",), ("1121",), "应收票据"),
        _provision("provision", ("坏账准备",), ("1231-01",), "坏账准备-应收票据"),
    ),
)

D2_SPEC = SemanticAccountSpec(
    row_code="BS-006",
    slots=(
        _gross("gross", ("应收账款",), ("1122",), "应收账款"),
        _provision("provision", ("坏账准备",), ("1231-02",), "坏账准备-应收账款"),
    ),
)

D3_SPEC = SemanticAccountSpec(
    row_code="BS-046",
    slots=(_gross("gross", ("预收款项",), ("2203",), "预收款项"),),
)

D4_SPEC = SemanticAccountSpec(
    row_code="IS-001",
    slots=(_gross("gross", ("营业收入", "主营业务收入"), ("6001",), "营业收入"),),
)

D5_SPEC = SemanticAccountSpec(
    row_code="BS-007",
    slots=(
        # 🔴 1124 在活体 account_chart 不存在 → fallback=() 宁缺勿造
        SemanticAccountSlot(
            key="gross", names=("应收款项融资",),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=(), label="应收款项融资",
        ),
    ),
)

D6_SPEC = SemanticAccountSpec(
    row_code="BS-011",
    slots=(
        _gross("gross", ("合同资产",), ("1141",), "合同资产"),
        _provision("provision", ("合同资产减值准备",), ("1142",), "合同资产减值准备"),
    ),
)

D7_SPEC = SemanticAccountSpec(
    row_code="BS-047",
    slots=(_gross("gross", ("合同负债",), ("2205",), "合同负债"),),
)


D_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "D1": D1_SPEC,
    "D2": D2_SPEC,
    "D3": D3_SPEC,
    "D4": D4_SPEC,
    "D5": D5_SPEC,
    "D6": D6_SPEC,
    "D7": D7_SPEC,
}

#: 损益类 D 循环
D_PL_CYCLES = frozenset({"D4"})

D_PL_POSITIVE_SIDE: dict[str, str] = {
    "D4": "credit",  # 收入类贷方正方向
}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return D_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "D1_SPEC", "D2_SPEC", "D3_SPEC", "D4_SPEC", "D5_SPEC", "D6_SPEC", "D7_SPEC",
    "D_CYCLE_SPECS", "D_PL_CYCLES", "D_PL_POSITIVE_SIDE", "spec_of",
]
