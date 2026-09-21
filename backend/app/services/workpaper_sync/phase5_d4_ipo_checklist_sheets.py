# -*- coding: utf-8 -*-
"""D4-25/26/27/28 IPO 检查表 —— 追加受管 sheet（同 adapter `d4.revenue_detail`，同 workbook）。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · 后端 store-projection provider

═══ workbook 裁决 ═══

四张 IPO 检查表前端同步宿主全部 `parent_duplicate` / `independentEntry:false`，父 entry =
`xlsx/gt-d4-operating-revenue`（capability=bidirectional），权威 workbook = ``D/D4 收入底稿.xlsx``
（与 D4-2/3/5/21~24 同一 blob / 同一 TEMPLATE_SHA256）。四张 IPO sheet 结构与
`D4-22至D4-32...IPO...xlsx` 字节级一致（B1 已核定）。故本模块把它们作为**追加受管 sheet**
挂进同一 entry，而非新建独立 entry。

═══ 行形态（列规格真源 = 前端 ipoChecklistSchema.SHEET_SPECS，英文 key 逐列对齐）═══

* **D4-25 经销商检查**（动态行，单级表头 row11）：13 列 A–M，无内部公式；数据 12–21，
  边界 A23「三、审计说明：」。UUID 用 N（数据止 M）。
* **D4-26 境外销售收入检查**（动态行，两级表头 row11/12）：19 列 = 14 主(A–N) + 5 子(O–S)。
  `占同类交易比例(F)`/`差异(M)` 是前端表内计算，但 OO 侧无内嵌公式 → 全列受管可编辑。
  UUID 用 T（数据止 S）。
* **D4-27 识别未披露的关联方**（动态行，单级表头 row14）：18 列 A–R，10 个身份属性列为勾选
  （值 1/空），`总计(M)` 源模板内嵌 `=SUM(C15:L15)` → **入 FORMULA_MASK 不入契约**。UUID 用 S。
* **D4-28 客户信息核查清单**（动态行，两级表头 row12/13）：15 列 = 9 主(A–I) + 5 子(J–N) + 索引号(O)。
  三个占比列(E/G/I)前端表内计算，OO 侧无内嵌公式 → 受管可编辑。UUID 用 P。

行身份 = `rowId`（前端 ChecklistRow 的稳定 key，禁下标兜底）。json_path = 前端列 key（camelCase）。

🔴 **`LAST_DATA_ROW_*` 语义**：仅记源模板出厂时的**占位末行**（如 D4-25=21，共 12..21 十行占位），
用于 `mapping_digest` 冻结与守卫复算，**不是运行时写入截断点**。四张表是动态行，真实行数超占位时
instrumentation 插行并把 `FOOTER_ROW_*` 结论区整体下移；运行时唯一硬上限是 `_ROW_LIMIT`(500)。
把 `last_data_row` 误当截断点会吞掉第 11 行起的数据 —— store 层「超占位不截断」由
`tests/workpaper_sync/test_d4_ipo_checklist_store_roundtrip.py::test_rows_beyond_template_placeholder_are_not_truncated` 守护。

四张表的 mapping_digest 冻结于本模块（`gen` 由 `_digest(mapping_digest_payload_*)` 现算）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.json_path import (
    JsonPathMissingSegmentError,
    resolve_json_path,
    set_json_path,
)

# 与 phase5_d4_revenue_detail / phase5_d4_ipo_related_sheets 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"


class D4ChecklistDigestError(ValueError):
    """IPO checklist sheet mapping_digest 漂移（与列规格真源不一致）。"""


def _digest(payload: dict) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _contract_fields_digest_shape(fields) -> list[dict]:
    return [
        {"col": c, "column_key": k, "header": h, "json_path": jp, "mode": m}
        for (k, c, m, _vt, jp, h) in fields
    ]


def _resolve_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


def _checkbox_json_paths(sheet_code: str) -> frozenset[str]:
    """该 sheet 里 value_type=boolean 的列的 json_path 集合（勾选框列）。

    唯一真源 = 字段元组第 4 位 `"boolean"`，不另维护列表（防两处漂移）。
    """
    return frozenset(
        spec[4] for spec in _SHEETS[sheet_code]["fields"] if spec[3] == "boolean"
    )


def _coerce_checkbox_to_store(value: Any) -> Any:
    """HTML store（JS 布尔）→ 投影值：勾选 `True`，未勾（False/空/0）→ `None`。

    🔴 未勾映射为 `None` 而不是 `False`：boolean_literal 落盘时 `None`→空格、`False`→`<v>0</v>`，
    源模板口径是「勾选=1 / 未勾=空白」，所以未勾必须是 `None`（否则 Excel 里满屏 0）。
    """
    if value is True or value == 1 or (isinstance(value, str) and value.strip() in ("1", "true", "True", "是", "Y", "√")):
        return True
    return None


def _coerce_checkbox_from_projection(value: Any) -> Any:
    """投影值（真 bool / 未勾 None）→ HTML store：`None`/未勾 → `False`（前端 el-checkbox 要严格布尔）。"""
    return value is True


# ═══════════════════════════════════════════════════════════════════════════
# D4-25 经销商检查（动态行，单级表头）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D425: Final[str] = "经销商检查D4-25"
TEMPLATE_ID_D425: Final[str] = "D425"
SHEET_KEY_D425: Final[str] = "d4-25-managed"  # 前端 D4_25_SHEET_KEY 锁死 d4-25-managed（带连字符）
ROWS_TABLE_KEY_D425: Final[str] = "dealer_check_rows"
STORE_ITEM_ID_D425: Final[str] = "D4-25-rows"
ROW_IDENTITY_STORE_KEY_D425: Final[str] = "rowId"

HEADER_ROW_D425: Final[int] = 11
FIRST_DATA_ROW_D425: Final[int] = 12
LAST_DATA_ROW_D425: Final[int] = 21
FOOTER_ROW_D425: Final[int] = 23
FOOTER_MARKER_D425: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D425: Final[str] = "M"
UUID_COL_D425: Final[str] = "N"
TABLE_NAME_D425: Final[str] = f"GT_{TEMPLATE_ID_D425}_ROWS"

#: 13 列（json_path = 前端 ipoChecklistSchema D4-25 列 key）。
MANAGED_FIELD_SPECS_D425: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    # 🔴 value_type 对齐前端 ipoChecklistSchema「唯一结构真源」：seq=number→amount、
    #    proportion=percent→ratio。此前误标 text，store 存 int（seq:1/proportion:1）在
    #    materialize `normalize_value(1,'text')` 抛 EditableCellWriteError，打挂整册 apply。
    #    amount/ratio 经 _DECIMAL_TYPES 接受 int→Decimal，往返正确。
    ("seq", "A", "editable", "amount", "seq", "序号"),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),
    ("dealer", "C", "editable", "text", "dealer", "经销商"),
    ("sales_qty", "D", "editable", "amount", "salesQty", "本期销售数量"),
    ("sales_amount", "E", "editable", "amount", "salesAmount", "本期销售金额"),
    ("proportion", "F", "editable", "ratio", "proportion", "占同类交易比例"),
    ("ar_balance", "G", "editable", "amount", "arBalance", "期末应收账款余额"),
    ("is_related", "H", "editable", "text", "isRelated", "是否关联方"),
    ("entity_type", "I", "editable", "text", "entityType", "个人/企业"),
    ("expense_bearer", "J", "editable", "text", "expenseBearer", "销售费用承担方式"),
    ("subsidy", "K", "editable", "text", "subsidy", "补贴或返利"),
    ("terminal_sales_amount", "L", "editable", "amount", "terminalSalesAmount", "终端销售金额"),
    ("remark", "M", "editable", "text", "remark", "备注"),
)
FORMULA_MASK_D425: Final[tuple[str, ...]] = ()
EXPECTED_MAPPING_DIGEST_D425: Final[str] = (
    "ba47b19e9fa30e8c5060289366ccab31e3d782435bdd86715843add51c30fdc5"
)


# ═══════════════════════════════════════════════════════════════════════════
# D4-26 境外销售收入检查（动态行，两级表头 14 主 + 5 子）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D426: Final[str] = "境外销售收入检查D4-26"
TEMPLATE_ID_D426: Final[str] = "D426"
SHEET_KEY_D426: Final[str] = "d4-26-managed"  # 前端 D4_26_SHEET_KEY 锁死 d4-26-managed
ROWS_TABLE_KEY_D426: Final[str] = "overseas_sales_rows"
STORE_ITEM_ID_D426: Final[str] = "D4-26-rows"
ROW_IDENTITY_STORE_KEY_D426: Final[str] = "rowId"

HEADER_ROWS_D426: Final[tuple[int, int]] = (11, 12)
FIRST_DATA_ROW_D426: Final[int] = 13
LAST_DATA_ROW_D426: Final[int] = 22
#: 源模板实测 A30「三、审计说明：」（非 23；23 是误抄 D4-25 行号）。
FOOTER_ROW_D426: Final[int] = 30
FOOTER_MARKER_D426: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D426: Final[str] = "S"
UUID_COL_D426: Final[str] = "T"
TABLE_NAME_D426: Final[str] = f"GT_{TEMPLATE_ID_D426}_ROWS"

#: 19 列 = 14 主(A–N) + 5 子(O–S)。二级列（核查程序勾选）值 1/空，value_type=text。
MANAGED_FIELD_SPECS_D426: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称"),
    ("country", "B", "editable", "text", "country", "所在国家/地区"),
    ("product_type", "C", "editable", "text", "productType", "产品种类"),
    ("business_mode", "D", "editable", "text", "businessMode", "业务模式"),
    ("sales_amount", "E", "editable", "amount", "salesAmount", "本期销售金额"),
    # value_type 对齐前端 percent → ratio（此前误标 text）。
    ("proportion", "F", "editable", "ratio", "proportion", "占同类交易比例"),
    ("trade_mode", "G", "editable", "text", "tradeMode", "贸易模式"),
    ("trade_terms", "H", "editable", "text", "tradeTerms", "主要贸易条款"),
    ("settlement_mode", "I", "editable", "text", "settlementMode", "出口结算模式"),
    ("has_third_party_payment", "J", "editable", "text", "hasThirdPartyPayment", "是否存在第三方回款"),
    ("third_party_reason", "K", "editable", "text", "thirdPartyReason", "第三方回款原因"),
    ("confirmed_sales_amount", "L", "editable", "amount", "confirmedSalesAmount", "核查程序确认的销售金额"),
    ("difference", "M", "editable", "amount", "difference", "差异"),
    ("difference_reason", "N", "editable", "text", "differenceReason", "差异原因分析"),
    # 5 个核查程序勾选列：value_type=boolean（勾选落 OOXML 真布尔 <v>1</v>，未勾空格）。
    ("check_field_visit", "O", "editable", "boolean", "checkFieldVisit", "实地走访"),
    ("check_trans_confirm", "P", "editable", "boolean", "checkTransConfirm", "交易函证"),
    ("check_customs_confirm", "Q", "editable", "boolean", "checkCustomsConfirm", "海关函证"),
    ("check_declaration", "R", "editable", "boolean", "checkDeclaration", "核对报关单"),
    ("check_eport_data", "S", "editable", "boolean", "checkEportData", "电子口岸数据查询"),
)
FORMULA_MASK_D426: Final[tuple[str, ...]] = ()
EXPECTED_MAPPING_DIGEST_D426: Final[str] = (
    "2e8b792957f42df0f9a6209779916f5446259f08344cb97e10a44e3b4be7055a"
)


# ═══════════════════════════════════════════════════════════════════════════
# D4-27 识别未披露的关联方（动态行，单级表头，总计列内嵌 =SUM 入 mask）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D427: Final[str] = "识别未披露的关联方D4-27"
TEMPLATE_ID_D427: Final[str] = "D427"
SHEET_KEY_D427: Final[str] = "d4-27-managed"  # 前端 D4_27_SHEET_KEY 锁死 d4-27-managed
ROWS_TABLE_KEY_D427: Final[str] = "undisclosed_rp_rows"
STORE_ITEM_ID_D427: Final[str] = "D4-27-rows"
ROW_IDENTITY_STORE_KEY_D427: Final[str] = "rowId"

HEADER_ROW_D427: Final[int] = 14
FIRST_DATA_ROW_D427: Final[int] = 15
LAST_DATA_ROW_D427: Final[int] = 24
#: 源模板实测 A27「三、审计说明：」（25 与 last_data+1 对齐但模板留了空行）。
FOOTER_ROW_D427: Final[int] = 27
FOOTER_MARKER_D427: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D427: Final[str] = "R"
UUID_COL_D427: Final[str] = "S"
TABLE_NAME_D427: Final[str] = f"GT_{TEMPLATE_ID_D427}_ROWS"

#: 18 列 A–R；总计列 M 源模板内嵌 =SUM(C15:L15) → 入 mask，不入受管契约（17 契约字段）。
MANAGED_FIELD_SPECS_D427: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    # seq value_type 对齐前端 number → amount（此前误标 text，store int 撞 normalize）。
    ("seq", "A", "editable", "amount", "seq", "序号"),
    ("name", "B", "editable", "text", "name", "姓名"),
    # 10 个身份属性勾选列：value_type=boolean（源模板示例 C16=1/G16=1 即勾选态）。
    ("is_personal_customer", "C", "editable", "boolean", "isPersonalCustomer", "个人客户"),
    ("is_customer_legal", "D", "editable", "boolean", "isCustomerLegal", "客户法人"),
    ("is_contract_signer", "E", "editable", "boolean", "isContractSigner", "合同签订人"),
    ("is_exec_relative", "F", "editable", "boolean", "isExecRelative", "高管亲属"),
    ("is_finance_dept", "G", "editable", "boolean", "isFinanceDept", "财务部门"),
    ("is_mgmt_dept", "H", "editable", "boolean", "isMgmtDept", "管理部门"),
    ("is_tech_dept", "I", "editable", "boolean", "isTechDept", "技术部门"),
    ("is_production_dept", "J", "editable", "boolean", "isProductionDept", "生产部门"),
    ("is_marketing_dept", "K", "editable", "boolean", "isMarketingDept", "营销部门"),
    ("is_other", "L", "editable", "boolean", "isOther", "其他"),
    # M = 总计（=SUM(C:L)）入 mask，不在此列表
    # 🔴 is_duplicate_name 是 Y/N 文本 select（非勾选框），保持 text，不改 boolean。
    ("is_duplicate_name", "N", "editable", "text", "isDuplicateName", "重名(Y/N)"),
    ("shareholder_exec_relative", "O", "editable", "text", "shareholderExecRelative", "公司股东/高管/亲属/员工"),
    ("annual_sales", "P", "editable", "amount", "annualSales", "年度销售额"),
    ("note", "Q", "editable", "text", "note", "说明"),
    ("index_no", "R", "editable", "text", "indexNo", "索引号"),
)
#: 总计列 M 逐行内嵌 =SUM(C:L) —— projection 不得覆盖。
FORMULA_MASK_D427: Final[tuple[str, ...]] = (
    f"M{FIRST_DATA_ROW_D427}:M{LAST_DATA_ROW_D427}",
)
EXPECTED_MAPPING_DIGEST_D427: Final[str] = (
    "b306839a6a68977112737136aca06680cfd1d6e90d90843bac3f9982de2febc2"
)


# ═══════════════════════════════════════════════════════════════════════════
# D4-28 客户信息核查清单（动态行，两级表头 9 主 + 5 子 + 索引号）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D428: Final[str] = "客户信息核查清单D4-28"
TEMPLATE_ID_D428: Final[str] = "D428"
SHEET_KEY_D428: Final[str] = "d4-28-managed"  # 前端 D4_28_SHEET_KEY 锁死 d4-28-managed
ROWS_TABLE_KEY_D428: Final[str] = "customer_checklist_rows"
STORE_ITEM_ID_D428: Final[str] = "D4-28-rows"
ROW_IDENTITY_STORE_KEY_D428: Final[str] = "rowId"

HEADER_ROWS_D428: Final[tuple[int, int]] = (12, 13)
FIRST_DATA_ROW_D428: Final[int] = 14
LAST_DATA_ROW_D428: Final[int] = 24
FOOTER_ROW_D428: Final[int] = 25
FOOTER_MARKER_D428: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D428: Final[str] = "O"
UUID_COL_D428: Final[str] = "P"
TABLE_NAME_D428: Final[str] = f"GT_{TEMPLATE_ID_D428}_ROWS"

#: 15 列 = 9 主(A–I) + 核查方式 5 子(J–N) + 索引号(O)。占比列 E/G/I 前端表内计算，OO 无内嵌公式。
MANAGED_FIELD_SPECS_D428: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    # seq number→amount、三个占比 percent→ratio，对齐前端「唯一结构真源」（此前误标 text）。
    ("seq", "A", "editable", "amount", "seq", "序号"),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),
    ("selection_reason", "C", "editable", "text", "selectionReason", "选取原因"),
    ("sales_amount", "D", "editable", "amount", "salesAmount", "销售金额"),
    ("sales_proportion", "E", "editable", "ratio", "salesProportion", "占总交易比重"),
    ("ar_balance", "F", "editable", "amount", "arBalance", "应收账款期末余额"),
    ("ar_proportion", "G", "editable", "ratio", "arProportion", "占期末余额比重"),
    ("contract_liab_balance", "H", "editable", "amount", "contractLiabBalance", "合同负债期末余额"),
    ("contract_liab_proportion", "I", "editable", "ratio", "contractLiabProportion", "占期末余额比重"),
    # 5 个核查方式勾选列：value_type=boolean（勾选落 <v>1</v>，未勾空格）。
    ("method_business_info", "J", "editable", "boolean", "methodBusinessInfo", "工商资料查询"),
    ("method_internet", "K", "editable", "boolean", "methodInternet", "互联网信息查询"),
    ("method_confirmation", "L", "editable", "boolean", "methodConfirmation", "函证"),
    ("method_interview", "M", "editable", "boolean", "methodInterview", "视频、电话访谈"),
    ("method_field_visit", "N", "editable", "boolean", "methodFieldVisit", "实地走访"),
    ("index_no", "O", "editable", "text", "indexNo", "索引号"),
)
FORMULA_MASK_D428: Final[tuple[str, ...]] = ()
EXPECTED_MAPPING_DIGEST_D428: Final[str] = (
    "19690f3494679a9427defda3f92e4f0380bb273b7f9773c4beff66604535a6fe"
)


# ── 每张表的静态描述（供 digest / 断言 / 契约构建）────────────────────────────
_SHEETS = {
    "D4-25": {
        "managed_sheet": MANAGED_SHEET_D425, "template_id": TEMPLATE_ID_D425,
        "sheet_key": SHEET_KEY_D425, "table_key": ROWS_TABLE_KEY_D425,
        "store_item_id": STORE_ITEM_ID_D425, "identity_key": ROW_IDENTITY_STORE_KEY_D425,
        "header_rows": [HEADER_ROW_D425], "first_data_row": FIRST_DATA_ROW_D425,
        "last_data_row": LAST_DATA_ROW_D425, "footer_row": FOOTER_ROW_D425,
        "footer_marker": FOOTER_MARKER_D425, "managed_last_col": MANAGED_LAST_COL_D425,
        "uuid_col": UUID_COL_D425, "table_name": TABLE_NAME_D425,
        "fields": MANAGED_FIELD_SPECS_D425, "formula_mask": FORMULA_MASK_D425,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D425, "field_count": 13,
    },
    "D4-26": {
        "managed_sheet": MANAGED_SHEET_D426, "template_id": TEMPLATE_ID_D426,
        "sheet_key": SHEET_KEY_D426, "table_key": ROWS_TABLE_KEY_D426,
        "store_item_id": STORE_ITEM_ID_D426, "identity_key": ROW_IDENTITY_STORE_KEY_D426,
        "header_rows": list(HEADER_ROWS_D426), "first_data_row": FIRST_DATA_ROW_D426,
        "last_data_row": LAST_DATA_ROW_D426, "footer_row": FOOTER_ROW_D426,
        "footer_marker": FOOTER_MARKER_D426, "managed_last_col": MANAGED_LAST_COL_D426,
        "uuid_col": UUID_COL_D426, "table_name": TABLE_NAME_D426,
        "fields": MANAGED_FIELD_SPECS_D426, "formula_mask": FORMULA_MASK_D426,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D426, "field_count": 19,
    },
    "D4-27": {
        "managed_sheet": MANAGED_SHEET_D427, "template_id": TEMPLATE_ID_D427,
        "sheet_key": SHEET_KEY_D427, "table_key": ROWS_TABLE_KEY_D427,
        "store_item_id": STORE_ITEM_ID_D427, "identity_key": ROW_IDENTITY_STORE_KEY_D427,
        "header_rows": [HEADER_ROW_D427], "first_data_row": FIRST_DATA_ROW_D427,
        "last_data_row": LAST_DATA_ROW_D427, "footer_row": FOOTER_ROW_D427,
        "footer_marker": FOOTER_MARKER_D427, "managed_last_col": MANAGED_LAST_COL_D427,
        "uuid_col": UUID_COL_D427, "table_name": TABLE_NAME_D427,
        "fields": MANAGED_FIELD_SPECS_D427, "formula_mask": FORMULA_MASK_D427,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D427, "field_count": 17,
    },
    "D4-28": {
        "managed_sheet": MANAGED_SHEET_D428, "template_id": TEMPLATE_ID_D428,
        "sheet_key": SHEET_KEY_D428, "table_key": ROWS_TABLE_KEY_D428,
        "store_item_id": STORE_ITEM_ID_D428, "identity_key": ROW_IDENTITY_STORE_KEY_D428,
        "header_rows": list(HEADER_ROWS_D428), "first_data_row": FIRST_DATA_ROW_D428,
        "last_data_row": LAST_DATA_ROW_D428, "footer_row": FOOTER_ROW_D428,
        "footer_marker": FOOTER_MARKER_D428, "managed_last_col": MANAGED_LAST_COL_D428,
        "uuid_col": UUID_COL_D428, "table_name": TABLE_NAME_D428,
        "fields": MANAGED_FIELD_SPECS_D428, "formula_mask": FORMULA_MASK_D428,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D428, "field_count": 15,
    },
}


def mapping_digest_payload(sheet_code: str) -> dict[str, Any]:
    s = _SHEETS[sheet_code]
    return {
        "contract_fields": _contract_fields_digest_shape(s["fields"]),
        "first_data_row": s["first_data_row"],
        "footer_marker_exact": s["footer_marker"],
        "footer_row": s["footer_row"],
        "header_rows": s["header_rows"],
        "last_data_row": s["last_data_row"],
        "managed_sheet": s["managed_sheet"],
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def compute_mapping_digest(sheet_code: str) -> str:
    return _digest(mapping_digest_payload(sheet_code))


def assert_mapping_digest(sheet_code: str) -> str:
    s = _SHEETS[sheet_code]
    got = compute_mapping_digest(sheet_code)
    if got != s["expected_digest"]:
        raise D4ChecklistDigestError(
            f"{sheet_code} mapping_digest 漂移：现算={got} 冻结={s['expected_digest']}"
        )
    n = len(s["fields"])
    if n != s["field_count"]:
        raise D4ChecklistDigestError(
            f"{sheet_code} 契约字段数须为 {s['field_count']}，实得 {n}"
        )
    return got


def assert_all_checklist_mapping_digests() -> dict[str, str]:
    return {code: assert_mapping_digest(code) for code in _SHEETS}


def stable_key_for(sheet_code: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{_SHEETS[sheet_code]['table_key']}/{row_identity}/{column_key}"


def rows_table_payload(sheet_code: str) -> dict[str, Any]:
    s = _SHEETS[sheet_code]
    managed_sheet = s["managed_sheet"]
    header_row = s["header_rows"][0]

    def _src(cell: str) -> str:
        return f"源xlsx!{managed_sheet}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in s["fields"]:
        fields.append(
            {
                "stable_field_key": stable_key_for(sheet_code, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{s['first_data_row']}"),
                "header_source_ref": _src(f"{column}{header_row}"),
                "store_item_id": s["store_item_id"],
                "header_text": header_text,
            }
        )
    return {
        "table_key": s["table_key"],
        "anchor": f"A{header_row}",
        "header_rows": len(s["header_rows"]),
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{s['identity_key']}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": s["footer_marker"],
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                f"{sheet_code} 动态行；A{s['footer_row']}「{s['footer_marker']}」是受管区下边界"
                f"（插行须下移）。UUID 用 {s['uuid_col']}（数据止 {s['managed_last_col']}）。"
            ),
        },
        "formula_mask": list(s["formula_mask"]),
        "fields": fields,
    }


def sheet_payload(sheet_code: str) -> dict[str, Any]:
    """instrumentation managed_sheets[] 的一项。"""
    s = _SHEETS[sheet_code]
    return {
        "sheet_key": s["sheet_key"],
        "excel_name": s["managed_sheet"],
        "template_id": s["template_id"],
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [rows_table_payload(sheet_code)],
    }


def instrumentation_spec(sheet_code: str, *, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    s = _SHEETS[sheet_code]
    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=s["template_id"],
        template_relative_path=template_relative_path,
        managed_sheet=s["managed_sheet"],
        first_data_row=s["first_data_row"],
        last_data_row=s["last_data_row"],
        footer_row=s["footer_row"],
        managed_last_col=s["managed_last_col"],
        uuid_col=s["uuid_col"],
        table_name=s["table_name"],
        sheet_key=s["sheet_key"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# store projection（HTML store JSON → FieldValue projection）+ merge（projection → rows）
# ═══════════════════════════════════════════════════════════════════════════


def _iter_store_rows(payload, *, identity_key: str, item_id: str):
    """行对象数组迭代（稳定身份，禁下标兜底、禁重复）。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise D4ChecklistDigestError(f"{item_id} remark 非合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise D4ChecklistDigestError(f"{item_id} 载荷必须是行对象数组，实得 {type(rows).__name__}")
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise D4ChecklistDigestError(f"{item_id} 第 {ordinal} 项不是对象")
        raw = row.get(identity_key)
        if not isinstance(raw, str) or not raw.strip():
            raise D4ChecklistDigestError(
                f"{item_id} 第 {ordinal} 行缺稳定行身份 {identity_key!r}（禁下标兜底）"
            )
        identity = raw.strip()
        if identity in seen:
            raise D4ChecklistDigestError(f"{item_id} 重复行身份 {identity!r}")
        seen.add(identity)
        yield identity, row


def build_store_projection(sheet_code: str, payload, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    s = _SHEETS[sheet_code]
    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    checkbox_paths = _checkbox_json_paths(sheet_code)
    for identity, row in _iter_store_rows(
        payload, identity_key=s["identity_key"], item_id=s["store_item_id"]
    ):
        budget.add_row(s["table_key"])
        row_keys.append(identity)
        for column_key, _c, _m, _vt, json_path, _h in s["fields"]:
            spec = contract.field_by_stable_key(stable_key_for(sheet_code, column_key))
            budget.add_field()
            sk = stable_key_for(sheet_code, column_key, identity)
            raw = _resolve_store_path(row, json_path)
            # checkbox 列：JS 布尔 → 勾选 True / 未勾 None（源模板「1 / 空」口径，见 _coerce_*）。
            cell_value = (
                _coerce_checkbox_to_store(raw) if json_path in checkbox_paths else raw
            )
            values[sk] = FieldValue(
                stable_key=sk,
                value=cell_value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={s["table_key"]: tuple(row_keys)},
    )


def merge_projection_into_rows(
    sheet_code: str, *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → rows（按稳定 rowId merge；formula_mask/protected 字段跳过）。"""
    s = _SHEETS[sheet_code]
    table_key = s["table_key"]
    identity_key = s["identity_key"]
    field_to_path = {spec[0]: spec[4] for spec in s["fields"]}
    checkbox_paths = _checkbox_json_paths(sheet_code)
    prefix = f"{table_key}/"

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(identity_key) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {identity_key: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        json_path = field_to_path.get(sk.rsplit("/", 1)[-1])
        if not json_path:
            continue
        visited += 1
        write_value = getattr(fv, "value", None)
        # checkbox 列：真 bool / 未勾 None → 前端 el-checkbox 要严格布尔（None/未勾 → False）。
        if json_path in checkbox_paths:
            write_value = _coerce_checkbox_from_projection(write_value)
        if set_json_path(target, json_path, write_value):
            applied += 1
            touched.add(str(rid))
    return [by_id[rid] for rid in order], applied, visited, touched


# ── 供 phase5_d4_revenue_detail 集成用的清单 ────────────────────────────────
CHECKLIST_SHEET_CODES: Final[tuple[str, ...]] = ("D4-25", "D4-26", "D4-27", "D4-28")
STORE_ITEM_ID_BY_CODE: Final[dict[str, str]] = {c: _SHEETS[c]["store_item_id"] for c in CHECKLIST_SHEET_CODES}
SHEET_KEY_BY_CODE: Final[dict[str, str]] = {c: _SHEETS[c]["sheet_key"] for c in CHECKLIST_SHEET_CODES}
