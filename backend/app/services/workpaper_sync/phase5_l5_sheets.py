# -*- coding: utf-8 -*-
"""L5 长期应付款 —— 受管 `明细表L5-2` 的身份/几何/字段声明（**两区同键 + flat 账龄**，R24 占位续行作静态骨架）。

spec: l5-true-bidirectional-2026-10-01 · T4（T1 架构坐实见 `.agents/tasks/.../t1-architecture-gate.md`）

═══ 🔴 两区同键 + flat 账龄（照 G9 多区 + D6 flat，L 域首次） ═══

受管表 `明细表L5-2`（科目 2701 长期应付款，负债类余额口径 期末=期初-借+贷）有**两个受管数据区**，
区之间夹着不受管的区标题行与小计行（照 G9 范式）：

| 区 | section_value | 分组标题（静态骨架） | 数据区 | 小计（静态骨架） | uuid_col | template_id |
|---|---|---|---|---|---|---|
| ① 售后租回 | `saleLeaseback` | A10 售后租回业务形成的融资 | **R11:15** | A16 小计 =SUM(B11:B15) | AD | L52R1 |
| ② 分期付款 | `installment`   | A17 分期付款方式购入固定资产 | **R18:22** | A23 小计 =SUM(B18:B22) | AE | L52R2 |

🔴 **R24「其他」段作模板静态骨架，不进受管区（用户裁决 A，2026-10-02）**：
R24 的 `A24='…'`（U+2026 排版续行占位）+ roll-forward 公式骨架（E24/L24/… 在，B24/C24/D24 输入格空），
是典型中文审计模板的「其他……」预留续行占位。现查坐实它**不是**业务数据行：
真库 `L5-L5-2-rows` 0 行且无任何 section/R24 历史痕迹、HTML 侧无用户可填的「其他」第三分组、
Excel R24 输入格全空。平台级 typography 门 `excel_typography_rows`（BP-21）fail-closed 拒绝把纯省略号
占位行声明为受管区末行（防 materialize 把业务字段写回 `……`）—— 该门比幽灵行防护更硬，T1 未测它。
⇒ R24 连同小计 A16/A23、合计 A25、区标题 A10/A17 一起作模板静态骨架（`is_template_skeleton_identity`
保护，roll-forward 与 SUM 公式幸存）。放弃的只是一个占位续行，两个真实业务分组全受管 ⇒ **零能力损失**。
合计 A25=`=SUM(B16,B23,B24)` 仍引用 B24（R24 的 B 格，模板预留空值 ⇒ SUM 结果不受影响），公式原样幸存。

两区**共享** `store_item_id='L5-L5-2-rows'`，用 `row_section_field='section'` + 各段 `row_section_value`
区分（前端一个 JSON 数组、单存储键）。`iter_store_rows` 按 section 过滤、`merge` 给新增行补段归属。

🔴 **T1/可行性报告「三区」结论勘误**：T1 候选 C 判「三区同键」成立（§四称单行第三段 last-first=0 在
projection/merge 全链路与行数解耦），但**漏测了 instrumentation 的 typography 门**（比幽灵行防护更硬的
平台级 BP-21 约束）—— 它在 first publication 期对区③ R24:24 fail-closed。实施期（2026-10-02）据用户裁决 A
收敛为**两区 + R24 占位静态**。T1/report 的「三区」措辞以此勘误为准（历史档案 append-only，不回填改写）。

两级表头 `header_group_row=8` / `header_leaf_row=9`。7 公式列 `(E,L,M,N,O,R,S)` 全 11 输入行同形：
`E=B-C+D` · `L=B+F+G` · `M=C+H+J` · `N=D+I+K` · `O=L-M+N` · `R=L-P` · `S=O-Q`（本行算术、无跨行派生、
无裸 IF ⇒ bare_IF=0，无需 neutralize、无 warning 退路）。

账龄 T~X 单组 5 桶（期末到期日分析），`AgingLayout.flat`（照 D6；L 域首个账龄表）；
叶子标签用模板实测全角字符（V `1～2年` 的 `～`=U+FF5E / W `２～3年` 的 `２`=U+FF12、`～`=U+FF5E），禁半角替换。

🔴 **列语义鸿沟（方案 b，报告 §二）**：HTML `L5DetailRow` 的融资属性列（名义金额/折现率/现值/起止日/
款项类型/币种/担保/HTML 旧标量 unadjusted·aje·rje·audited/债权人）与 Excel roll-forward 对不上 ⇒
退 **html_only**（继续喂 L5-5/L5-6/L5-7，不进契约、OO 侧不渲染）。受管区只覆盖 Excel A..S + 账龄 T~X。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    StoreKind,
)

PHASE5_WAVE: Final[str] = "l_cycle_long_term_payables"
ENTRY_ID: Final[str] = "xlsx/gt-l5-long-term-payables"
ADAPTER_ID: Final[str] = "l5.long_term_payables"
#: manifest 冻结的幻影码（宿主 GtL5LongTermPayables CamelCase，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"L5L"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L5 长期应付款.xlsx"
#: 现算（PRE_SANITIZE）。若 T5 发布被 OOXML 安全门拒而需净化外链 → 此为净化前值，净化后另算。
TEMPLATE_SHA256: Final[str] = (
    "09380626107dc1b975662eaa60fa99ec541901c0729bb0d2b35bbb60807a9b68"
)
MANAGED_SHEET: Final[str] = "明细表L5-2"
TEMPLATE_ID: Final[str] = "L52"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
HEADER_GROUP_ROW: Final[int] = 8
HEADER_LEAF_ROW: Final[int] = 9

#: 两区共享的 store 键（双前缀 `L5-L5-2-`，照 `useL5Detail.ts` 实测 `ITEM_ROWS`）。
STORE_ITEM_ID: Final[str] = "L5-L5-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "key"
ROW_SECTION_FIELD: Final[str] = "section"
FOOTER_MARKER: Final[str] = "小计"
#: 🔴 主区（区① 售后租回）的 UUID 列。`projection_first_publication._observe_identity_inventory`
#: 的 fallback 读 `provider.UUID_COL`（因 ExcelInstrumentationSpec 字段名是 uuid_col 而非
#: uuid_column，`getattr(spec,'uuid_column',None)` 恒 None）—— 多区 provider 必须显式暴露主区 UUID 列，
#: 否则 identity inventory 的 uuid_column_letter 落 None、`resolved_sheet_by` 恒 None（照 L7 的 UUID_COL）。
UUID_COL: Final[str] = "AD"
#: 主区 Excel Table 名（同理供 inventory fallback；但主区 instrumentation_spec().table_name 已非空，
#: 此常量只作与 L7 对齐的显式声明）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_LONG_TERM_PAYABLE_ROWS_R1"
#: 🔴 主区（区①）的 table_key。多受管区 provider 必须声明它指向主表，首版发布据此取主 binding、
#: 其余区走 sibling_bindings（`projection_first_publication._row_identity_table_key`）。
ROWS_TABLE_KEY: Final[str] = "long_term_payable_rows_r1"

#: 🔴 html_only 行键（照 D4-5；前端有、模板无、不进契约、OO 侧不渲染）。
#: 必须与前端 `useL5Detail.L5_HTML_ONLY_KEYS` 逐值一致（adapter 测试守护）。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = (
    "nominalAmount", "discountRate", "presentValue", "startDate", "maturityDate",
    "category", "currency", "guaranteeType", "unadjusted", "aje", "rje", "audited", "creditor",
)

#: 一级分组标题单元格（两级表头第一维，R8 合并组）。无组的列取 ""。
_G: Final[dict[str, str]] = {
    "unadjusted": f"B{HEADER_GROUP_ROW}",   # B8:E8「未审数」
    "prior_adj": f"F{HEADER_GROUP_ROW}",     # F8:G8「期初调整」
    "aje": f"H{HEADER_GROUP_ROW}",           # H8:I8「账项调整」
    "rje": f"J{HEADER_GROUP_ROW}",           # J8:K8「重分类调整」
    "audited": f"L{HEADER_GROUP_ROW}",       # L8:O8「审定数」
    "disclosure": f"R{HEADER_GROUP_ROW}",    # R8:S8「披露审定数」
}

#: 19 个标量受管字段（7 元组 `(column_key, 列标, mode, value_type, json_key, header_text, group_header_cell)`，
#: 顺序即 Excel 列序 A→S）。账龄 T~X 由 AgingLayout.flat 展开追加，不在此列。
#: 🔴 json_key 对齐前端 `useL5Detail.L5DetailRow`（camelCase）。
#: 🔴 E/L/M/N/O/R/S 七列 mode=formula —— 模板逐行有真公式，OO 侧不得被值覆盖。
#: 🔴 有组标题的列（B..S）header_text 取**叶子行 R9**，无组的（A）取组标题行 R8。
FIELD_SPECS_L52: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("payable_name", "A", "editable", "text", "payableName", "债权人名称", ""),
    # ── B8:E8 未审数 ────────────────────────────────────────────────────
    ("beginning", "B", "editable", "amount", "beginning", "期初余额", _G["unadjusted"]),
    ("period_repayment", "C", "editable", "amount", "periodRepayment", "借方发生", _G["unadjusted"]),
    ("period_increase", "D", "editable", "amount", "periodIncrease", "贷方发生", _G["unadjusted"]),
    ("end_balance", "E", "formula", "amount", "endBalance", "期末余额", _G["unadjusted"]),
    # ── F8:G8 期初调整 ──────────────────────────────────────────────────
    ("prior_adjustment", "F", "editable", "amount", "priorAdjustment", "账项调整", _G["prior_adj"]),
    ("prior_reclass", "G", "editable", "amount", "priorReclass", "重分类调整", _G["prior_adj"]),
    # ── H8:I8 账项调整 ──────────────────────────────────────────────────
    ("aje_debit", "H", "editable", "amount", "ajeDebit", "借方发生", _G["aje"]),
    ("aje_credit", "I", "editable", "amount", "ajeCredit", "贷方发生", _G["aje"]),
    # ── J8:K8 重分类调整 ────────────────────────────────────────────────
    ("rje_debit", "J", "editable", "amount", "rjeDebit", "借方发生", _G["rje"]),
    ("rje_credit", "K", "editable", "amount", "rjeCredit", "贷方发生", _G["rje"]),
    # ── L8:O8 审定数 ────────────────────────────────────────────────────
    ("audited_beginning", "L", "formula", "amount", "auditedBeginning", "期初余额", _G["audited"]),
    ("audited_debit", "M", "formula", "amount", "auditedDebit", "借方发生", _G["audited"]),
    ("audited_credit", "N", "formula", "amount", "auditedCredit", "贷方发生", _G["audited"]),
    ("audited_ending", "O", "formula", "amount", "auditedEnding", "期末余额", _G["audited"]),
    # ── P8/Q8 减一年内到期（单列，无组）───────────────────────────────────
    ("minus_prior_due", "P", "editable", "amount", "minusPriorDue", "减：期初一年内到期长期应付款", ""),
    ("minus_end_due", "Q", "editable", "amount", "minusEndDue", "减：期末一年内到期长期应付款", ""),
    # ── R8:S8 披露审定数 ────────────────────────────────────────────────
    ("disclosure_beginning", "R", "formula", "amount", "disclosureBeginning", "期初余额", _G["disclosure"]),
    ("disclosure_ending", "S", "formula", "amount", "disclosureEnding", "期末余额", _G["disclosure"]),
)

#: 7 公式列的模板形态（负债余额口径，逐字实测 R11）。
FORMULA_TEMPLATES: Final[dict[str, str]] = {
    "E": "=B{row}-C{row}+D{row}",   # 期末余额（未审）= 期初-借+贷
    "L": "=B{row}+F{row}+G{row}",   # 审定期初
    "M": "=C{row}+H{row}+J{row}",   # 审定借方
    "N": "=D{row}+I{row}+K{row}",   # 审定贷方
    "O": "=L{row}-M{row}+N{row}",   # 审定期末
    "R": "=L{row}-P{row}",          # 披露期初审定
    "S": "=O{row}-Q{row}",          # 披露期末审定
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = ("E", "L", "M", "N", "O", "R", "S")

#: flat 账龄单组 5 桶（T~X）。叶子标签逐字实测（全角 `～`=U+FF5E / `２`=U+FF12），禁半角替换。
#: 组标题锚格 T8（T8:X8「期末到期日分析」合并区起始格）。flat_key 用 camelCase（成 HTML json 顶层键）。
AGING_GROUPS_L52: Final[tuple[AgingGroupSpec, ...]] = (
    AgingGroupSpec(
        json_prefix="",
        group_header_cell="T8",
        segments=(
            ("agingWithin6m", "T", "6个月以内"),
            ("aging6to12m", "U", "6-12月"),
            ("aging1to2y", "V", "1～2年"),
            ("aging2to3y", "W", "２～3年"),
            ("agingOver3y", "X", "3年以上"),
        ),
    ),
)


def _section_spec(
    *,
    table_key: str,
    template_suffix: str,
    uuid_col: str,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    section_value: str,
    error_label: str,
) -> RowTableSheetSpec:
    """各受管区共用的声明工厂（照 `phase5_g9_02_detail._section_spec`；L5 现为两区 R1/R2）。

    各区**只在**行号区间、`uuid_col`、`table_key`、`template_id` 后缀、`row_section_value`、
    `footer_row` 上不同；表头 / 字段集 / 公式列 / store 键 / 账龄声明完全相同 —— 抄多份必漂移。

    🔴 `template_id` 必须逐区不同（`L52R1/R2`；R24 其他段作静态骨架不建区，故无 R3）：
    instrumentation 的 definedName 按它命名，各区共用会争同一个 definedName
    （框架层 `build_instrumentation_payload_for_sheets` 有显式门）。
    `sheet_key` 反过来必须共享（否则契约层产出两个同 `excel_name` 的 sheet 条目）。
    """
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET,
        sheet_key=SHEET_KEY,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_GROUP_ROW,
        header_leaf_row=HEADER_LEAF_ROW,
        store_item_id=STORE_ITEM_ID,
        empty_payload=EMPTY_STORE_PAYLOAD,
        row_identity_key=ROW_IDENTITY_STORE_KEY,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_L52,
        formula_columns=FORMULA_COLUMNS,
        formula_templates=FORMULA_TEMPLATES,
        aging_layout=AgingLayout.flat,
        aging_groups=AGING_GROUPS_L52,
        footer_marker=FOOTER_MARKER,
        #: 各区小计/合计行真有 SUM 公式（区①16 / 区②23 / 区③的 footer 25=合计）。
        footer_carries_total_formula=True,
        #: footer 标签在 A 列（A16/A23 小计、A25 合计）。
        footer_search_column="A",
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD,
        row_section_value=section_value,
        #: 锚点取第 0 位 payable_name（债权人名称，真业务文本；无整数序号列）。
        ghost_row_anchor_index=0,
    )


#: 区① 售后租回业务形成的融资（模板区标题 R10；数据 R11:15；小计 R16）
SPEC_L52_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="long_term_payable_rows_r1",
    template_suffix="R1",
    uuid_col="AD",
    first_data_row=11,
    last_data_row=15,
    footer_row=16,
    section_value="saleLeaseback",
    error_label="L5-2 长期应付款明细表（售后租回）",
)

#: 区② 分期付款方式购入固定资产（模板区标题 R17；数据 R18:22；小计 R23）
SPEC_L52_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="long_term_payable_rows_r2",
    template_suffix="R2",
    uuid_col="AE",
    first_data_row=18,
    last_data_row=22,
    footer_row=23,
    section_value="installment",
    error_label="L5-2 长期应付款明细表（分期付款）",
)

# 🔴 区③「其他」R24:24 作模板静态骨架，不建 RowTableSheetSpec（用户裁决 A，见模块 docstring）。
#    uuid_col AF 一并不用（两区只用 AD/AE）。section 枚举 `other` 不对应任何受管区。

ALL_SPECS_L52: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_L52_R1,
    SPEC_L52_R2,
)

#: 契约 html_store 的 section 字段信息（经 provider 的 extra_review 带出，照 G9 契约形态）。
ROW_SECTION_VALUES: Final[tuple[str, ...]] = tuple(
    s.row_section_value for s in ALL_SPECS_L52
)

_HTML_STORE_NOTE: Final[str] = (
    "L5-2 长期应付款明细表存成 `L5-L5-2-rows` 的 remark JSON 数组（useL5Detail 的 "
    "JSON.stringify(rows)）；每行已有稳定 key（2026-10-01 把私有 Date.now+Math.random "
    "生成器换成平台共享 newRowIdentity('l52det')，已有 key 优先不重铸）。"
    "🔴 两个受管区（售后租回 saleLeaseback / 分期付款 installment）共用**同一个** "
    f"`{STORE_ITEM_ID}` 数组，行的区归属由 `section` 字段表达 —— 契约对应两条 tables[]"
    "（逐段不同 uuid_col AD/AE 与行区间），但 html_store.item_id 只有一条。"
    "R24「其他」段作模板静态骨架不进受管区（typography 门 BP-21 拒占位续行，用户裁决 A）。"
    "🔴 融资属性列（名义金额/折现率/现值/起止日/款项类型/币种/担保 + HTML 旧标量 "
    "unadjusted/aje/rje/audited + 债权人）退 html_only：继续喂 L5-5/L5-6/L5-7，不进契约、OO 侧不渲染。"
    "真库 `L5-L5-2-rows` 现算 0 行，零迁移负担。"
)
#: 🔴 **此常量是契约数据（`reviewed_basis` 字段，参与 canonical digest，被磁盘契约字节锁定）**，
#: 非 docstring —— 其中「三区 UUID 列 AD/AE/AF」为勘误前措辞，与同串前文「两受管区 R11:15·R18:22」
#: 内部不一致。改它会改动已交付 reviewed 契约 `l5.long_term_payables.json` 的 digest（超出「只改注释」范围），
#: 故保持原字节不动；终态两区结论以模块 docstring 与 `ALL_SPECS_L52`（现为两段）为准。
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 L/L5 长期应付款.xlsx 的 明细表L5-2（sha 09380626…）："
    "两级表头 R8 组（债权人名称/未审数/期初调整/账项调整/重分类调整/审定数/减一年内到期/披露审定数/"
    "期末到期日分析/关联方/发函/期后付款/合同索引号/备注）+ R9 叶子；两受管区 R11:15·R18:22"
    "（售后租回/分期付款），共享 store 键 L5-L5-2-rows + section 字段分区（uuid_col AD/AE）；"
    "区标题 A10/A17 + 小计 A16/A23 + 合计 A25（=SUM(B16,B23,B24) 非连续枚举）+ R24「其他」占位续行"
    "（A24='…' U+2026，typography 门 BP-21 拒受管，用户裁决 A）作静态骨架；"
    "7 公式列 E=B-C+D·L=B+F+G·M=C+H+J·N=D+I+K·O=L-M+N·R=L-P·S=O-Q（负债余额口径，全 11 输入行同形）；"
    "账龄 T~X 单组 5 桶 flat（6个月以内/6-12月/1～2年/２～3年/3年以上，叶子全角字符）；"
    "三区 UUID 列 AD/AE/AF（R11~R25 全空坐实）；受管表零裸 IF（bare_IF=0，不需 neutralize）；"
    "manifest 幻影码 L5L finder 零命中；amount_kind=balance（负债期末=期初-借+贷）；科目 2701。"
    "L5-3 未确认融资费用明细表（A 列 ='明细表L5-2'!A{n} 镜像引用）本轮不受管、作独立后续；"
    "真 OO 往返须专门断言 L5-2 受管区扩行不打坏 L5-3 的硬行号镜像引用。"
)
