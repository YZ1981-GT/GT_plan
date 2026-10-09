"""H8-2「使用权资产、累计折旧及减值准备明细表」—— sheet 层薄声明。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`
现算底账：同 spec 的 `evidence/h2-h4-h8-h10-mapping-facts.md` §3

═══ 为什么 H8 是剩余最规整的一条 ═══

它是全 H 循环**唯一 58 列全部 1:1 映射、零 `template_only_columns`** 的主表：
前端 `H8DetailRow` 的 `cost*` / `dep*` / `impair*` 三族命名与模板三大区块**逐列同构**，
连「本期租入 / 租赁负债调整 / 其他增加 / 转租赁为融资租赁 / 转让或持有待售 / 其他减少」
这六个明细去向都一一对上。⇒ **无需任何审计域裁决**（对比 H10 与 H3/H5/H7 的结构性不匹配）。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H8 使用权资产.xlsx`（465,476 B，**全 H 最大**）· 20 sheets ·
本 sheet `max_row=79` / `max_column=58`，**有效内容列 58（A..BF）** —— 与 max_column 相等。

* **四级**表头 **R8 / R9 / R10 / R11**（`header_rows = 4`）
* 数据区 **R12-R31（20 行）** —— 全 H 最长数据区（H9/H6 各 5 行、H4 16 行）
* footer **R32**，`A32='合计'`，`D32..BF32` 为 `=SUM(x12:x31)`
* 数据行公式列 **17 个**
* UUID 列 **BG** = 有效内容列（58）+ 1（HC-13）

🔴 **footer 之后还有不受管区域 R33-R38**（与 H4 同族缺陷形态）：
`A33='其中：'` + R34-R38 五行按 `=SUMPRODUCT(($A$12:$A$31=$A34)*(D$12:D$31))` 做的
**按类别小计**，行标签取 `=底稿目录!A9..A13`。不显式登记，merge 会把它们当数据行覆盖。
🔴 与 H4 的差异：H8 的 SUMPRODUCT 按 **A 列（使用权资产类别）**分组，H4 按 **B 列**分组 ——
两者列位不同，守卫不能共用同一个写死的分组列。

═══ 四大区块（表头合并区逐字实测，51 个合并域）═══

* `A8:A11` 使用权资产类别 · `B8:B11` 名称 · `C8:C11` 编号
* **使用权资产原值 `D8:V8`**
  - `D9:D11` 期初数 · 未审数 `E9:K9`（增加 E-G / 减少 H-J / 期末 K）
  - `L9:L11` 期初调整 · 账项调整 `M9:R9`（增加 M-O / 减少 P-R）
  - 审定数 `S9:V9`（期初 S / 增加 T / 减少 U / 期末 V）
* **累计折旧 `W8:AM8`**
  - `W9:W11` 期初数 · 未审数 `X9:AC9`（增加 X-Y / 减少 Z-AB / 期末 AC）
  - `AD9:AD11` 期初调整 · 账项调整 `AE9:AI9`（增加 AE-AF / 减少 AG-AI）
  - 审定数 `AJ9:AM9`（期初 AJ / 增加 AK / 减少 AL / 期末 AM）
* **减值准备 `AN8:BD8`** —— 与累计折旧同构
  - `AN9:AN11` 期初数 · 未审数 `AO9:AT9` · `AU9:AU11` 期初调整 ·
    账项调整 `AV9:AZ9` · 审定数 `BA9:BD9`
* **审定净值 `BE8:BF9`**：BE 期初净值 · BF 期末净值
  🔴 这两列是**审定**口径（`BE=S-AJ-BA` / `BF=V-AM-BD`）⇒ 映 `netBeginAud`/`netEndAud`。
  前端的 `netBeginUnadj` / `netEndUnadj` 模板**无列** ⇒ store-only。
  按名字直觉把 BE/BF 映到 unadj 会把审定净值写进未审字段。

🔴 **增加/减少两族的内部去向数不同，不得跨区块复制**：
原值块是 **3 增 3 减**（本期租入/租赁负债调整/其他增加 · 转租赁/转让持有待售/其他减少），
折旧与减值块是 **2 增 3 减**（本期计提/其他增加 · 转租赁/转让持有待售/其他减少）。
把原值块的 3 增照抄到折旧块会多映一列、整块列位右移。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H802",
    "MANAGED_SHEET_H802",
    "SHEET_KEY_H802",
    "STORE_ITEM_ID_H802",
    "ROW_IDENTITY_STORE_KEY_H802",
    "FORMULA_TEMPLATES_H802",
    "STORE_ONLY_FIELDS_H802",
    "TEMPLATE_ONLY_COLUMNS_H802",
    "DERIVED_TOTAL_KEYS_H802",
    "SIBLING_TABLE_KEYS_H802",
    "UNMANAGED_REGIONS_H802",
    "INTRA_ENTRY_CONSUMERS_H802",
    "CROSS_ENTRY_CONSUMERS_H802",
    "EFFECTIVE_COLUMNS_H802",
    "UUID_COL_H802",
]

MANAGED_SHEET_H802: Final[str] = "明细表H8-2"
TEMPLATE_ID_H802: Final[str] = "H82"
SHEET_KEY_H802: Final[str] = "h802-managed"
ROWS_TABLE_KEY_H802: Final[str] = "right_of_use_assets_detail_rows"

#: 按值取自 `useH8Detail.ts` 的 `ROWS_KEY`，不按 sheet 号推演。
#: 🔴 HC-8 冻结键（见 `CROSS_ENTRY_CONSUMERS_H802`）。
STORE_ITEM_ID_H802: Final[str] = "H8-2-rows"

#: 行身份 `row-${Date.now().toString(36)}-${Math.random()...}` ⇒ HC-7 族 A。
#: 🔴 slice 标 `row_identity_is_positional=True` 是**过期快照** —— 下标身份
#:    （`GtH8RightOfUseAssets.vue#578` 的 `seed-${i}`）已在 commit 91933bd68 改为
#:    按科目编码的 `buildHSeedRowId`。判据按现状复核。
ROW_IDENTITY_STORE_KEY_H802: Final[str] = "rowId"

HEADER_TOP_ROW_H802: Final[int] = 8
HEADER_LEAF_ROW_H802: Final[int] = 11
FIRST_DATA_ROW_H802: Final[int] = 12
LAST_DATA_ROW_H802: Final[int] = 31
FOOTER_ROW_H802: Final[int] = 32
FOOTER_MARKER_H802: Final[str] = "合计"
EFFECTIVE_COLUMNS_H802: Final[int] = 58
UUID_COL_H802: Final[str] = "BG"

#: 🔴 footer 之后的**不受管区域**（同 H4 的族，但分组列不同）。
UNMANAGED_REGIONS_H802: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 33,
        "last_row": 38,
        "kind": "category_subtotal_block",
        "group_by_column": "A",
        "note": (
            "A33='其中：'；R34-R38 为 "
            "=SUMPRODUCT(($A$12:$A$31=$A34)*(D$12:D$31)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A13。🔴 分组列是 **A（使用权资产类别）**，"
            "H4 的同族区块按 **B** 分组 —— 守卫不得共用写死的分组列。"
            "不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 **空** —— 58 个模板列**全部**有 store 字段（全 H 唯一零 template-only 的主表）。
TEMPLATE_ONLY_COLUMNS_H802: Final[tuple[tuple[str, str], ...]] = ()

#: HTML 有字段但模板无列 ⇒ store-only，不映射任何格。
STORE_ONLY_FIELDS_H802: Final[tuple[str, ...]] = (
    # 租赁合同要素（模板本表不设列，在 H8-4/H8-5 等表）
    "contractNo",
    "lessor",
    "leaseType",
    "startDate",
    "endDate",
    "leaseTermMonths",
    # 初始计量（在 H8-6 初始及后续计量表）
    "h9InitialAmount",
    "directCost",
    "incentive",
    "initialAmount",
    # 🔴 未审净值两列：模板 BE/BF 是**审定**口径 ⇒ 未审净值无处可映
    "netBeginUnadj",
    "netEndUnadj",
    # 其它
    "modificationAmount",
    "terminationDate",
    "remark",
    # 旧命名遗留的折旧三字段（与 dep* 族重复，前端自用）
    "accDepBegin",
    "depCurrentPeriod",
    "accDepEnd",
    "netValue",
)

#: 🔴 HC-6 派生合计副本：与主表同批写出，不参与 roundtrip 比对。
DERIVED_TOTAL_KEYS_H802: Final[tuple[str, ...]] = ("H8-2-initial-total",)

#: 🔴 同模块但**另一张表**的键 —— 不是本表的合计副本，也不在本轮受管面。
#: 登记它们是为了让后续批次不把它们误当派生键跳过。
SIBLING_TABLE_KEYS_H802: Final[tuple[str, ...]] = (
    # H8-1 审定表（7 键，全在 useH8Detail.ts）
    "H8-1-cost-audited-total",
    "H8-1-dep-audited-total",
    "H8-1-impair-audited-total",
    "H8-1-net-audited",
    "H8-1-cost-rows",
    "H8-1-dep-rows",
    "H8-1-impair-rows",
    # H8-8 折旧测算表
    "H8-8-dep-rows",
    # TB 核对种子键（不是发布门 —— H8 无 publishToTb）
    "H8-adj-tb-amount-ending",
    "H8-adj-tb-amount-opening",
)

#: 🔴 HC-8 键名冻结依据 —— **11 个 entry 内消费方**（按值 grep 实测，非跨 entry）。
#:
#: 与 H9/H6 的冻结理由不同：`H9-2-rows` / `H6-2-rows` 是被**别的 entry** 消费
#: （H8 侧读 H9、H10/H1 侧读 H6），本键是**H8 自己**的 11 处扇出。冻结力度更强 ——
#: 改名要同步改 11 个文件，且其中 `useH8Adjudication` / `useH8CrossSheet` /
#: `useH8Disclosure` 三处是审定勾稽与附注推送的入口。
#:
#: 🔴 早先按直觉写成 `useH9CrossSheet.ts` + `h8DisclosureSyncPayload.ts` 是错的：
#:    前者按值 grep **零命中** `H8-2-rows`（H8↔H9 的联动方向是 H8 读 `H9-2-rows`，
#:    见 `useH8DisposalCheck.ts` 的 `H9_ROWS_KEY`），后者也不引用本键。
#:    这份清单是 grep 结果，不是推测。
INTRA_ENTRY_CONSUMERS_H802: Final[tuple[str, ...]] = (
    "GtH8RightOfUseAssets.vue",       # 宿主：种子预填（BP-5/BP-6 修复点）
    "useH8Detail.ts",                 # 定义方（ROWS_KEY）
    "useH8Adjudication.ts",           # 审定勾稽 + 非标类别清单
    "useH8CrossSheet.ts",             # 跨 sheet 明细行来源
    "useH8Disclosure.ts",             # 附注按类别汇总 + pullFromSources
    "useH8DisposalCheck.ts",          # 处置检查（同文件另读 H9-2-rows）
    "useH8Depreciation.ts",           # 折旧测算带入入账值与起止日
    "useH8Impairment.ts",             # 减值测算
    "useH8LeaseModification.ts",      # 租赁变更回写 modificationAmount
    "useH8Recoverable.ts",            # 可收回金额测试
    "useH8RelatedParty.ts",           # 关联方带入去重
    "useH8LeaseIdentification.ts",    # 租赁识别
)

#: 向后兼容别名：既有通用判据按 `CROSS_ENTRY_CONSUMERS_*` 取冻结依据。
#: 🔴 本键的消费方全在 entry 内 ⇒ 别名指向同一元组，但**语义是 intra-entry**，
#:    读判据时不要据此以为 H8-2-rows 被别的 entry 消费。
CROSS_ENTRY_CONSUMERS_H802: Final[tuple[str, ...]] = INTRA_ENTRY_CONSUMERS_H802

#: 58 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序 A→BF；`header_text` 取该列**最下层**非空表头；
#: `group_header_cell` 取其上一层的合并起始格（纵向合并列留空）。
#: `json_key` 逐字取 `useH8Detail.H8DetailRow`。
FIELD_SPECS_H802: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("category", "A", "editable", "text", "category", "使用权资产类别", ""),
    ("asset_name", "B", "editable", "text", "assetName", "使用权资产名称", ""),
    ("asset_no", "C", "editable", "text", "assetNo", "使用权资产编号", ""),
    # ══ 使用权资产原值 D..V（3 增 3 减）══════════════════════════════════════
    ("cost_begin_unadj", "D", "editable", "amount", "costBeginUnadj", "期初数", "D8"),
    ("cost_inc_lease", "E", "editable", "amount", "costIncLease", "本期租入", "E10"),
    ("cost_inc_reval", "F", "editable", "amount", "costIncReval", "租赁负债调整", "E10"),
    ("cost_inc_other", "G", "editable", "amount", "costIncOther", "其他增加", "E10"),
    ("cost_dec_sublease", "H", "editable", "amount", "costDecSublease", "转租赁为融资租赁", "H10"),
    ("cost_dec_disposal", "I", "editable", "amount", "costDecDisposal", "转让或持有待售", "H10"),
    ("cost_dec_other", "J", "editable", "amount", "costDecOther", "其他减少", "H10"),
    ("cost_end_unadj", "K", "formula", "amount", "costEndUnadj", "期末数", "E9"),
    ("cost_open_adj", "L", "editable", "amount", "costOpenAdj", "期初调整", ""),
    ("cost_aje_inc_lease", "M", "editable", "amount", "costAjeIncLease", "本期租入", "M10"),
    ("cost_aje_inc_reval", "N", "editable", "amount", "costAjeIncReval", "租赁负债调整", "M10"),
    ("cost_aje_inc_other", "O", "editable", "amount", "costAjeIncOther", "其他增加", "M10"),
    ("cost_aje_dec_sublease", "P", "editable", "amount", "costAjeDecSublease", "转租赁为融资租赁", "P10"),
    ("cost_aje_dec_disposal", "Q", "editable", "amount", "costAjeDecDisposal", "转让或持有待售", "P10"),
    ("cost_aje_dec_other", "R", "editable", "amount", "costAjeDecOther", "其他减少", "P10"),
    ("cost_begin_aud", "S", "formula", "amount", "costBeginAud", "期初数", "S9"),
    ("cost_inc_aud", "T", "formula", "amount", "costIncAud", "本期增加", "S9"),
    ("cost_dec_aud", "U", "formula", "amount", "costDecAud", "本期减少", "S9"),
    ("cost_end_aud", "V", "formula", "amount", "costEndAud", "期末数", "S9"),
    # ══ 累计折旧 W..AM（2 增 3 减）══════════════════════════════════════════
    ("dep_begin_unadj", "W", "editable", "amount", "depBeginUnadj", "期初数", "W8"),
    ("dep_prov_unadj", "X", "editable", "amount", "depProvUnadj", "本期计提", "X10"),
    ("dep_other_inc_unadj", "Y", "editable", "amount", "depOtherIncUnadj", "其他增加", "X10"),
    ("dep_dec_sublease", "Z", "editable", "amount", "depDecSublease", "转租赁为融资租赁", "Z10"),
    ("dep_dec_disposal", "AA", "editable", "amount", "depDecDisposal", "转让或持有待售", "Z10"),
    ("dep_other_dec_unadj", "AB", "editable", "amount", "depOtherDecUnadj", "其他减少", "Z10"),
    ("dep_end_unadj", "AC", "formula", "amount", "depEndUnadj", "期末数", "X9"),
    ("dep_open_adj", "AD", "editable", "amount", "depOpenAdj", "期初调整", ""),
    ("dep_aje_prov", "AE", "editable", "amount", "depAjeProv", "本期计提", "AE10"),
    ("dep_aje_other_inc", "AF", "editable", "amount", "depAjeOtherInc", "其他增加", "AE10"),
    ("dep_aje_dec_sublease", "AG", "editable", "amount", "depAjeDecSublease", "转租赁为融资租赁", "AG10"),
    ("dep_aje_dec_disposal", "AH", "editable", "amount", "depAjeDecDisposal", "转让或持有待售", "AG10"),
    ("dep_aje_other_dec", "AI", "editable", "amount", "depAjeOtherDec", "其他减少", "AG10"),
    ("dep_begin_aud", "AJ", "formula", "amount", "depBeginAud", "期初数", "AJ9"),
    ("dep_inc_aud", "AK", "formula", "amount", "depIncAud", "本期增加", "AJ9"),
    ("dep_dec_aud", "AL", "formula", "amount", "depDecAud", "本期减少", "AJ9"),
    ("dep_end_aud", "AM", "formula", "amount", "depEndAud", "期末数", "AJ9"),
    # ══ 减值准备 AN..BD（2 增 3 减，与折旧同构）═════════════════════════════
    ("impair_begin_unadj", "AN", "editable", "amount", "impairBeginUnadj", "期初数", "AN8"),
    ("impair_prov_unadj", "AO", "editable", "amount", "impairProvUnadj", "本期计提", "AO10"),
    ("impair_other_inc_unadj", "AP", "editable", "amount", "impairOtherIncUnadj", "其他增加", "AO10"),
    ("impair_dec_sublease", "AQ", "editable", "amount", "impairDecSublease", "转租赁为融资租赁", "AQ10"),
    ("impair_dec_disposal", "AR", "editable", "amount", "impairDecDisposal", "转让或持有待售", "AQ10"),
    ("impair_other_dec_unadj", "AS", "editable", "amount", "impairOtherDecUnadj", "其他减少", "AQ10"),
    ("impair_end_unadj", "AT", "formula", "amount", "impairEndUnadj", "期末数", "AO9"),
    ("impair_open_adj", "AU", "editable", "amount", "impairOpenAdj", "期初调整", ""),
    ("impair_aje_prov", "AV", "editable", "amount", "impairAjeProv", "本期计提", "AV10"),
    ("impair_aje_other_inc", "AW", "editable", "amount", "impairAjeOtherInc", "其他增加", "AV10"),
    ("impair_aje_dec_sublease", "AX", "editable", "amount", "impairAjeDecSublease", "转租赁为融资租赁", "AX10"),
    ("impair_aje_dec_disposal", "AY", "editable", "amount", "impairAjeDecDisposal", "转让或持有待售", "AX10"),
    ("impair_aje_other_dec", "AZ", "editable", "amount", "impairAjeOtherDec", "其他减少", "AX10"),
    ("impair_begin_aud", "BA", "formula", "amount", "impairBeginAud", "期初数", "BA9"),
    ("impair_inc_aud", "BB", "formula", "amount", "impairIncAud", "本期增加", "BA9"),
    ("impair_dec_aud", "BC", "formula", "amount", "impairDecAud", "本期减少", "BA9"),
    ("impair_end_aud", "BD", "formula", "amount", "impairEndAud", "期末数", "BA9"),
    # ══ 审定净值 BE..BF（🔴 审定口径，不是未审）═════════════════════════════
    ("net_begin_aud", "BE", "formula", "amount", "netBeginAud", "期初净值", "BE8"),
    ("net_end_aud", "BF", "formula", "amount", "netEndAud", "期末净值", "BE8"),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R12-R31。
#:
#: 🔴 三处易抄错：
#:   · `K`（原值未审期末）用 `SUM(D:G)-SUM(H:J)`（**含期初 D**），
#:     而 `AC`/`AT`（折旧/减值未审期末）用 `SUM(W:Y)-SUM(Z:AB)`（首格即期初）——
#:     区块起始列不同，range 端点不能平移复制。
#:   · 审定增加 `T` 是 `(E+F+G)+M+N+O`（3 增），`AK`/`BB` 是 `X+AE+Y+AF`（2 增，**交错顺序**）。
#:   · 审定减少 `U` 是 `(H+I+J)+P+Q+R`，`AL`/`BC` 是 `Z+AI+AB+AA+AG+AH`
#:     （**乱序但等价**，逐字保留模板原式，不"整理"成顺序 —— 整理等于改模板）。
FORMULA_TEMPLATES_H802: Final[dict[str, str]] = {
    "K": "=SUM(D{r}:G{r})-SUM(H{r}:J{r})",
    "S": "=D{r}+L{r}",
    "T": "=(E{r}+F{r}+G{r})+M{r}+N{r}+O{r}",
    "U": "=(H{r}+I{r}+J{r})+P{r}+Q{r}+R{r}",
    "V": "=S{r}+T{r}-U{r}",
    "AC": "=SUM(W{r}:Y{r})-SUM(Z{r}:AB{r})",
    "AJ": "=W{r}+AD{r}",
    "AK": "=X{r}+AE{r}+Y{r}+AF{r}",
    "AL": "=Z{r}+AI{r}+AB{r}+AA{r}+AG{r}+AH{r}",
    "AM": "=AJ{r}+AK{r}-AL{r}",
    "AT": "=SUM(AN{r}:AP{r})-SUM(AQ{r}:AS{r})",
    "BA": "=AN{r}+AU{r}",
    "BB": "=AO{r}+AV{r}+AP{r}+AW{r}",
    "BC": "=AQ{r}+AZ{r}+AS{r}+AR{r}+AX{r}+AY{r}",
    "BD": "=BA{r}+BB{r}-BC{r}",
    "BE": "=S{r}-AJ{r}-BA{r}",
    "BF": "=V{r}-AM{r}-BD{r}",
}

SPEC_H802: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H802,
    sheet_key=SHEET_KEY_H802,
    table_key=ROWS_TABLE_KEY_H802,
    template_id=TEMPLATE_ID_H802,
    table_name=f"GT_{TEMPLATE_ID_H802}_ROWS",
    uuid_col=UUID_COL_H802,
    first_data_row=FIRST_DATA_ROW_H802,
    last_data_row=LAST_DATA_ROW_H802,
    footer_row=FOOTER_ROW_H802,
    header_group_row=HEADER_TOP_ROW_H802,
    header_leaf_row=HEADER_LEAF_ROW_H802,
    store_item_id=STORE_ITEM_ID_H802,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H802,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H802,
    formula_columns=tuple(FORMULA_TEMPLATES_H802),
    formula_templates=FORMULA_TEMPLATES_H802,
    footer_marker=FOOTER_MARKER_H802,
    error_label="H8-2 使用权资产、累计折旧及减值准备明细表",
)
