"""H2 在建工程的语义科目定位规格（单一真源）。

**报表行**（`report_config` 实证）::

    BS-029 在建工程
      soe_standalone : TB('1604','期末余额')

`1605 工程物资` 同属 `BS-029` 但不是减值准备而是独立资产子项 → 单独槽 `eng_mat`。
H4 工程物资循环反向单列 `1604`。

**IMP-012 在建工程减值准备** formula=NULL，且平台标准科目表**无该科目独立编码**
（`1605` 是工程物资、`1606` 是固定资产清理）。

🔴 **`impairment` 槽 `fallback_standard_codes=()` 是有意为之，不是遗漏**
（2026-08-03 复盘实证）：

- 客户科目表自建了该科目（如 `1607 在建工程减值准备`）→ 按**科目名**命中，取数正常；
- 多数项目没有该科目 → `found=False`，调用方显示「本项目无此科目」而非取 0（宁缺勿造）。

若给它硬编码一个兜底码，在「客户没有该科目」时会取到别的科目的钱 —— 这正是
本 spec 要修的 P0 类缺陷（H8 取 `1901`、H9 取 `2205`）。故**保留空兜底**，
由 `test_h2_impairment_slot_semantics` 双向锁死。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = (
    "减值准备",
    "物资",
    "减值损失",
)

#: 槽键 → 前端 `tb_values` 键前缀
H2_SLOT_KEY_PREFIX = {
    "gross": "cip",
    "eng_mat": "eng_mat",
    "impairment": "cip_imp",
}

H2_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-029",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("在建工程",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=("1604",),
            label="在建工程",
        ),
        SemanticAccountSlot(
            key="eng_mat",
            names=("工程物资",),
            exclude_names=("减值准备", "减值损失"),
            fallback_standard_codes=("1605",),
            label="工程物资",
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("在建工程减值准备",),
            exclude_names=("减值损失",),
            fallback_standard_codes=(),
            label="在建工程减值准备",
            is_provision=True,
            # 🔴 槽级 row_code（消除假冲突告警）：spec 级 `BS-029 = TB('1604')` 只含原值，
            # 而 `build_conflicts` 会拿它的码集**逐槽**比对 ⇒ 备抵槽一旦定位到客户自建的
            # 减值准备科目就恒报 `('impairment','1604',<实际码>)` 假冲突。
            # 备抵在 `report_config` 里自成一行 `IMP-012 在建工程减值准备`，
            # 声明它即改用**它自己那条行**作对照基准。
            #
            # 该行两个变体公式**实测均为 NULL**（2026-08-12 postgres 只读复核：
            # soe_standalone / soe_consolidated 都是 None）⇒ 声明后 basis 为空、
            # 走 `build_conflicts` 的**三态跳过**（「未知」不等于「有冲突」）。
            # 这**也是**修好 —— 假告警消除；不得因「无公式可对照」而不声明，
            # 否则该槽会继续拿主行码集比对并恒报假冲突。
            row_code="IMP-012",
        ),
    ),
)

__all__ = ["H2_ACCOUNT_SPEC", "H2_SLOT_KEY_PREFIX"]
