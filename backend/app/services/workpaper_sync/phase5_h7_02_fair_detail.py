"""H7-2（**公允价值模式**）「生产性生物资产明细表」—— sheet 层薄声明。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

变体轴的另一半（成本模式见 `phase5_h7_02_cost_detail`）。两张各有独立持久化键
（`H7-2-cost-rows` / `H7-2-fair-rows`），必须同批交付。

═══ 几何（openpyxl 逐格实测）═══

`有效内容列 28（A..AB）`。
* **三级**表头 R9 / R10 / R11（成本模式那张是**四级** ⇒ 同一 entry 内两张层数不同）
* 数据区 **R12-R36（25 行）** —— 🔴 起始行比成本模式**早一行**（成本 R13）
* footer **R37**，`A37='合计'`，全列 SUM
* 数据行公式列 **11 个**（映射侧 0 个）
* UUID 列 **AC** = 28 + 1
* footer 之后 R38-R43 是 `其中：` + 五行 SUMPRODUCT 小计（标签取 `=底稿目录!A9..A13`）

两区块：
* **原值 D..P**（`D9`）：未审 D-I（D 期初余额 / E 本年增加 / F 增加方式 / G 本年减少 /
  H 减少方式 / I 期末余额）· 期初调整 J · 账项调整 K-L · 审定 M-P
* **公允价值变动 Q..X**（`Q9`）：未审 Q-S（Q 期初余额 / R 本年变动 / S 期末余额）·
  期初调整 T · 本期变动调整 U · 审定 V-X
* 尾部：`Y 期初净值`（`=M+V`）· `Z 期末净值`（`=P+X`）· `AA 是否有权属证明` ·
  `AB 是否抵押受限`

═══ 🔴 映射率 3/28（11%）—— 与 H3 公允模式同一个根因 ═══

`H7TabDetailFair.vue` 内联的 `FairDetailRow` 只有 **9 个**字段：

    rowId · assetName · assetType · quantity · fvLevel
    fvBegin · increase · decrease · fvChange · isSubtotal?

Tab 的列标签逐字是：`资产名称` · `类别` · `数量` · `公允价值层级` ·
`期初公允价值` · `本期增加` · `本期减少` · `公允价值变动损益` ·
`期末公允价值`（`auto-calc-col`，不落库）。

⇒ `fvBegin` 是**期初公允价值总额**，不是模板 `D` 那一列的「原值」；
`increase` / `decrease` 也是公允价值口径的增减，不是原值的本年增减。
与 H3 公允模式（`calcFairEndBalance` 把 change 加进 end）同族：模板把
「原值」与「公允价值变动」分成两块、净值才是两者之和（`Y=M+V` / `Z=P+X`），
而前端只有**一个含变动的公允总额**口径。把总额映进原值列 `D` 会让 `Y=M+V`
把公允变动**重复计一次**。

能对上的只有三格：`A 类别` · `C 名称` · `R 本年变动 ↔ fvChange`。

🔴 `S 期末余额`（`=Q+R`）也映不上：前端「期末公允价值」是展示期 auto-calc 不落库，
且它的口径是**含原值的总额**而 S 只是累计变动那一块。

═══ 覆盖闭合 ═══

**3 映射 + 25 template-only == 28 有效列**，并集连续 A..AB 无缺口。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H702_FAIR",
    "MANAGED_SHEET_H702_FAIR",
    "SHEET_KEY_H702_FAIR",
    "STORE_ITEM_ID_H702_FAIR",
    "ROW_IDENTITY_STORE_KEY_H702_FAIR",
    "FORMULA_TEMPLATES_H702_FAIR",
    "STORE_ONLY_FIELDS_H702_FAIR",
    "TEMPLATE_ONLY_COLUMNS_H702_FAIR",
    "DECLARED_COVERAGE_GAPS_H702_FAIR",
    "DERIVED_TOTAL_KEYS_H702_FAIR",
    "UNMANAGED_REGIONS_H702_FAIR",
    "EFFECTIVE_COLUMNS_H702_FAIR",
    "UUID_COL_H702_FAIR",
]

MANAGED_SHEET_H702_FAIR: Final[str] = "明细表（公允价值模式）H7-2"
TEMPLATE_ID_H702_FAIR: Final[str] = "H72F"
SHEET_KEY_H702_FAIR: Final[str] = "h702fair-managed"
ROWS_TABLE_KEY_H702_FAIR: Final[str] = "biological_assets_fair_detail_rows"

#: 按值取自 `H7TabDetailFair.vue#L230/#L248`（键内联在 Tab 里）。
STORE_ITEM_ID_H702_FAIR: Final[str] = "H7-2-fair-rows"
ROW_IDENTITY_STORE_KEY_H702_FAIR: Final[str] = "rowId"

HEADER_TOP_ROW_H702_FAIR: Final[int] = 9
HEADER_GROUP_ROW_H702_FAIR: Final[int] = 10
HEADER_LEAF_ROW_H702_FAIR: Final[int] = 11
#: 🔴 比成本模式早一行（成本 R13 / 公允 R12）—— 照抄会让 merge 越界写进表头。
FIRST_DATA_ROW_H702_FAIR: Final[int] = 12
LAST_DATA_ROW_H702_FAIR: Final[int] = 36
FOOTER_ROW_H702_FAIR: Final[int] = 37
FOOTER_MARKER_H702_FAIR: Final[str] = "合计"
EFFECTIVE_COLUMNS_H702_FAIR: Final[int] = 28
UUID_COL_H702_FAIR: Final[str] = "AC"

UNMANAGED_REGIONS_H702_FAIR: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 38,
        "last_row": 43,
        "kind": "category_subtotal_block",
        "note": (
            "A38='其中：'；R39-R43 为 "
            "=SUMPRODUCT(($A$12:$A$36=$A39)*(D$12:D$36)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A13。不受管、不比对、不覆盖。"
        ),
    },
)

DERIVED_TOTAL_KEYS_H702_FAIR: Final[tuple[str, ...]] = ()

#: 🔴 模板有列但 HTML 无对端 ⇒ **25 列**。原值整块在列的理由见 docstring
#: （前端 `fvBegin` 是含变动的公允总额，不是原值）。
TEMPLATE_ONLY_COLUMNS_H702_FAIR: Final[tuple[tuple[str, str], ...]] = (
    ("B", "生产性生物资产编号"),
    ("D", "期初余额"),
    ("E", "本年增加"),
    ("F", "增加方式"),
    ("G", "本年减少"),
    ("H", "减少方式"),
    ("I", "期末余额"),
    ("J", "期初调整"),
    ("K", "本期增加"),
    ("L", "本期减少"),
    ("M", "期初余额"),
    ("N", "本年增加"),
    ("O", "本年减少"),
    ("P", "期末余额"),
    ("Q", "期初余额"),
    ("S", "期末余额"),
    ("T", "期初调整"),
    ("U", "本期变动调整"),
    ("V", "期初余额"),
    ("W", "本年变动"),
    ("X", "期末余额"),
    ("Y", "期初净值"),
    ("Z", "期末净值"),
    ("AA", "是否有权属证明"),
    ("AB", "是否抵押受限"),
)

STORE_ONLY_FIELDS_H702_FAIR: Final[tuple[str, ...]] = (
    "quantity",
    "fvLevel",
    # 🔴 含累计公允变动的**总额**口径，不是模板 D 那一列的「原值」
    "fvBegin",
    "increase",
    "decrease",
    "isSubtotal",
)

DECLARED_COVERAGE_GAPS_H702_FAIR: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H7F-GAP-1",
        "title": "前端公允价值口径是**含变动的总额**，模板把「原值」与「公允价值变动」分两块",
        "template_columns": ["D", "E", "G", "I", "M", "N", "O", "P", "Q", "S", "V", "W", "X", "Y", "Z"],
        "store_fields": ["fvBegin", "increase", "decrease"],
        "why_not_mapped": (
            "`H7TabDetailFair.vue` 的列标签逐字是 `期初公允价值` / `本期增加` / `本期减少` / "
            "`公允价值变动损益` / `期末公允价值`(auto-calc) ⇒ `fvBegin` 是**期初公允价值总额**，"
            "`increase`/`decrease` 是公允价值口径的增减。模板把「原值 D..P」与"
            "「公允价值变动 Q..X」分成两块、净值才是两者之和（Y=M+V / Z=P+X）。"
            "把总额映进原值列会让 Y 把公允变动**重复计一次**。与 H3F-GAP-1 同族。"
        ),
        "what_still_syncs": "A 类别 / C 名称 / R 本年变动 ↔ fvChange。",
        "stop_and_report": (
            "要把总额口径拆回「原值 + 累计公允变动」两个独立字段，属前端模型变更 + 存量数据"
            "迁移（且拆分基准年的累计变动无从追溯）⇒ 审计域与数据治理裁决。"
        ),
        "owner": "审计业务方 / spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H7F-GAP-2",
        "title": "模板四段（按作用位置）与前端无审定口径",
        "template_columns": ["J", "K", "L", "T", "U"],
        "store_fields": [],
        "why_not_mapped": (
            "`FairDetailRow` 只有 9 个字段，**没有任何调整或审定字段**"
            "（H7 的审定数在 H7TabAdjudicationFair / H7-1 审定表，是另一张表）。"
            "模板的期初调整 / 账项调整 / 本期变动调整五列因此全无对端。"
        ),
        "resolution_verdict": "reject_widening_this_sheet",
        "stop_and_report": (
            "🔴 **审定四档不要补进本 sheet** —— 与 H5-GAP-1 / H7C-GAP-1 同一条否决："
            "公允侧审定数**前端已经有了**，在 `H7TabAdjudicationFair.vue`（键前缀 `H7-1-fair-`，"
            "带独立 TB 发布门）。往明细表再存一份 = 同一个量两处可改。"
            "⇒ 正解是让 `审定表（公允价值模式）H7-1` 进受管面；前置门 = 审定表引擎尚不存在"
            "（见 H7C-GAP-1 与 `test_deferred_imports_resolve.py` 的欠账清单）。"
            "🔴 本条**不与 H7F-GAP-1 同批**：GAP-1 是口径拆分（且拆分基准年的累计公允变动"
            "无从追溯，属存量数据信息丢失），本条只是「数据在另一张表」。混在一起会让"
            "可做的那半被不可做的那半拖住。"
        ),
        "owner": "框架层：审定表引擎 spec（承载 H7-1 公允侧）",
    },
    {
        "gap_id": "H7F-GAP-3",
        "title": "`AA 是否有权属证明` / `AB 是否抵押受限` 前端无字段",
        "template_columns": ["AA", "AB"],
        "store_fields": [],
        "why_not_mapped": (
            "`FairDetailRow` 没有权属/抵押字段（成本模式那张 Tab 也没有）。"
            "🔴 不得按名字近似映到 `fvLevel`（公允价值层级）—— 那是 FV 层级不是权属状态。"
        ),
        "stop_and_report": "需先确认这两列在 H7 是否应由明细表承载（H3 是另设 产权核对表H3-12）。",
        "owner": "审计业务方",
    },
)

#: 3 个受管字段。
FIELD_SPECS_H702_FAIR: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("asset_type", "A", "editable", "text", "assetType", "生产性生物资产类别", ""),
    ("asset_name", "C", "editable", "text", "assetName", "生产性生物资产名称", ""),
    ("fv_change_current", "R", "editable", "amount", "fvChange", "本年变动", "Q10"),
)

#: 🔴 **空** —— 11 个公式列一个都没进 `field_specs`。
FORMULA_TEMPLATES_H702_FAIR: Final[dict[str, str]] = {}

SPEC_H702_FAIR: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H702_FAIR,
    sheet_key=SHEET_KEY_H702_FAIR,
    table_key=ROWS_TABLE_KEY_H702_FAIR,
    template_id=TEMPLATE_ID_H702_FAIR,
    table_name=f"GT_{TEMPLATE_ID_H702_FAIR}_ROWS",
    uuid_col=UUID_COL_H702_FAIR,
    first_data_row=FIRST_DATA_ROW_H702_FAIR,
    last_data_row=LAST_DATA_ROW_H702_FAIR,
    footer_row=FOOTER_ROW_H702_FAIR,
    header_group_row=HEADER_TOP_ROW_H702_FAIR,
    header_leaf_row=HEADER_LEAF_ROW_H702_FAIR,
    store_item_id=STORE_ITEM_ID_H702_FAIR,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H702_FAIR,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H702_FAIR,
    formula_columns=tuple(FORMULA_TEMPLATES_H702_FAIR),
    formula_templates=FORMULA_TEMPLATES_H702_FAIR,
    footer_marker=FOOTER_MARKER_H702_FAIR,
    error_label="H7-2（公允价值模式）生产性生物资产明细表",
)
