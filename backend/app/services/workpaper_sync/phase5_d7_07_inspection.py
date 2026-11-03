# -*- coding: utf-8 -*-
"""D7-7「合同负债检查表」—— 双区声明（区①本期变动 / 区②期后结转）。

spec: d567-sync-coverage-via-row-table-engine · Task 16 · Requirements 3.4
几何复核：spec oo-writeback-template-parity-closure R3 批 B2（openpyxl 逐格，2026-10-28）

═══ 几何（与 D3-7 / D6-6 同型）═══

区①「（1）本期增减变动检查」：两级表头 R16（组）/ R17（叶），数据 R18-R30，footer R31「合计」（G/H 两列 SUM）。
  A 客户名称 · B..H「记账凭证」组（日期 / 凭证编号 / 业务内容 / 对方科目 / 对方明细科目 / 借方金额 / 贷方金额）·
  I 支持性文件 · J..N「核对内容」1~5 · O 索引号 · P 是否异常 · Q 备注说明（A/I/O/P/Q 跨两行合并）。
区②「（2）期后结转检查」：两级表头 R33 / R34，数据 R35-R39，footer R40（只 G 一列 SUM）。
  B..G「记账凭证」组只到 G = **借方金额**（合同负债期后结转是借方）；H:I 合并为「支持性文件」（值写主列 H）。

🔴 原声明按另一种列序写（A..R：F 借方 / G 贷方 / H 支持性文件 / I..O 七个检查 / P 索引 / Q 异常 / R 备注），
   与模板逐列错位；区② 照抄区① 的列，而模板区② 只有借方一列金额；单级 `header_row` 让 R17 叶子表头落进
   数据区。D6-6 区② 同类错位一并改（见该模块）。

═══ json 键 = 前端 `useD7VoucherCheck.VoucherCheckRow` ═══

核对内容 = `checkItems[0..4]`（布尔数组）；是否异常 = `isAbnormal`（布尔）。OO 侧新增行先建 5 项数组，
未勾 / 非异常在 Excel 里留空（不写 FALSE）。区② 金额 = `debitAmount`（前端随本批由贷方改为借方，旧数据的
`creditAmount` 载入时迁移）。
🔴 store keys = D7-7-period-rows / D7-7-post-rows（不是 D7-7-rows 聚合键！）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D707_PERIOD", "SPEC_D707_POST", "MANAGED_SHEET_D707"]

MANAGED_SHEET_D707: Final[str] = "合同负债检查表D7-7"
SHEET_KEY_D707: Final[str] = "d77-managed"

TEMPLATE_ID_D707_PERIOD: Final[str] = "D77PERIOD"
STORE_ITEM_ID_D707_PERIOD: Final[str] = "D7-7-period-rows"
TEMPLATE_ID_D707_POST: Final[str] = "D77POST"
STORE_ITEM_ID_D707_POST: Final[str] = "D7-7-post-rows"

_ARRAYS: Final[tuple[tuple[str, int, object], ...]] = (("checkItems", 5, False),)


def _checks(group_row: int) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """核对内容 J..N（组标题「核对内容」，叶子 1~5）= 前端 checkItems[0..4]。"""
    return tuple(
        (f"check{i + 1}", chr(ord("J") + i), "editable", "boolean", f"checkItems/{i}", f"核对内容{i + 1}", f"J{group_row}")
        for i in range(5)
    )


_TAIL: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
    ("is_abnormal", "P", "editable", "boolean", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注说明", ""),
)

#: 区① 17 列（A..Q），组标题行 R16。
FIELD_SPECS_D707_PERIOD: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("date", "B", "editable", "text", "date", "日期", "B16"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", "B16"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", "B16"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", "B16"),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细科目", "B16"),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", "B16"),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额", "B16"),
    ("support_doc", "I", "editable", "text", "supportDocs", "支持性文件", ""),
    *_checks(16),
    *_TAIL,
)

#: 区② 16 列（A..H、J..Q；H:I 合并的「支持性文件」值写主列 H，I 不声明），组标题行 R33。
FIELD_SPECS_D707_POST: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("date", "B", "editable", "text", "date", "日期", "B33"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", "B33"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", "B33"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", "B33"),
    ("counter_detail", "F", "editable", "text", "counterDetail", "对方明细科目", "B33"),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", "B33"),
    ("support_doc", "H", "editable", "text", "supportDocs", "支持性文件", ""),
    *_checks(33),
    *_TAIL,
)

SPEC_D707_PERIOD: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D707,
    sheet_key=SHEET_KEY_D707,
    table_key="inspection_period_rows",
    template_id=TEMPLATE_ID_D707_PERIOD,
    table_name=f"GT_{TEMPLATE_ID_D707_PERIOD}_ROWS",
    uuid_col="S",  # 受管列止于 Q；与区② T 各用一列
    first_data_row=18,
    last_data_row=30,
    footer_row=31,
    header_group_row=16,
    header_leaf_row=17,
    store_item_id=STORE_ITEM_ID_D707_PERIOD,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D707_PERIOD,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合计",
    error_label="D7-7 检查表 区①本期",
    row_array_defaults=_ARRAYS,
    boolean_unchecked_as_blank=True,
)

SPEC_D707_POST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D707,
    sheet_key=SHEET_KEY_D707,
    table_key="inspection_post_rows",
    template_id=TEMPLATE_ID_D707_POST,
    table_name=f"GT_{TEMPLATE_ID_D707_POST}_ROWS",
    uuid_col="T",  # 🔴 不同区不同 UUID 列
    first_data_row=35,
    last_data_row=39,
    footer_row=40,
    header_group_row=33,
    header_leaf_row=34,
    store_item_id=STORE_ITEM_ID_D707_POST,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D707_POST,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合计",
    error_label="D7-7 检查表 区②期后",
    row_array_defaults=_ARRAYS,
    boolean_unchecked_as_blank=True,
)
