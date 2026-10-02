# -*- coding: utf-8 -*-
"""L3 长期借款 —— 受管 `长期借款检查表L3-9` 的身份/几何/字段声明。

spec: l-cycle-true-adapter-registration · Task 12（L3）

选型现算：L3-9 是唯一同时具备「单连续输入区 + 前端/模板字段 16/16 对齐 + 数据区公式 0 +
已有稳定 rowId」的表。L3-1 是 87 公式的派生审定表；L3-2 虽与 L1 模板同构但模板有效列
31、前端仅 17 字段且分组复杂；L3-7 有 4 个 #REF!；其余检查表字段重合更低。

几何：两级表头 r10/r11，数据 r12~r20，footer A21「合计」，R22/R23 是引用 L3-2 的派生
检查比例（明确不受管），有效列 A..P；物理 max_column=34(AH) ⇒ UUID 列 AI。数据区零公式，
formula_mask 为空。册内 38 definedName（31 broken）/40 裸 IF/4 个 #REF!，但受管表裸 IF 0。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as _fields

PHASE5_WAVE: Final[str] = "l_cycle_long_term_loans"
ENTRY_ID: Final[str] = "xlsx/gt-l3-long-term-loans"
ADAPTER_ID: Final[str] = "l3.long_term_loans"
WP_CODES: Final[frozenset[str]] = frozenset({"L3L"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L3 长期借款.xlsx"
TEMPLATE_SHA256: Final[str] = "ca0ac1e878fde45f8aa91f5ecae4fc685b82c83d5ec765a8094ef263999e2b60"
MANAGED_SHEET: Final[str] = "长期借款检查表L3-9"
TEMPLATE_ID: Final[str] = "L39"
SHEET_KEY: Final[str] = "l39-managed"
ROWS_TABLE_KEY: Final[str] = "long_term_loan_voucher_rows"
TABLE_NAME: Final[str] = "GT_L39_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 20
FOOTER_ROW: Final[int] = 21
MANAGED_LAST_COL: Final[str] = "P"
UUID_COL: Final[str] = "AI"
FOOTER_MARKER: Final[str] = "合计"
STORE_ITEM_ID: Final[str] = "L3-L3-9-voucher-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()

#: 16 个字段，模板 A..P 与 `L3VoucherCheckRow` 业务字段逐一对应；数据区无公式。
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

SPEC_L39: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID, table_name=TABLE_NAME, uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW, footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW, header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7, formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES, aging_layout=None, aging_groups=(),
    footer_marker=FOOTER_MARKER, footer_carries_total_formula=True,
    footer_search_column="A", error_label="L3-9 长期借款检查表",
    ghost_row_anchor_index=1,  # voucherNo：真业务文本；date 可能合法为空
)
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _fields(SPEC_L39)
)
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L39.formula_mask

_HTML_STORE_NOTE: Final[str] = (
    "整张 L3-9 凭证检查表存成 `L3-L3-9-voucher-rows` 的 remark JSON 数组；每行已有稳定 rowId，"
    "增删改均按 rowId。2026-10-01 只把私有 Date.now+Math.random 生成器换成平台共享 "
    "newRowIdentity('l39vc')，已有 rowId 优先不重铸。criteria/note/conclusion 三个 sibling item "
    "本轮不受管、不预登记。真库本 item 0 行，零迁移负担。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 L3 长期借款.xlsx（14 sheet，sha ca0ac1e8…）：L3-9 两级表头 "
    "r10/r11、数据 r12~r20、footer A21、A..P 16 字段与前端业务字段 16/16 对齐、数据区公式 0；"
    "物理 max_column=AH 故 UUID=AI；manifest 幻影码 L3L finder 零命中。"
)
