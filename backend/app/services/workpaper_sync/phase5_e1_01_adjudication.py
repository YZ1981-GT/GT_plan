# -*- coding: utf-8 -*-
"""E1-1「货币资金审定表」—— `AdjudicationSheetSpec` 实例声明（slot_driven 模式）。

spec: e1-sync-coverage-and-first-canary · Task 20 · Requirements 4.1~4.7, 8.1
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 几何（openpyxl 逐格实测，2026-09-26）═══

47r×10c / **193** 公式（密度 **41%**）—— 全平台审定表里公式最多、密度最高。

**表头**：R5-R7（项目/期初/期末/调整/审定/变动/原因分析），三行表头。

**数据区**（slot_driven，`E1_SLOT_ORDER` 常量定顺序）：

与 D1-1 的三区模型（gross/bd/net）不同，E1-1 是**平铺槽位**结构——每行一个科目，
由 `E1TabAdjudication.vue` 的 `E1_SLOT_ORDER` 常量定顺序（不分区块）。科目包括：
  - 库存现金 R8
  - 银行存款 R9（含机构类/理财类/其他类子行 R10-R12）
  - 数字货币 R13
  - 其他货币资金 R14
  - 合计 R15
  - 小计（含受限资金 R17-R22 / 非受限 R23-R28）
  - 试算平衡表数 R30
  - 差异 R31

🔴 **slot_driven 不分 section**：E1-1 的行是 per-cell 槽位（`E1-adj-{item}-{field}`），
   不走 `AdjudicationSection` 的区块模型。`row_mode = slot_driven`。

🔴 **三个值来源**（spec 需求 4.5）：
  1. 本 sheet 人工：`E1-adj-diff-note` / `E1-adj-total-note` / 各项 `reason_analysis`
  2. 跨 sheet 聚合：`E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited`
     6 键取自 E1-3 分组小计（`useE1BankDetail:80-90`）
  3. 跨册：`E1-accrued-interest-rows` 属**第 3 册**（范围外）
     ⇒ 须定义「第 3 册未受管」时的降级行为（不得因缺失判成空/0）

🔴 **TB 发布门（裁决 H9 / E1-P17）**：
  `E1TabAdjudication.vue:336` 有 `data-testid="e1-publish-tb"` → `publishToTb`。
  sync 回写路径**不得**触达 `trial_balance`。三条红线：
  ① sync 回写路径对 trial_balance 写次数为 0
  ② 未点发布前 trial_balance 不变
  ③ 两道 CI 守卫 check_tb_writeback_no_direct_call / check_tb_publish_confirm_gate 保持绿

🔴 **本声明只交付几何 + 逐格 mask + 值来源**。
   存量迁移与四态状态机接入是后续真栈任务。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = [
    "SPEC_E101",
    "MANAGED_SHEET_E101",
    "E1_ADJ_PREFIX",
    "E1_SLOT_ORDER",
    "CROSS_SHEET_AGGREGATION_KEYS_E101",
    "CROSS_VOLUME_KEYS_E101",
    "TB_PUBLISH_TESTID_E101",
]

MANAGED_SHEET_E101: Final[str] = "货币资金审定表E1-1"
TEMPLATE_ID_E101: Final[str] = "E11"
SHEET_KEY_E101: Final[str] = f"{TEMPLATE_ID_E101.lower()}-managed"

#: per-cell 锚点键的前缀（前端 `E1TabAdjudication.vue` 的 per-cell 键格式）。
E1_ADJ_PREFIX: Final[str] = "E1-adj-"

#: TB 发布门的 data-testid（E1TabAdjudication.vue:336）。
TB_PUBLISH_TESTID_E101: Final[str] = "e1-publish-tb"

#: 🔴 E1-1 的槽位顺序（从 E1TabAdjudication.vue 的 E1_SLOT_ORDER 常量取）。
#:    slot_driven 模式用它而不是 section 的 first_data_row/last_data_row。
E1_SLOT_ORDER: Final[tuple[str, ...]] = (
    "cash",                    # R8  库存现金
    "bank_deposit",            # R9  银行存款
    "bank_institution",        # R10 其中：机构类
    "bank_finance",            # R11 其中：理财类
    "bank_other",              # R12 其中：其他类
    "digital_currency",        # R13 数字货币
    "other_monetary",          # R14 其他货币资金
    "total",                   # R15 合计
    "restricted_deposit",      # R17 其中：受限资金-定期存款
    "restricted_margin",       # R18 受限资金-保证金
    "restricted_frozen",       # R19 受限资金-冻结资金
    "restricted_pledge",       # R20 受限资金-质押存款
    "restricted_other",        # R21 受限资金-其他
    "restricted_subtotal",     # R22 受限小计
    "unrestricted_deposit",    # R23 非受限-活期存款
    "unrestricted_current",    # R24 非受限-库存现金
    "unrestricted_digital",    # R25 非受限-数字货币
    "unrestricted_other_mf",   # R26 非受限-其他货币资金
    "unrestricted_other",      # R27 非受限-其他
    "unrestricted_subtotal",   # R28 非受限小计
    "accrued_interest",        # R29 应计利息（🔴 跨册取数）
)

#: 跨 sheet 聚合键（从 E1-3 分组小计取数）。
CROSS_SHEET_AGGREGATION_KEYS_E101: Final[tuple[str, ...]] = (
    "E1-bank-detail-institution-opening-unaudited",
    "E1-bank-detail-institution-total-unaudited",
    "E1-bank-detail-finance-opening-unaudited",
    "E1-bank-detail-finance-total-unaudited",
    "E1-bank-detail-other-opening-unaudited",
    "E1-bank-detail-other-total-unaudited",
)

#: 跨册取数键（属第 3 册，本 entry 范围外）。
CROSS_VOLUME_KEYS_E101: Final[tuple[str, ...]] = (
    "E1-accrued-interest-rows",
)

#: ─── 受管字段（审定表列 A-J）──────────────────────────────────────────────
#: 🔴 E1-1 的 B-H 绝大多数数据格是**跨 sheet 公式**或**计算公式**。
#:    真正可编辑的极少：各项 reason_analysis（J 列）和极少数手工录入格。
#:    field_specs 的 mode 声明列级默认。
_FIELD_SPECS_E101: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "期初未审数", f"B{5}"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "期初调整", f"B{5}"),
    ("prior_audited", "D", "formula", "amount", "priorAudited", "期初审定数", f"B{5}"),
    ("current_unadjusted", "E", "formula", "amount", "currentUnadjusted", "期末未审数", f"E{5}"),
    ("current_aje", "F", "formula", "amount", "currentAje", "期末调整", f"E{5}"),
    ("current_audited", "G", "formula", "amount", "currentAudited", "期末审定数", f"E{5}"),
    ("change_amount", "H", "formula", "amount", "changeAmount", "变动额", f"H{5}"),
    ("change_rate", "I", "formula", "ratio", "changeRate", "变动率", f"H{5}"),
    ("reason_analysis", "J", "editable", "text", "reasonAnalysis", "原因分析", ""),
)


#: ─── 逐格 mask（193 公式 / 密度 41%）═══════════════════════════════════
#: 🔴 实测所有公式格的完整清单。E1-1 密度比 D1-1 高得多（193 vs ~60），
#:    且「同列有公式行也有非公式行」⇒ 必须逐格而非列向区间。
def _build_cell_mask() -> tuple[str, ...]:
    """构建逐格 formula mask（大写 A1 形态）。"""
    cells: list[str] = []

    # 审定列 D/G（= B+C / E+F）—— 全部数据行 + 合计行
    for col in ("D", "G"):
        for row in range(8, 32):
            cells.append(f"{col}{row}")

    # 变动额/变动率 H/I —— 全部有数据的行
    for col in ("H", "I"):
        for row in range(8, 32):
            cells.append(f"{col}{row}")

    # 合计行 R15 的 B-G（SUM 公式）
    for col in ("B", "C", "E", "F"):
        cells.append(f"{col}{15}")

    # 受限小计 R22 / 非受限小计 R28 的 B-G
    for subtotal_row in (22, 28):
        for col in ("B", "C", "D", "E", "F", "G"):
            cells.append(f"{col}{subtotal_row}")

    # 试算平衡表数 R30 —— 用于 TB 核对
    for col in ("B", "E"):
        cells.append(f"{col}{30}")

    # 差异行 R31
    for col in ("B", "E"):
        cells.append(f"{col}{31}")

    # 跨 sheet 公式（B/E 的银行存款行 R9 引用 E1-3 分组小计）
    for col in ("B", "E"):
        for row in (9, 10, 11, 12):
            cells.append(f"{col}{row}")

    return tuple(sorted(set(cells)))


_CELL_MASK_E101: Final[tuple[str, ...]] = _build_cell_mask()


#: 字段值来源声明（供四态覆盖状态机用）。
#: 🔴 **派生格不可由 OO 侧直接写**（需求 4.5）：否则 OO 回写覆盖聚合结果。
_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.cross_sheet,
    "prior_aje": AdjudicationValueSource.cross_sheet,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.cross_sheet,
    "current_aje": AdjudicationValueSource.cross_sheet,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
    "reason_analysis": AdjudicationValueSource.manual,
}


SPEC_E101: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_E101,
    sheet_key=SHEET_KEY_E101,
    template_id=TEMPLATE_ID_E101,
    header_rows=(5, 6, 7),
    sections=(),  # 🔴 slot_driven 无 section（平铺槽位模型）
    row_mode=AdjudicationRowMode.slot_driven,
    total_row=15,        # 合计行
    tb_row=30,           # 试算平衡表数
    diff_row=31,         # 差异数
    footer_marker="合计",
    store_item_id="",    # per-cell 锚点，无单一 store item
    row_identity_key="", # slot_driven 无行身份
    per_cell_key_template=f"{E1_ADJ_PREFIX}{{slot}}-{{field}}",
    field_specs=_FIELD_SPECS_E101,
    cell_mask=_CELL_MASK_E101,
    value_sources=_VALUE_SOURCES,
    slot_order=E1_SLOT_ORDER,
    html_only_item_ids=(),
)
