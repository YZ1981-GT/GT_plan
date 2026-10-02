# -*- coding: utf-8 -*-
"""L7 其他非流动负债 —— 受管 `明细表L7-2` 的身份/几何/字段声明。

spec: l7-true-bidirectional-2026-10-01 · 第3步（选型见 `.agents/tasks/l7-managed-table-choice/report.md`）

选型现算：L7-2 明细表是 L7 整册唯一的数据录入源（审定表 L7-1 / 两张附注 / 检查表 L7-4
全部跨 sheet 引用 `明细表L7-2`），HTML 子组件 `L7TabDetail.vue` 是其忠实渲染（27 列语义逐列
对齐、行动态、公式一致、持久化已是单 item JSON 数组 `L7-L7-2-full-data`）。

几何（openpyxl 逐格实测，sha 9fe09748…）：两级表头 r10（组标题 项目/未审数/期初调整/账项调整/
重分类调整/审定数/文件依据/索引号/备注）+ r11（叶子 期初余额/本期增加/本期减少/期末余额 等），
数据区 r12~r16（5 行），footer r17 标签在 **A17「合计」**（B17~O17 连续 =SUM(..12:..16)）。
r18「三、审计说明：」之下不受管。有效业务列 A..R（18 列）；物理 max_column=27(AA) ⇒ UUID 列 AB。
五个公式列 E/L/M/N/O 逐行 E=B+C-D / L=B+F+G / M=C+H+J / N=D+I+K / O=L+M-N（负债口径）。
受管表零裸 IF（整册裸 IF 仅 审定表L7-1 6 格，per-file 中性化照挂）。

🔴 列语义错位（如实登记，不影响往返正确性）：HTML `L7DetailRow` 把 P/Q/R 命名为
nature/reason/maturityInfo（性质/原因/到期），而 Excel 模板 P10/Q10/R10 实际表头是
文件依据/索引号/备注。契约按**列位置**搬运（json_key 对齐前端存储、header_text 忠于模板），
两者位置一一对应，往返不受影响；header_text 仅用于契约文档/校验，不改 UI 显示。
"""
from __future__ import annotations

from typing import Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as _fields

PHASE5_WAVE: Final[str] = "l_cycle_other_noncurrent_liabilities"
ENTRY_ID: Final[str] = "xlsx/gt-l7-other-noncurrent-liabilities"
ADAPTER_ID: Final[str] = "l7.other_noncurrent_liabilities"
#: manifest 冻结的 wp_code_pattern（宿主 GtL7OtherNoncurrentLiabilities CamelCase 幻影码，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"L7O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L7 其他非流动负债.xlsx"
#: 🔴 净化后 sha（sanitize_l7_template_external_links.py 把受管 sheet 的 3 个共享公式组展开为
#: 逐格显式公式，受管 sheet openpyxl 逐格 0 diff，仅去 OOXML 共享组结构）。
#: 净化前原始值见 PRE_SANITIZE_TEMPLATE_SHA256（真 OO 往返 materialize 对横向共享组 M12:N16
#: 抛 excel_row_shift_shared_formula_orientation_unsupported，故净化在五环发布前执行）。
TEMPLATE_SHA256: Final[str] = "35e47cf951e4ec008525d9f65008b3fc48852d59b1f25ac0089b5426394b9436"
PRE_SANITIZE_TEMPLATE_SHA256: Final[str] = "9fe09748148a6f0692eef85e0c0cf3e24f22ea7e5d011c029dfa3e71bb04daea"
MANAGED_SHEET: Final[str] = "明细表L7-2"
TEMPLATE_ID: Final[str] = "L72"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "other_noncurrent_liability_detail_rows"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 16
FOOTER_ROW: Final[int] = 17
MANAGED_LAST_COL: Final[str] = "R"
UUID_COL: Final[str] = "AB"
FOOTER_MARKER: Final[str] = "合计"
STORE_ITEM_ID: Final[str] = "L7-L7-2-full-data"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
#: 前端 L7DetailRow 全部 18 字段均有模板对应列 ⇒ 无 HTML-only 字段。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()

#: 组标题单元格（两级表头第一维）：B/F/H/J/L 五个 merged 组（r10 组标题行）。
_G: Final[Mapping[str, str]] = {
    "unadjusted": f"B{HEADER_GROUP_ROW}",   # B10:E10「未审数」
    "prior_adj": f"F{HEADER_GROUP_ROW}",     # F10:G10「期初调整」
    "aje": f"H{HEADER_GROUP_ROW}",           # H10:I10「账项调整」
    "rje": f"J{HEADER_GROUP_ROW}",           # J10:K10「重分类调整」
    "audited": f"L{HEADER_GROUP_ROW}",       # L10:O10「审定数」
}

