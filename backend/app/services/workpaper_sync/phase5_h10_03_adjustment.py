"""H10-3「资产处置损益调整分录汇总表」—— sheet 层薄声明。

spec: `h2-h6-h10-pilot-cross-reference-lanes`

═══ 🔴 为什么受管 sheet 是 H10-3 而不是 slice 声明的「明细表H10-2」═══

slice 把本 entry 的 `primary_table` 记成 `明细表H10-2 ↔ H10-detail-rows`
（依据是 `A7='项目'`）。**openpyxl + 前端双向实测推翻了这个配对**（H 循环第 6 条实测反驳）：

* 模板 `明细表H10-2` 是 **9 类固定行（R8:R16，按被处置资产类别）× 12 个月（B..M）**
  的月度矩阵，本期合计 `N=SUM(B:M)`、账项调整 `O`、重分类调整 `P`、期末审定
  `Q=N+O+P`、上年同期 `U/V/W`、结构比 `T/Y`、增长比 `Z`。
* 前端 `H10-detail-rows`（`useH10Detail.ts`）是**逐单项资产台账**：25 个字段
  （assetName / assetType / sourceWp / originalCost / accumulatedDepreciation /
  disposalIncome / disposalGainLoss / approvalDoc / …），行可增删、身份是 `id`。
* 🔴 **前端全库零月度建模**：按值 grep `1月|月度|monthly|month|各月` 在
  `workpaper/{h10/**, composables/*H10*, composables/h10*}` 下 **零命中**。

两者行身份不同类（资产**类别** vs **单项**资产）、列面零交集 ⇒ 强行配对只能造两种错：
把逐资产金额塞进某个月（时点造假），或写进 `N`（毁掉 `=SUM(B:M)` 公式，Excel 重算成 0）。
两者都是静默错数，与 H5 拒绝映 `V 折耗期末数` 同一条纪律。

而 `调整分录汇总H10-3` ↔ `H10-adjustment-rows`（`useH10Adjustment.ts`）是**逐字段真对齐**
的动态行表，映射率 **6/10（60%）是全 H 循环最高档**。

═══ 几何（openpyxl 逐格实测）═══

`有效内容列 10（A..J）`，`max_column=10`（无空列尾巴）。

* **单级**表头 **R5**（`header_rows=1`）—— 🔴 H 循环前 8 条全是两级/三级/四级表头，
  照抄 `header_group_row`/`header_leaf_row` 会让 anchor 落在 R4（标题区）。
* 数据区 **R6-R18（13 行）**，实测 **13 行全空**（模板只预画样式，无预填行标签）
* footer **R19**，`A19='合计'`，仅 `G19='=SUM(G6:G18)'` / `H19='=SUM(H6:H18)'`
  两格有公式（不是全列 SUM —— 本表只有两个金额列）
* **数据行公式列 0 个** ⇒ `FORMULA_TEMPLATES` 是空字典
* UUID 列 **K** = 10 + 1
* 数据区**零合并域**（全册只有 `A1:J1` / `A2:J2` 两个标题合并）
* R20-R21 是 footer 之下的未受管区（借贷差额校验 + 提示文字），见 `UNMANAGED_REGIONS`

═══ 映射（6/10）═══

| 列 | 表头 | store 字段 | 模式 |
|---|---|---|---|
| A | 调整事项说明 | `summary` | editable |
| B | 类别（账项调整AJE/重分类调整RJE/其他） | `entryType` | **auto_source** |
| C | 报表项目 | — | template-only |
| D | 科目名称 | `accountName` | editable |
| E | 附注项目 | — | template-only |
| F | 对方科目 | — | template-only |
| G | 借方调整金额 | `debitAmount` | editable |
| H | 贷方调整金额 | `creditAmount` | editable |
| I | 索引 | — | template-only |
| J | 备注 | `remark` | editable |

═══ 🔴 为什么 `B 类别` 必须是 `auto_source` 而不是 `editable` ═══

前端 `entryType` 只有**二值** —— `useH10Adjustment.normalizeEntry` 逐字是
`entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE'`。而模板 B 列表头写的是
**三值**「账项调整AJE / 重分类调整RJE / **其他**」。

若声明 `editable`：审计师在 OO 里把 B 填成「其他」⇒ 回到 HTML 被**静默归一成 `AJE`**
⇒ 下一次 HTML 保存又把 `AJE` 写回 Excel ⇒ 用户填的值被无声换掉。这正是 H5 拒绝映
`V 折耗期末数` 的同一类缺陷。

`auto_source` 的语义（既有先例：`phase5_f3_05_overdue.term_days` /
`phase5_f1_05_long_term.audited_balance` / `phase5_g11_02_detail` 的两个占比列）是
「HTML 侧权威、Excel 侧受保护」：值照样写进 Excel 给审计师看，但那一格在 OO 里不可编辑
⇒ 三值里的「其他」根本进不来，归一化缺陷无从触发。

🔴 `auto_source` 要求模板该格**无公式**（`excel_materialize` 对 auto_source 遇公式抛
`ProtectedRegionWriteError`）—— B6:B18 实测全空，满足。

═══ 覆盖闭合 ═══

**6 映射 + 4 template-only == 10 有效列**，并集连续 A..J 无缺口、无重复。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H1003",
    "MANAGED_SHEET_H1003",
    "SHEET_KEY_H1003",
    "STORE_ITEM_ID_H1003",
    "ROW_IDENTITY_STORE_KEY_H1003",
    "FORMULA_TEMPLATES_H1003",
    "STORE_ONLY_FIELDS_H1003",
    "TEMPLATE_ONLY_COLUMNS_H1003",
    "DECLARED_COVERAGE_GAPS_H1003",
    "DERIVED_TOTAL_KEYS_H1003",
    "UNMANAGED_REGIONS_H1003",
    "EFFECTIVE_COLUMNS_H1003",
    "UUID_COL_H1003",
    "FIELD_SPECS_H1003",
]

MANAGED_SHEET_H1003: Final[str] = "调整分录汇总H10-3"
TEMPLATE_ID_H1003: Final[str] = "H103"
SHEET_KEY_H1003: Final[str] = "h1003-managed"
ROWS_TABLE_KEY_H1003: Final[str] = "asset_disposal_adjustment_rows"

#: 按值取自 `useH10Adjustment.ts` 的 `ITEM_ID_ROWS`（模块常量，**字面量**不是拼接）。
STORE_ITEM_ID_H1003: Final[str] = "H10-adjustment-rows"
ROW_IDENTITY_STORE_KEY_H1003: Final[str] = "rowId"

#: 🔴 **单级**表头（H 循环唯一一张）—— 用 `header_row` 而非 group/leaf 一对。
HEADER_ROW_H1003: Final[int] = 5
FIRST_DATA_ROW_H1003: Final[int] = 6
LAST_DATA_ROW_H1003: Final[int] = 18
FOOTER_ROW_H1003: Final[int] = 19
FOOTER_MARKER_H1003: Final[str] = "合计"
EFFECTIVE_COLUMNS_H1003: Final[int] = 10
UUID_COL_H1003: Final[str] = "K"

UNMANAGED_REGIONS_H1003: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 20,
        "last_row": 21,
        "kind": "balance_check_and_hint",
        "note": (
            "A20='借贷差额（应为0）'，G20='=G19-H19'、"
            "H20='=IF(G20=0,\"平衡\",\"不平衡\")'（全册 46 个含 IF 公式格之一）；"
            "A21 是提示文字。footer 之下、不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 聚合副本（HC-6）：`useH10Adjustment.syncWriteback` 把本表行聚合成
#: `{currentAje, currentRje}` 写进 `H10-adj-overlay`，并据此 patch `H10-adj-rows`
#: （H10-1 审定表的 store）。它们是**派生**的，不是第二份事实：
#:   · roundtrip 比对必须排除（否则 OO 侧没有对应格 ⇒ 判成「HTML 侧多出内容」）；
#:   · 重算责任方是前端 `syncWriteback`，**不是**本 provider。
DERIVED_TOTAL_KEYS_H1003: Final[tuple[str, ...]] = (
    "H10-adj-overlay",
)

#: 模板有列但 HTML 无对端 ⇒ **4 列**。
TEMPLATE_ONLY_COLUMNS_H1003: Final[tuple[tuple[str, str], ...]] = (
    ("C", "报表项目"),
    ("E", "附注项目"),
    ("F", "对方科目"),
    ("I", "索引"),
)

#: HTML 有字段但模板无列。
STORE_ONLY_FIELDS_H1003: Final[tuple[str, ...]] = (
    # 展示序号（`seq`）—— 不是行身份（身份是 rowId），模板也没有序号列
    "seq",
    # 🔴 模板 H10-3 **没有日期列**（H10-4 检查表才有 `B 日期`）
    "date",
    # 前端恒填 '6115'，模板只有 `D 科目名称` 没有科目编码列
    "accountCode",
    "preparedBy",
)

DECLARED_COVERAGE_GAPS_H1003: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H10-GAP-1",
        "title": "模板「明细表H10-2」是 9 类×12 月矩阵，前端零月度建模 ⇒ 整张表不可受管",
        "template_columns": [],
        "template_sheet": "明细表H10-2",
        "store_fields": ["H10-detail-rows", "H10-adj-rows"],
        "why_not_mapped": (
            "模板 `明细表H10-2` 的行是**被处置资产类别**（R8:R16 九类固定行，标签逐字与前端 "
            "`H10_ADJUDICATION_ITEMS` 前 9 项一致），列是 **1月..12月**（B..M）+ 本期合计 "
            "`N=SUM(B:M)` + 账项调整 `O` + 重分类调整 `P` + 期末审定 `Q=N+O+P` + "
            "上年同期三列 `U/V/W`。前端两个候选载体都对不上整张表："
            "①`H10-detail-rows` 是**逐单项资产台账**（25 字段、行可增删、身份 `id`），"
            "行身份与「资产类别」不同类；"
            "②`H10-adj-rows`（H10-1 审定表 store）行身份对得上（9 个 rowKey），"
            "`currentAje/currentRje/priorUnadjusted/priorAje/priorRje` 五个字段也分别对上 "
            "`O/P/U/V/W` 五列，但 **`currentUnadjusted` 无处可落** —— 模板该值在 "
            "`N=SUM(B8:M8)`，是 12 个月分月单元格的和，而前端按值 grep "
            "`1月|月度|monthly|各月` 在全部 H10 组件/composable 下**零命中**。"
            "写进 `N` 会毁掉公式且 Excel 按空月份重算成 0（静默清零）；分摊进某个月是时点造假。"
        ),
        "what_still_syncs": (
            "本 entry 改以 `调整分录汇总H10-3 ↔ H10-adjustment-rows` 为受管表（6/10 映射，"
            "全 H 最高档）。明细表H10-2 维持 legacy 只读 OO 视图。"
        ),
        "stop_and_report": (
            "要让 明细表H10-2 进受管面，需先裁决两件事：①前端是否补 9 类×12 月的月度载体"
            "（属前端模型新增 + 审计口径确认「分月发生额」是否必填）；②若只同步 O/P/U/V/W "
            "五列而留空 B..M，materialize 出的册子里「本期合计/期末审定」会显示 0 —— "
            "那是可见缺口不是静默错数，但是否可接受需业务方拍板。"
        ),
        "owner": "审计业务方 / spec h2-h6-h10-pilot-cross-reference-lanes 后续任务",
    },
    {
        "gap_id": "H10-GAP-2",
        "title": "`B 类别` 走 auto_source 而非 editable —— 前端枚举只有二值，模板是三值",
        "template_columns": ["B"],
        "store_fields": ["entryType"],
        "why_not_mapped": (
            "不是「未映射」而是**降级为单向**：`useH10Adjustment.normalizeEntry` 逐字是 "
            "`entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE'` ⇒ 任何非 `'RJE'` 的输入"
            "都被归一成 `'AJE'`。模板 B 列表头是三值「账项调整AJE/重分类调整RJE/**其他**」。"
            "声明 editable 会让审计师在 OO 填的「其他」被静默换成 AJE 并回写覆盖。"
            "改 `auto_source` 后该格在 OO 侧受保护（值照写、不可编辑），归一化缺陷无从触发。"
        ),
        "what_still_syncs": "HTML → Excel 单向：AJE/RJE 照样写进 B 列供审计师阅读。",
        "stop_and_report": (
            "要恢复双向需前端把 `entryType` 扩成三值枚举（含 `OTHER`）并确认「其他」类调整"
            "在 `aggregateH10AdjustmentAjeRje` 里的归集口径（当前只聚合 AJE/RJE 两档，"
            "新增第三档会改变回写到 H10-1 的金额）。"
        ),
        "owner": "审计业务方 / 前端 H10 模型",
    },
    {
        "gap_id": "H10-GAP-3",
        "title": "`C 报表项目` / `E 附注项目` / `F 对方科目` / `I 索引` 前端无字段",
        "template_columns": ["C", "E", "F", "I"],
        "store_fields": [],
        "why_not_mapped": (
            "`H10AdjustmentEntry` 只有 11 个字段，这四列一个都没有。"
            "🔴 `F 对方科目` 尤其不得近似映到 `accountName` —— 前端代码里 "
            "`useH10Adjustment.syncWriteback` 逐字写着 "
            "`counterAccountCode: '', // TODO: 分录目前无对方科目字段，靠摘要推断`，"
            "即「对方科目」在前端**确实缺失**且已被自己登记为 TODO。把 `accountName`"
            "（本方科目，恒为『资产处置损益』）映进 F 会让对方科目全表显示成本方科目。"
            "`I 索引` 也不得映 `preparedBy`（编制人 ≠ 索引号）。"
        ),
        "stop_and_report": (
            "补这四个字段属前端模型变更；其中 `F 对方科目` 是分录完整性的必要字段"
            "（借贷双方缺一方无法复核），建议与集中调整分录管理一并解决。"
        ),
        "owner": "前端 H10 模型 / 集中调整分录模块",
    },
    {
        "gap_id": "H10-GAP-4",
        "title": "OO 侧改了 G/H 金额后，向 H10-1 审定表的再聚合需由前端重跑",
        "template_columns": ["G", "H"],
        "store_fields": ["H10-adj-overlay", "H10-adj-rows"],
        "why_not_mapped": (
            "不是列缺口而是**链路缺口**：本表金额经 `syncWriteback` 聚合成 AJE/RJE 净额写进 "
            "`H10-adj-overlay` 并 patch `H10-adj-rows`（H10-1 审定表 store）。"
            "原实现只在 HTML 侧 `persist()` 里触发 ⇒ OO 侧改完切回来，H10-3 行是新的、"
            "H10-1 审定数还是旧的。"
        ),
        "what_still_syncs": (
            "本轮已在 `useH10Adjustment` 加**按值守卫的** watch：`H10-adjustment-rows` 变化后"
            "重算聚合，只有聚合结果与 `H10-adj-overlay` 现值**不同**时才重跑 syncWriteback "
            "⇒ HTML 侧编辑不会重复触发（persist 已写过、值相等直接 no-op），"
            "OO 侧带回新金额时恰好触发一次。"
        ),
        "stop_and_report": (
            "彻底解法是把聚合下沉到后端（随 WORKPAPER_SAVED 事件重算），"
            "属跨模块编排，不在本 lane 范围。"
        ),
        "owner": "spec h2-h6-h10-pilot-cross-reference-lanes 后续任务",
    },
)

#: 6 个受管字段（顺序即 `managed_field_specs()` 输出顺序，零回归门钉住）。
#:
#: 🔴 `ghost_row_anchor_index` 用默认 0（`A 调整事项说明 ↔ summary`）：它正是前端新增行时
#:    必填的那个字段（`addRow` 用 ElMessageBox.prompt 要摘要，空则不建行）⇒ 天然适合当
#:    幽灵行锚点。
FIELD_SPECS_H1003: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("adjustment_summary", "A", "editable", "text", "summary", "调整事项说明", ""),
    # 🔴 auto_source 而非 editable —— 理由见模块 docstring 与 H10-GAP-2
    (
        "entry_type",
        "B",
        "auto_source",
        "text",
        "entryType",
        "类别（账项调整AJE/重分类调整RJE/其他）",
        "",
    ),
    ("account_name", "D", "editable", "text", "accountName", "科目名称", ""),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方调整金额", ""),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方调整金额", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

#: 🔴 **空** —— 数据区 R6:R18 实测零公式（footer R19 的两个 SUM 与 R20 的差额校验
#: 都在数据区之外，由 footer_anchor / UNMANAGED_REGIONS 分别表达）。
FORMULA_TEMPLATES_H1003: Final[dict[str, str]] = {}

SPEC_H1003: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H1003,
    sheet_key=SHEET_KEY_H1003,
    table_key=ROWS_TABLE_KEY_H1003,
    template_id=TEMPLATE_ID_H1003,
    table_name=f"GT_{TEMPLATE_ID_H1003}_ROWS",
    uuid_col=UUID_COL_H1003,
    first_data_row=FIRST_DATA_ROW_H1003,
    last_data_row=LAST_DATA_ROW_H1003,
    footer_row=FOOTER_ROW_H1003,
    #: 🔴 单级表头走 `header_row`；group/leaf 一对留空（传了会让 header_rows 算成 2）
    header_row=HEADER_ROW_H1003,
    store_item_id=STORE_ITEM_ID_H1003,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H1003,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H1003,
    formula_columns=tuple(FORMULA_TEMPLATES_H1003),
    formula_templates=FORMULA_TEMPLATES_H1003,
    footer_marker=FOOTER_MARKER_H1003,
    error_label="H10-3 资产处置损益调整分录汇总表",
)
