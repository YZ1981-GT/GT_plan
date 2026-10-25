# -*- coding: utf-8 -*-
"""N4 税金及附加 —— 受管 sheet 层声明（身份 / 几何 / 字段 / RowTableSheetSpec）。

spec: n-cycle-sync-foundation-and-first-canary · N4 canary · Task 3

按 `phase5_l1_sheets.py` 的既有范式从 provider 主模块拆出（`check_file_size.py` 对**新增**
`.py` 强制 ≤800 行）。

受管 sheet = `税金及附加明细表N4-2`（openpyxl 逐格实测，净化后复算）：**单级表头** r8、
数据区 r9~r18（r9~r16 预印 8 税种名、r17/r18 空）、footer r19（标签在 **A19**「合计」）、
11 列 A..K（有效业务列到 K），三个公式列 E/I/K 逐行。

🔴 `税金及附加审定表N4-1` 是**派生只读投影**：r7~r15 无一个可输入格（全是跨表引用 N4-2 +
加总 + 裸 IF 变动率），写它会毁掉整册「审定表取数自明细表」的联动，与 L1 的 `审定表L1-1`
完全同构。

🔴 模板**既知缺陷**（记录型锁定，SHALL NOT 改 .xlsx）：
  - `E9 = '=B9+C9+N4'`（r9 消费税）—— 第三加数应为 `D9`，误写 `N4`（被 Excel 当列引用、恒空
    ⇒ 静默吞第三分量，NC-32 A1 族）。`FORMULA_TEMPLATES['E']` 以正确形态 `=B{row}+C{row}+D{row}`
    为模板；r9 的异常只在守卫里以记录型断言锁定，不在 materialize 时"修复"（修复属模板修订另案）。
  - `D19 = '=SUM(D4:N18)'`（footer D 列 SUM 越界到 N 列/从 r4 起）—— 同属模板缺陷，记录型锁定。

模板已净化（Task 7a `sanitize_n4_template_external_links.py` 删 2 外链部件 + 中性化隐藏「原底稿」
册的 5 个外部引用公式，留 `.preclean.bak`）；受管 sheet 逐格 0 diff，故 `TEMPLATE_SHA256`
取**净化后**值。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / 净化后模板实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "n_cycle_taxes_and_surcharges"
ENTRY_ID: Final[str] = "xlsx/gt-n4-taxes-and-surcharges"
ADAPTER_ID: Final[str] = "n4.taxes_and_surcharges"
#: manifest 冻结的 wp_code_pattern（宿主 GtN4TaxesAndSurcharges CamelCase 幻影码，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"N4T"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "N/N4 税金及附加.xlsx"
#: 🔴 净化后 sha256（Task 7a）—— 读模板时 fail-closed 校验。
TEMPLATE_SHA256: Final[str] = (
    "2005eada32506e9e2b1b6f68c704ca4f6626b8a78e9e2a3a221ca00602cad638"
)
MANAGED_SHEET: Final[str] = "税金及附加明细表N4-2"
#: 🔴 派生只读投影表：r7~r15 全公式（跨表引用 N4-2 + 加总 + 裸 IF），一格不写。
DERIVED_SHEET: Final[str] = "税金及附加审定表N4-1"
TEMPLATE_ID: Final[str] = "N42"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "taxes_surcharges_detail_rows"

#: 🔴 单级表头：N4-2 只有 r8 一行表头（与 L1 两级表头不同）。
HEADER_ROW: Final[int] = 8

#: 数据区与 footer（净化后复算：数据 9-18，合计 19）。
FIRST_DATA_ROW: Final[int] = 9
LAST_DATA_ROW: Final[int] = 18
FOOTER_ROW: Final[int] = 19

#: 最后一列受管业务列（K 差异）与隐藏 row UUID 列（= max_column + 1 = 12 = L）。
MANAGED_LAST_COL: Final[str] = "K"
UUID_COL: Final[str] = "L"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer 标签实测在 **A19**、文本 `合计`（引擎默认按 A 列找 marker，无需像 L1 补 C 列）。
FOOTER_MARKER: Final[str] = "合计"
FOOTER_LABEL_CELL: Final[str] = f"A{FOOTER_ROW}"
FOOTER_SEARCH_COLUMN: Final[str] = "A"

STORE_ITEM_ID: Final[str] = "N4-2-detail-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
#: 🔴 熵键（`useN4Detail` 用 `row-${random}`）作稳定身份 —— 同税种可多行（多笔印花税），
#: 语义键会撞，故保留熵键 `rowKey`（不改语义键），对齐 `shared/stableRowIdentity.ts`。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowKey"

#: 🔴 前端 `N4DetailRow` 有、模板列无直接对应的 UI 计算中间量 —— 保留为 HTML-only，**不入契约**。
#:   taxBasis/taxRate/periodAmount/yoyChange/diff/n2Accrual 都是 computed（calcYoyChange 等），
#:   不是持久化真源；seq 是展示序号、isEditable 是 UI 标记。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = (
    "seq",
    "taxBasis",
    "taxRate",
    "periodAmount",
    "yoyChange",
    "n2Accrual",
    "diff",
    "isEditable",
)

#: 11 个受管字段，7 元组 `(column_key, 列标, mode, value_type, store json 键, 表头文本, 组标题单元格)`，
#: 顺序即 Excel 列序 A→K。N4-2 单级表头 ⇒ 组标题单元格全为 ""。
#:
#: 🔴 E/I/K 三列 mode=formula —— 模板里逐行有真公式，OO 侧不得被值覆盖。
#: 🔴 `json_key` 按模板列补齐（design §0.4 逐列对齐）：UI 的 N4DetailRow 是计算视图，
#:    这里落的是**模板 N4-2 的 11 列**（本/上期各「未审数/账项调整/重分类调整/审定数」+
#:    应交税费贷方金额 + 差异）。
MANAGED_FIELD_SPECS_7: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("tax_type", "A", "editable", "text", "taxType", "项目", ""),
    ("period_unadjusted", "B", "editable", "amount", "periodUnadjusted", "本期未审数", ""),
    ("period_aje", "C", "editable", "amount", "periodAje", "账项调整", ""),
    ("period_rje", "D", "editable", "amount", "periodRje", "重分类调整", ""),
    ("period_audited", "E", "formula", "amount", "periodAudited", "本期审定数", ""),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "上期未审数", ""),
    ("prior_aje", "G", "editable", "amount", "priorAje", "账项调整", ""),
    ("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整", ""),
    ("prior_audited", "I", "formula", "amount", "priorAudited", "上期审定数", ""),
    ("accrual_credit", "J", "editable", "amount", "accrualCredit", "应交税费贷方金额", ""),
    ("accrual_diff", "K", "formula", "amount", "accrualDiff", "与应交税费贷方差异", ""),
)

#: 三个公式列的模板形态（本期审定数 = 本期未审+账项+重分类；上期同；差异 = 本期审定−应交税费贷方）。
#: 🔴 r9 消费税的 E 列模板缺陷（`=B9+C9+N4`）不进这里 —— 这里是**正确**形态（以 r10 为模板），
#:    缺陷只在守卫里记录型锁定。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "E": "=B{row}+C{row}+D{row}",
    "I": "=F{row}+G{row}+H{row}",
    "K": "=E{row}-J{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 单一权威声明（引擎行为全由本 spec 驱动，provider 不手写 mask / 字段展开）
# ═══════════════════════════════════════════════════════════════════════════

SPEC_N42: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=TABLE_NAME,
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    #: 🔴 单级表头：只有 header_row，不设 header_group_row/header_leaf_row。
    header_row=HEADER_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    #: 🔴 N4-2 无账龄组（税种明细，非账龄分析）。
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    #: footer B19~K19 连续列（除 A 标签）全是 `=SUM(X9:X18)` ⇒ 真有公式（D19 是越界缺陷，记录型锁）。
    footer_carries_total_formula=True,
    #: 🔴 footer 标签在 A19（引擎默认即 A 列，与 L1 的 C 列不同）。
    footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="N4-2 明细表",
    #: 🔴 锚点取第 0 位 `tax_type`（税种名，真业务名称 = 模板 A 列）：
    #: 不取 `seq`（整数序号，`0` 是合法真值不是"空"信号，同 L1/d6）。
    ghost_row_anchor_index=0,
)

#: 11 个受管字段（6 元组视图），由框架层现算 —— provider 不复制展开结果。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_N42)
)

#: 三个公式列的只读区域，由框架层 property 现算（E9:E18 / I9:I18 / K9:K18）。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_N42.formula_mask

#: column_key → 组标题单元格（N4-2 单级表头 ⇒ 空字典）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    row[0]: row[6] for row in MANAGED_FIELD_SPECS_7 if row[6]
}

_HTML_STORE_NOTE: Final[str] = (
    "整张税金及附加明细表存成这一条 item `N4-2-detail-rows` 的 remark/conclusion（JSON 数组"
    "字符串，useN4Detail 的 rows）。本契约按 stable field + row rowKey 拆开。🔴 行身份是**熵键**"
    "（`row-${random}` / `row-${Date.now()}-${random}`）而非语义键 —— 同税种可多行（多笔印花税），"
    "语义键会撞，故保留熵键作稳定身份，对齐 shared/stableRowIdentity.ts 的 adoptRowKey（已落库"
    "优先）+ generatedRowKey。真库 `N4-2-detail-rows` 现算 0 行，零迁移负担。🔴 前端 N4DetailRow "
    "的 taxBasis/taxRate/periodAmount/yoyChange/diff/n2Accrual/seq/isEditable 是 computed / UI "
    "标记，模板无持久化真源列 ⇒ 保留为 HTML-only，不入契约。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测权威模板 N/N4 税金及附加.xlsx（9 sheet，净化后 sha256 2005eada）的受管 sheet "
    "税金及附加明细表N4-2：单级表头 行 8（项目/本期未审数/账项调整/重分类调整/本期审定数/上期未审数/"
    "账项调整/重分类调整/上期审定数/应交税费贷方金额/与应交税费贷方差异），11 列 A-K，数据区 9-18"
    "（r9~r16 预印 8 税种名 消费税/城市维护建设税/教育费附加/资源税/房产税/土地使用税/车船使用税/"
    "印花税，r17/r18 空），footer 19 —— 🔴 footer 标签在 A19「合计」（引擎默认 A 列），"
    "B19~K19 连续列全 =SUM(X9:X18)；三个公式列逐行 E=B+C+D（本期审定数）/ I=F+G+H（上期审定数）/ "
    "K=E-J（与应交税费贷方差异）。册内零 Excel Table、零 definedName ⇒ GT_N42_ROWS 为本契约新建、"
    "UUID 列取 max_column+1 = L。整册裸 IF 20 格全在派生表 税金及附加审定表N4-1（K/M 列变动率），"
    "受管表零命中（per-file 策略仍挂中性化）。🔴 canary 不选 税金及附加审定表N4-1：该表 r7~r15 "
    "无一个可输入格（全是跨表引用 N4-2 + 加总 + 裸 IF 变动率）。🔴 模板既知缺陷 E9=`=B9+C9+N4`"
    "（第三加数误写列引用）与 D19=`=SUM(D4:N18)`（越界）记录型锁定，不改模板。"
)