#: 18 个受管字段，7 元组 `(column_key, 列标, mode, value_type, store json 键, 表头文本, 组标题单元格)`，
#: 顺序即 Excel 列序 A→R。
#: 🔴 json_key 对齐前端 `useL7Detail.L7DetailRow`（camelCase）。
#: 🔴 E/L/M/N/O 五列 mode=formula —— 模板里逐行有真公式，OO 侧不得被值覆盖。
#: 🔴 有组标题的列（B..O）header_text 取**叶子行**文本，无组的（A/P/Q/R）取组标题行文本。
MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("begin_unadjusted", "B", "editable", "amount", "beginUnadjusted", "期初余额", _G["unadjusted"]),
    ("begin_aje", "C", "editable", "amount", "beginAje", "本期增加", _G["unadjusted"]),
    ("begin_rje", "D", "editable", "amount", "beginRje", "本期减少", _G["unadjusted"]),
    ("begin_audited", "E", "formula", "amount", "beginAudited", "期末余额", _G["unadjusted"]),
    ("aje_increase", "F", "editable", "amount", "ajeIncrease", "账项调整", _G["prior_adj"]),
    ("rje_increase", "G", "editable", "amount", "rjeIncrease", "重分类调整", _G["prior_adj"]),
    ("end_aje_increase", "H", "editable", "amount", "endAjeIncrease", "本期增加", _G["aje"]),
    ("end_rje_decrease", "I", "editable", "amount", "endRjeDecrease", "本期减少", _G["aje"]),
    ("end_aje_decrease", "J", "editable", "amount", "endAjeDecrease", "本期增加", _G["rje"]),
    ("end_rje_increase", "K", "editable", "amount", "endRjeIncrease", "本期减少", _G["rje"]),
    ("end_unadjusted", "L", "formula", "amount", "endUnadjusted", "期初余额", _G["audited"]),
    ("end_aje", "M", "formula", "amount", "endAje", "本期增加", _G["audited"]),
    ("end_rje", "N", "formula", "amount", "endRje", "本期减少", _G["audited"]),
    ("end_audited", "O", "formula", "amount", "endAudited", "期末余额", _G["audited"]),
    ("nature", "P", "editable", "text", "nature", "文件依据", ""),
    ("reason", "Q", "editable", "text", "reason", "索引号", ""),
    ("maturity_info", "R", "editable", "text", "maturityInfo", "备注", ""),
)

#: 五个公式列的模板形态（负债口径）。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "E": "=B{row}+C{row}-D{row}",
    "L": "=B{row}+F{row}+G{row}",
    "M": "=C{row}+H{row}+J{row}",
    "N": "=D{row}+I{row}+K{row}",
    "O": "=L{row}+M{row}-N{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

SPEC_L72: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=TABLE_NAME,
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    #: L7-2 无账龄组 —— 两级表头纯粹是「调整类型 × 增减方向」。
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    #: footer B17~O17 连续 14 列全是 `=SUM(X12:X16)` ⇒ 真有公式。
    footer_carries_total_formula=True,
    #: 🔴 footer 标签在 A17「合计」（与 L3-9 同在 A 列）。
    footer_search_column="A",
    error_label="L7-2 其他非流动负债明细表",
    #: 🔴 锚点取第 0 位 item_name（项目名称，真业务文本；无整数序号列可用）。
    ghost_row_anchor_index=0,
)

#: 18 个受管字段（6 元组视图），由框架层现算 —— provider 不复制展开结果。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _fields(SPEC_L72)
)

#: 五个公式列的只读区域，由框架层 property 现算。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L72.formula_mask

#: column_key → 组标题单元格（只有 B..O 有）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    row[0]: row[6] for row in MANAGED_FIELD_SPECS_7 if row[6]
}

_HTML_STORE_NOTE: Final[str] = (
    "整张 L7-2 明细表存成 `L7-L7-2-full-data` 的 remark JSON 数组（useL7Detail 的 "
    "JSON.stringify(rows)）；每行已有稳定 rowId（2026-10-01 把私有 Date.now+Math.random "
    "生成器换成平台共享 newRowIdentity('l72det')，已有 rowId 优先不重铸）。契约按 stable "
    "field + row rowId 拆开。sibling 键 `L7-L7-2-rows`（勾稽摘要）/ `L7-L7-2-row-N-end_balance`"
    "（供 CrossSheet 读）本轮不受管、不预登记。真库 `L7-L7-2-%` 现算 0 行，零迁移负担。"
    "🔴 前端 L7DetailRow 全部 18 字段均有模板对应列 ⇒ 无 HTML-only 字段。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 L/L7 其他非流动负债.xlsx（8 sheet，sha 9fe09748…）：受管 "
    "明细表L7-2 两级表头 r10（组标题 项目/未审数/期初调整/账项调整/重分类调整/审定数/文件依据/"
    "索引号/备注）+ r11 叶子、数据区 r12~r16（5 行）、footer A17「合计」（B17~O17 连续 "
    "=SUM(X12:X16)）、A..R 18 字段与前端 L7DetailRow 18/18 对齐、五个公式列 "
    "E=B+C-D / L=B+F+G / M=C+H+J / N=D+I+K / O=L+M-N（负债口径）；物理 max_column=AA(27) 故 "
    "UUID=AB；manifest 幻影码 L7O finder 零命中。受管表零裸 IF（整册裸 IF 仅 审定表L7-1 6 格，"
    "per-file 中性化照挂）。canary 不选 审定表L7-1（R7~R11 全跨 sheet 公式，下游视图非录入表）。"
)
