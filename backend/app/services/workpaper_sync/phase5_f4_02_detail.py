# -*- coding: utf-8 -*-
"""F4-2「明细表」—— sheet 层薄声明。

spec: f4-sync-coverage-and-first-canary · Task 15 · Requirements 3.1~3.5
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R9（组）/ R10（叶子）**：27 列 A~AA。
数据区 **R11~R31**（21 行）· footer **R32** 合计。

公式列 4 个：H(=E+F+G) / K(=E+J-I) / M(=K+L) / T(=M+R+S)。
UUID **AB**（non_null=0）。

═══ 账龄（THREE_YEAR 4 段，动态枚举）═══

模板物理列**固定 4 段**（N~Q 未审 / U~X 审定），对应 THREE_YEAR 预设。
前端 `useAgingConfig` 支持三种预设：THREE_YEAR(4段) / FIVE_YEAR(6段) / CUSTOM。
F4 的默认预设是 **THREE_YEAR**（`DEFAULT_SUBJECT_PRESETS.F4 = 'THREE_YEAR'`）。

🔴 **仅 THREE_YEAR 启用**（裁决 F4-P8，照 F1-2 先例）：
当项目配置为 FIVE_YEAR(6段) 或 CUSTOM 时，4 列模板物理列容纳不下 ⇒
整表降级 legacy + 中文提示。

两个 nested 账龄组：
| 组 | 组标题格 | 列 | json_prefix | 段 |
|---|---|---|---|---|
| 未审账龄 | N9 | N/O/P/Q | agingUnadjusted | within1/y1to2/y2to3/over3 |
| 审定账龄 | U9 | U/V/W/X | agingAudited | within1/y1to2/y2to3/over3 |

═══ 前端已对齐 ═══

F4-P7：`useF4Detail.ts:301` 注释明确标注已对齐模板口径，预期直接绿（作 F1-2 参照）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F402",
    "MANAGED_SHEET_F402",
    "STORE_ITEM_ID_F402",
]

MANAGED_SHEET_F402: Final[str] = "明细表F4-2"
TEMPLATE_ID_F402: Final[str] = "F42"
SHEET_KEY_F402: Final[str] = "f42-managed"
ROWS_TABLE_KEY_F402: Final[str] = "payable_detail_rows"
STORE_ITEM_ID_F402: Final[str] = "F4-2-rows"

ROW_IDENTITY_STORE_KEY_F402: Final[str] = "rowId"

HEADER_GROUP_ROW_F402: Final[int] = 9
HEADER_LEAF_ROW_F402: Final[int] = 10
FIRST_DATA_ROW_F402: Final[int] = 11
LAST_DATA_ROW_F402: Final[int] = 31
FOOTER_ROW_F402: Final[int] = 32
FOOTER_MARKER_F402: Final[str] = "合计"
MANAGED_LAST_COL_F402: Final[str] = "AA"
UUID_COL_F402: Final[str] = "AB"

#: 账龄段定义（THREE_YEAR 4 段，与 D3/D7/F1-2 同型）。
#: 🔴 段 key 与 `useAgingConfig.PRESET_SEGMENTS.THREE_YEAR` 逐值一致。
#: 模板 R10 叶子标签含全角字符（实测：N10「1年以下」O10「1～2年」P10「２～3年」Q10「3年以上」）。
_AGING_SEGMENTS_F402 = (
    ("within1", "1年以下"),
    ("y1to2", "1～2年"),
    ("y2to3", "２～3年"),
    ("over3", "3年以上"),
)

#: 🔴 仅 THREE_YEAR 启用；非 THREE_YEAR 时受管关闭（照 F1-2 先例 · 裁决 F4-P8）。
F402_AGING_DOWNGRADE_MESSAGE: Final[str] = (
    "当前项目的账龄配置非 THREE_YEAR（4 段），模板物理列（N~Q / U~X）容纳不下 ⇒ "
    "整表降级 legacy。请确认项目账龄设置或在 HTML 模式下编辑。"
)

#: 15 个非账龄 editable 字段（A~AA 减去公式列 H/K/M/T 和账龄列 N~Q/U~X）。
FIELD_SPECS_F402: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("creditor_name", "A", "editable", "text", "creditorName", "债权人名称", ""),
    ("company_code", "B", "editable", "text", "companyCode", "公司代码", ""),
    ("related_party_type", "C", "editable", "text", "relatedPartyType", "关联方类型", ""),
    ("payment_nature", "D", "editable", "text", "paymentNature", "款项性质", ""),
    ("opening_unadjusted", "E", "editable", "amount", "openingUnadjusted", "期初未审余额", ""),
    ("opening_aje", "F", "editable", "amount", "openingAje", "期初账项调整", ""),
    ("opening_rje", "G", "editable", "amount", "openingRje", "期初重分类调整", ""),
    # H 公式（期初审定）
    ("debit_occurrence", "I", "editable", "amount", "debitOccurrence", "借方发生", ""),
    ("credit_occurrence", "J", "editable", "amount", "creditOccurrence", "贷方发生", ""),
    # K 公式（期末余额）
    ("reclass_adjustment", "L", "editable", "amount", "reclassAdjustment", "被审计单位重分类调整", ""),
    # M 公式（期末未审）
    # N~Q 未审账龄（aging_groups）
    ("current_aje", "R", "editable", "amount", "currentAje", "账项调整", ""),
    ("current_rje", "S", "editable", "amount", "currentRje", "重分类调整", ""),
    # T 公式（审定数）
    # U~X 审定账龄（aging_groups）
    ("is_confirmed", "Y", "editable", "text", "isConfirmed", "是否函证", ""),
    ("post_period_payment", "Z", "editable", "amount", "postPeriodPayment", "期后付款", ""),
    ("remark", "AA", "editable", "text", "remark", "备注", ""),
)

#: 两个 nested 账龄组（照 F1-2 / D3 先例翻成 AgingGroupSpec）。
_AGING_GROUPS_F402: Final[tuple[AgingGroupSpec, ...]] = (
    AgingGroupSpec(
        json_prefix="agingUnadjusted",
        group_header_cell=f"N{HEADER_GROUP_ROW_F402}",
        segments=tuple(
            (seg_key, col)
            for (seg_key, _), col in zip(_AGING_SEGMENTS_F402, ("N", "O", "P", "Q"))
        ),
        leaf_labels=tuple(label for _, label in _AGING_SEGMENTS_F402),
    ),
    AgingGroupSpec(
        json_prefix="agingAudited",
        group_header_cell=f"U{HEADER_GROUP_ROW_F402}",
        segments=tuple(
            (seg_key, col)
            for (seg_key, _), col in zip(_AGING_SEGMENTS_F402, ("U", "V", "W", "X"))
        ),
        leaf_labels=tuple(label for _, label in _AGING_SEGMENTS_F402),
    ),
)

SPEC_F402: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F402,
    sheet_key=SHEET_KEY_F402,
    table_key=ROWS_TABLE_KEY_F402,
    template_id=TEMPLATE_ID_F402,
    table_name=f"GT_{TEMPLATE_ID_F402}_ROWS",
    uuid_col=UUID_COL_F402,
    first_data_row=FIRST_DATA_ROW_F402,
    last_data_row=LAST_DATA_ROW_F402,
    footer_row=FOOTER_ROW_F402,
    header_group_row=HEADER_GROUP_ROW_F402,
    header_leaf_row=HEADER_LEAF_ROW_F402,
    store_item_id=STORE_ITEM_ID_F402,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F402,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F402,
    formula_columns=("H", "K", "M", "T"),
    formula_templates={
        "H": "=E{r}+F{r}+G{r}",
        "K": "=E{r}+J{r}-I{r}",
        "M": "=K{r}+L{r}",
        "T": "=M{r}+R{r}+S{r}",
    },
    footer_marker=FOOTER_MARKER_F402,
    footer_carries_total_formula=True,
    # ── 账龄（nested，THREE_YEAR 4 段 × 2 组）──
    aging_layout=AgingLayout.nested,
    aging_groups=_AGING_GROUPS_F402,
    error_label="F4-2 应付账款明细表",
)
