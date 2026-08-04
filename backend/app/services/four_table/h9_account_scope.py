"""H9 租赁负债的语义科目定位规格（单一真源）。

**修掉的真实缺陷**

`_h9_lease_liabilities._H9_ACCOUNT_PREFIXES = {"2205"}` ——
`2205` 实为**合同负债**（D7 循环的科目，`BS-047`=`TB('2205')`）。
租赁负债真值 `2601`，未确认融资费用 `2602`。

**报表行**（`report_config` 实证）::

    BS-063 租赁负债
      soe_standalone : TB('2601','期末余额') - TB('2602','期末余额')

`2602 未确认融资费用` 在 `account_chart` 中 `direction` 有 debit/credit 两种标注
→ 必须 `is_provision=True` 显式声明，靠名称定位。

🔴 **H9 是负债类循环**：`2601` 在 `account_chart` 里 `direction='credit'`，
取余额时不需要 abs()（贷方余额即正值表示负债规模），
但 `2602` 作为抵减项取绝对值再从 `2601` 中减去。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 槽键 → 前端 `tb_values` 键前缀
H9_SLOT_KEY_PREFIX = {
    "gross": "lease_liability",
    "unearned_finance": "unearned_finance",
}

H9_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-063",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("租赁负债",),
            exclude_names=("未确认融资费用", "一年内到期"),
            fallback_standard_codes=("2601",),
            label="租赁负债",
        ),
        # 🔴 裸名 `未确认融资费用` 在全库**同时**对应两个顶层科目（2026-08-04 DB 实证）：
        #    `2602` = 租赁负债的未确认融资费用（standard 侧 6 个项目）
        #    `2702` = **长期应付款**的未确认融资费用（standard 7 / client 4 个项目，
        #             `df5b8403` 的 client 侧甚至直接命名为「长期应付款未确认融资费用」）
        #    → 只按裸名定位会把 L5 的 contra 扣进租赁负债（当前 `2702` 全库余额为空，
        #      属**潜伏态**；一旦有余额就是错数）。故名称只认带主体前缀的写法，
        #      裸名交由第③/④层的 `2602` 码定位（要求它在本项目科目表里确实存在）。
        #    客户把它记成 `2651.02` 子科目的情形由 `h0_book_amounts._resolve_one`
        #    的「族内子科目不重复扣减」规则处理（父族聚合已按方向净掉）。
        SemanticAccountSlot(
            key="unearned_finance",
            names=("租赁负债未确认融资费用",),
            exclude_names=("长期应付款",),
            fallback_standard_codes=("2602",),
            label="未确认融资费用",
            is_provision=True,
        ),
    ),
    legacy_standard_names=("长期应付款",),
)

__all__ = ["H9_ACCOUNT_SPEC", "H9_SLOT_KEY_PREFIX"]
