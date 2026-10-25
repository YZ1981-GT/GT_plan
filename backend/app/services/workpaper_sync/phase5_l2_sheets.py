# -*- coding: utf-8 -*-
"""L2 应付利息 —— 受管 `应付利息检查表L2-4` 的身份/几何/字段声明。

spec: l-cycle-true-adapter-registration · Task 12（L2，最后一条）

选型现算：L2-4 是 L3-9 的孪生表（凭证级检查表）—— 单连续输入区、前端 `VoucherCheckRow`
16 字段与模板 A..P 16/16 对齐、数据区 r12~r23 零公式、已有稳定 `rowId`。排除：审定表
L2-1（派生汇总，SUMIF/加总）、明细表 L2-2（数据源头但前端字段分组复杂且被 L2-4 的
本期发生额跨 sheet 引用，改它会连带检查比例链）、调整分录 L2-3（与调整分录模块重复）。

几何（openpyxl 逐格实测，sha 8a747c99…）：两级表头 r10/r11，数据 r12~r23（12 行，比
L3-9 多 3 行），footer A24「合计」，r25/r26 是引用 L2-2 的本期发生额/检查比例派生行
（受管区截止 r23、footer r24，派生行声明只读）。有效列 A..P(16)，物理 max_column=S(19)
⇒ UUID 列 T。数据区零公式 ⇒ formula_mask 空。册内 0 definedName / 0 external rels /
112 裸 IF（受管表 L2-4 零命中，per-file 中性化仍挂）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as _fields

PHASE5_WAVE: Final[str] = "l_cycle_interest_payable"
ENTRY_ID: Final[str] = "xlsx/gt-l2-interest-payable"
ADAPTER_ID: Final[str] = "l2.interest_payable"
WP_CODES: Final[frozenset[str]] = frozenset({"L2I"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L2 应付利息.xlsx"
TEMPLATE_SHA256: Final[str] = "8a747c9931f5a5e0f3a89d243b1eb6aea13ce9b16743664e7ce1a3d4678c989a"
MANAGED_SHEET: Final[str] = "应付利息检查表L2-4"
TEMPLATE_ID: Final[str] = "L24"
SHEET_KEY: Final[str] = "l24-managed"
ROWS_TABLE_KEY: Final[str] = "interest_payable_voucher_rows"
TABLE_NAME: Final[str] = "GT_L24_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 23
FOOTER_ROW: Final[int] = 24
MANAGED_LAST_COL: Final[str] = "P"
UUID_COL: Final[str] = "T"
FOOTER_MARKER: Final[str] = "合计"
STORE_ITEM_ID: Final[str] = "L2-L2-4-voucher-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()

#: 16 字段，模板 A..P 与 `VoucherCheckRow` 业务字段逐一对应；数据区无公式。
MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("date", "A", "editable", "date", "date", "日期", ""),
    ("voucher_no", "B", "editable", "text", "voucherNo", "凭证编号", ""),
    ("business_content", "C", "editable", "text", "businessContent", "业务内容", ""),
    ("counter_account", "D", "editable", "text", "counterAccount", "对方科目", ""),
    ("counter_sub_account", "E", "editable", "text", "counterSubAccount", "对方明细科目", ""),
    ("debit_amount", "F", "editable", "amount", "debitAmount", "借方金额", ""),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", ""),
    ("supporting_doc", "H", "editable", "text", "supportingDoc", "支持性文件", ""),
    ("check_1", "I", "editable", "boolean", "check1", "核对内容①", "I10"),
    ("check_2", "J", "editable", "boolean", "check2", "核对内容②", "I10"),
    ("check_3", "K", "editable", "boolean", "check3", "核对内容③", "I10"),
    ("check_4", "L", "editable", "boolean", "check4", "核对内容④", "I10"),
    ("check_5", "M", "editable", "boolean", "check5", "核对内容⑤", "I10"),
    ("index_no", "N", "editable", "text", "indexNo", "索引号", ""),
    ("abnormal", "O", "editable", "boolean", "abnormal", "是否异常", ""),
    ("remark", "P", "editable", "text", "remark", "备注", ""),
)
FORMULA_TEMPLATES: Final[dict[str, str]] = {}
FORMULA_COLUMNS: Final[tuple[str, ...]] = ()

SPEC_L24: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID, table_name=TABLE_NAME, uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW, footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW, header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7, formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES, aging_layout=None, aging_groups=(),
    footer_marker=FOOTER_MARKER, footer_carries_total_formula=True,
    footer_search_column="A", error_label="L2-4 应付利息检查表",
    ghost_row_anchor_index=1,  # voucherNo：真业务文本；date 可能合法为空
)
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _fields(SPEC_L24)
)
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L24.formula_mask

_HTML_STORE_NOTE: Final[str] = (
    "整张 L2-4 应付利息检查表存成 `L2-L2-4-voucher-rows` 的 remark JSON 数组；每行已有稳定 "
    "rowId，增删改均按 rowId。2026-10-01 只把私有 Date.now+Math.random 生成器换成平台共享 "
    "newRowIdentity('l24vc')，已有 rowId 优先不重铸。criteria/note/conclusion 三个 sibling "
    "item 本轮不受管、不预登记。真库本 item 0 行，零迁移负担。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 L2 应付利息.xlsx（8 sheet，sha 8a747c99…）：L2-4 两级表头 "
    "r10/r11、数据 r12~r23、footer A24、A..P 16 字段与前端 VoucherCheckRow 16/16 对齐、数据区"
    "公式 0；物理 max_column=S 故 UUID=T；r25/r26 是引用 L2-2 的派生行声明只读；"
    "manifest 幻影码 L2I finder 零命中。"
)
